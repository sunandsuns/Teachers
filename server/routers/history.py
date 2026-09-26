"""历史记录 API 路由（界面上的「回响」）。

只做参数校验与响应建模，存取规则全在 ``services/history.py``。

「库不可用」该回什么
--------------------------------------------------------------------------
**这一组回 200，不是 503。** 它们是全项目仅有的两处"降级成空态"之一（另一处是
画像），依据是响应的类型**能说清发生了什么**：``HistoryListResponse`` 里带着
``available`` 与 ``error``，用户看到的是"你还没有记录"加一句原因，而不是一个
报错页。

反过来说，凡是响应里没地方写 ``available`` 的接口（裸列表、聚合对象）都不能这么
做——那是把"读不到"伪装成"真的没有"。所以库故障的默认出口是 503（见
``errors.py``），要降级就得在这里显式接住。这样偏离默认的地方一眼可见。

**声明里也不写 503**：契约要和行为一致，而不是"凡碰库的接口都声明 503"。这一组
所有接口都会降级（存储层的公开方法一律不抛异常），真声明了 503，生成的客户端就会
带一条永远走不到的分支。其他碰库的组照旧声明——见「画像」那组的同样处理，以及
``tests/unit/test_contract.py`` 里把这条钉住的守卫。

两种列表
--------------------------------------------------------------------------
- ``/api/history``      平铺：一条记录一项
- ``/api/history/topics`` 聚合：一次会话的连续追问并成一张卡片

「回响」页用的是后者——追问会让平铺列表迅速长到翻不动，而是话题卡片既能一眼
看全有多少件事，点开又能顺着读完整段对话。

**路由顺序有讲究**：``/topics`` 必须写在 ``/{record_id}`` 之前。FastAPI 按注册
顺序匹配，而 ``record_id`` 声明为 ``int``——``/topics`` 撞上它会因为类型不符而
直接 422，根本轮不到后面那条路由。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_user
from ..errors import NOT_FOUND, UNAUTHORIZED, merge
from ..schemas.common import DeleteResponse
from ..schemas.history import (
    BulkDeleteRequest,
    HistoryItem,
    HistoryListResponse,
    HistoryStatusResponse,
    TopicItem,
    TopicListResponse,
)
from ..services.auth import User
from ..services.history import MAX_LIMIT, get_history_store

# 「回响」是每个人的问答记录，必须登录。理由与做法见 `deps.py`。
# 错误面比其他组窄：库故障在这里表现为 ``available: false``，不占错误码。
router = APIRouter(
    prefix="/api/history",
    tags=["history"],
    dependencies=[Depends(require_user)],
    responses=merge(UNAUTHORIZED, NOT_FOUND),
)


def _to_item(record) -> HistoryItem:
    return HistoryItem(
        id=record.id,
        question=record.question,
        answer=record.answer,
        model=record.model,
        llm_used=record.llm_used,
        retrieved_count=record.retrieved_count,
        conversation_id=record.conversation_id,
        created_at=record.created_at,
        created_ts=record.created_ts,
    )


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


@router.get("", response_model=HistoryListResponse)
async def list_history(
    limit: int = Query(20, ge=1, le=MAX_LIMIT, description="本页条数"),
    offset: int = Query(0, ge=0, description="跳过的条数，用于翻页"),
    user: User = Depends(require_user),
):
    """按时间倒序列出**当前这个人**的记录（平铺）。

    写成 ``async`` 是合适的：库就在本机，查询是微秒级的，
    不会像调用外部模型那样长时间占住事件循环。
    """
    store = get_history_store()
    total, records = store.list(user_id=user.id, limit=limit, offset=offset)
    return HistoryListResponse(
        available=store.available,
        error=store.error,
        total=total,
        items=[_to_item(r) for r in records],
    )


@router.get("/topics", response_model=TopicListResponse)
async def list_topics(
    limit: int = Query(20, ge=1, le=MAX_LIMIT, description="本页话题数"),
    offset: int = Query(0, ge=0, description="跳过的话题数，用于翻页"),
    user: User = Depends(require_user),
):
    """按话题聚合列出，最近活跃的在前。"""
    store = get_history_store()
    total, topics = store.list_topics(user_id=user.id, limit=limit, offset=offset)
    return TopicListResponse(
        available=store.available,
        error=store.error,
        total=total,
        items=[
            TopicItem(
                id=topic.id,
                title=topic.title,
                question_count=topic.question_count,
                first_ts=topic.first_ts,
                last_ts=topic.last_ts,
                latest_question=topic.latest_question,
                latest_answer=topic.latest_answer,
            )
            for topic in topics
        ],
    )


@router.get("/topics/{topic_id}", response_model=HistoryListResponse)
async def list_topic_records(
    topic_id: str,
    limit: int = Query(MAX_LIMIT, ge=1, le=MAX_LIMIT, description="本页条数"),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
):
    """一个话题里的全部问答，按时间正序（读起来就是一段对话）。"""
    store = get_history_store()
    total, records = store.list_by_topic(
        topic_id, user_id=user.id, limit=limit, offset=offset
    )
    return HistoryListResponse(
        available=store.available,
        error=store.error,
        total=total,
        items=[_to_item(r) for r in records],
    )


@router.delete("/topics/{topic_id}", response_model=DeleteResponse)
async def delete_topic(topic_id: str, user: User = Depends(require_user)):
    """删掉整个话题。**只删自己的**——别人的话题在这里表现为"不存在"。"""
    deleted = get_history_store().delete_topic(topic_id, user_id=user.id)
    if not deleted:
        raise _not_found("topic_not_found", f"话题不存在: {topic_id}")
    return DeleteResponse(deleted=deleted)


@router.post("/delete", response_model=DeleteResponse)
async def delete_selected(request: BulkDeleteRequest, user: User = Depends(require_user)):
    """按记录与话题**混合**删一批——界面上勾选删除走的就是这里。

    为什么是 ``POST`` 而不是 ``DELETE``：要删的东西是一份清单（记录 id 与话题 id
    两串），塞进 URL 既长又容易撞上各种长度限制，而带 body 的 ``DELETE`` 在
    代理与客户端那边历来支持不齐。这里没有幂等语义要守，POST 更实在。

    **删不到东西不算失败**：勾选的目标里可能有刚被过期清理掉的一条，那不该让
    整批失败。返回 200 与真实删掉的条数，由界面去说明结果。
    """
    return DeleteResponse(
        deleted=get_history_store().delete_many(
            ids=request.ids, topics=request.topics, user_id=user.id
        )
    )


@router.get("/status", response_model=HistoryStatusResponse)
async def history_status(user: User = Depends(require_user)):
    """存储概况。**打开「回响」页时会调它，顺带触发机会式清理。**"""
    return HistoryStatusResponse(**get_history_store().status(user_id=user.id))


@router.delete("/{record_id}", response_model=DeleteResponse)
async def delete_history(record_id: int, user: User = Depends(require_user)):
    """删掉一条。**只删自己的**。"""
    if not get_history_store().delete(record_id, user_id=user.id):
        raise _not_found("record_not_found", f"记录不存在: id={record_id}")
    return DeleteResponse(deleted=1)


@router.delete("", response_model=DeleteResponse)
async def clear_history(user: User = Depends(require_user)):
    """清空**当前这个人**的记录。"""
    return DeleteResponse(deleted=get_history_store().clear(user_id=user.id))
