"""历史记录 API 路由（界面上的「回响」）。

与前几个路由同一个套路：只做参数校验与响应建模，存取规则全在
``services/history.py``。这里唯一需要动脑的地方是**"库不可用"该回什么**——
答案是 200 而不是 500，理由见下方各接口的说明。

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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import current_user
from ..services.auth import User
from ..services.history import MAX_LIMIT, get_history_store

#: 一次批量删除最多接受多少个目标。见 :class:`BulkDeleteRequest`。
MAX_BULK_TARGETS = 500

router = APIRouter(prefix="/api/history", tags=["history"])


def _owner(user: Optional[User]) -> Optional[int]:
    """把"当前是谁"收敛成一个归属 id。

    未登录时返回 ``None``——那是 :mod:`services.history` 里"匿名访客那一份"
    的约定值（``user_id IS NULL``），不是"不过滤"。
    """
    return user.id if user is not None else None


class HistoryItem(BaseModel):
    """一条求教记录。"""

    id: int
    question: str
    answer: str
    model: Optional[str] = Field(None, description="产出回答的模型；null 表示本地检索降级")
    llm_used: bool
    retrieved_count: int
    conversation_id: Optional[str] = Field(
        None, description="所属话题；升级前的老记录为 null"
    )
    created_at: str = Field(..., description="本地时区的 ISO 8601")
    created_ts: float = Field(..., description="Unix 时间戳（秒）")


class TopicItem(BaseModel):
    """一个话题：一次会话里的连续追问聚成的一张卡片。"""

    id: str = Field(..., description="话题 id；老记录是 solo:<记录id>")
    title: str = Field(..., description="话题的第一问")
    question_count: int
    first_ts: float
    last_ts: float
    latest_question: str
    latest_answer: str


class HistoryListResponse(BaseModel):
    """记录列表。

    ``available=False`` 时列表为空、``error`` 里是原因——这是接口层面的
    **优雅降级**：数据库建不出来（程序目录只读、磁盘满）不该让界面报错，
    而应该照常渲染、顺手把原因说清楚。
    """

    available: bool
    error: str
    total: int
    items: list[HistoryItem]


class TopicListResponse(BaseModel):
    """话题列表。``total`` 是**话题**数，不是记录数。"""

    available: bool
    error: str
    total: int
    items: list[TopicItem]


class HistoryStatusResponse(BaseModel):
    """存储概况：有多少条、保留多久、下次什么时候清理。"""

    available: bool
    error: str
    db_path: str
    total: int
    retention_days: float
    last_purge_at: Optional[str]
    next_purge_at: Optional[str]
    size_bytes: int


class DeleteResponse(BaseModel):
    """删除结果。``deleted`` 是实际删掉的条数。"""

    deleted: int


class BulkDeleteRequest(BaseModel):
    """勾选删除的目标：记录 id 与话题 id 可以混着给，也可以只给一边。

    两个清单都设了长度上限：这是**不可撤销**的操作，与其收下一个畸形请求
    （比如几万个 id）去拼一条巨型 SQL，不如当场返回 422。界面上的勾选量来自
    已加载的列表，远够不到这个数。
    """

    ids: list[int] = Field(
        default_factory=list,
        max_length=MAX_BULK_TARGETS,
        description="要删的记录 id",
    )
    topics: list[str] = Field(
        default_factory=list,
        max_length=MAX_BULK_TARGETS,
        description="要整段删掉的话题 id（含老记录的 solo:<记录id>）",
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


@router.get("", response_model=HistoryListResponse)
async def list_history(
    limit: int = Query(20, ge=1, le=MAX_LIMIT, description="本页条数"),
    offset: int = Query(0, ge=0, description="跳过的条数，用于翻页"),
    user: Optional[User] = Depends(current_user),
):
    """按时间倒序列出**当前这个人**的记录（平铺）。

    写成 ``async`` 是合适的：库就在本机，查询是微秒级的，
    不会像调用外部模型那样长时间占住事件循环。
    """
    store = get_history_store()
    total, records = store.list(user_id=_owner(user), limit=limit, offset=offset)
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
    user: Optional[User] = Depends(current_user),
):
    """按话题聚合列出，最近活跃的在前。"""
    store = get_history_store()
    total, topics = store.list_topics(user_id=_owner(user), limit=limit, offset=offset)
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
    user: Optional[User] = Depends(current_user),
):
    """一个话题里的全部问答，按时间正序（读起来就是一段对话）。"""
    store = get_history_store()
    total, records = store.list_by_topic(
        topic_id, user_id=_owner(user), limit=limit, offset=offset
    )
    return HistoryListResponse(
        available=store.available,
        error=store.error,
        total=total,
        items=[_to_item(r) for r in records],
    )


@router.delete("/topics/{topic_id}", response_model=DeleteResponse)
async def delete_topic(topic_id: str, user: Optional[User] = Depends(current_user)):
    """删掉整个话题。**只删自己的**——别人的话题在这里表现为"不存在"。"""
    deleted = get_history_store().delete_topic(topic_id, user_id=_owner(user))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"话题不存在: {topic_id}")
    return DeleteResponse(deleted=deleted)


@router.post("/delete", response_model=DeleteResponse)
async def delete_selected(
    request: BulkDeleteRequest, user: Optional[User] = Depends(current_user)
):
    """按记录与话题**混合**删一批——界面上勾选删除走的就是这里。

    为什么是 ``POST`` 而不是 ``DELETE``：要删的东西是一份清单（记录 id 与话题 id
    两串），塞进 URL 既长又容易撞上各种长度限制，而带 body 的 ``DELETE`` 在
    代理与客户端那边历来支持不齐。这里没有幂等语义要守，POST 更实在。

    **删不到东西不算失败**：勾选的目标里可能有刚被过期清理掉的一条，那不该让
    整批失败。返回 200 与真实删掉的条数，由界面去说明结果。
    """
    return DeleteResponse(
        deleted=get_history_store().delete_many(
            ids=request.ids, topics=request.topics, user_id=_owner(user)
        )
    )


@router.get("/status", response_model=HistoryStatusResponse)
async def history_status(user: Optional[User] = Depends(current_user)):
    """存储概况。**打开「回响」页时会调它，顺带触发机会式清理。**"""
    return HistoryStatusResponse(**get_history_store().status(user_id=_owner(user)))


@router.delete("/{record_id}", response_model=DeleteResponse)
async def delete_history(record_id: int, user: Optional[User] = Depends(current_user)):
    """删掉一条。**只删自己的**。"""
    if not get_history_store().delete(record_id, user_id=_owner(user)):
        raise HTTPException(status_code=404, detail=f"记录不存在: id={record_id}")
    return DeleteResponse(deleted=1)


@router.delete("", response_model=DeleteResponse)
async def clear_history(user: Optional[User] = Depends(current_user)):
    """清空**当前这个人**的记录。匿名访客清的是"无归属"的那一份。"""
    return DeleteResponse(deleted=get_history_store().clear(user_id=_owner(user)))
