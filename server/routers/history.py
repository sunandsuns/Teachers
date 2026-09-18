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

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.history import MAX_LIMIT, get_history_store

router = APIRouter(prefix="/api/history", tags=["history"])


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
):
    """按时间倒序列出全部记录（平铺）。

    写成 ``async`` 是合适的：库就在本机，查询是微秒级的，
    不会像调用外部模型那样长时间占住事件循环。
    """
    store = get_history_store()
    total, records = store.list(limit=limit, offset=offset)
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
):
    """按话题聚合列出，最近活跃的在前。"""
    store = get_history_store()
    total, topics = store.list_topics(limit=limit, offset=offset)
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
):
    """一个话题里的全部问答，按时间正序（读起来就是一段对话）。"""
    store = get_history_store()
    total, records = store.list_by_topic(topic_id, limit=limit, offset=offset)
    return HistoryListResponse(
        available=store.available,
        error=store.error,
        total=total,
        items=[_to_item(r) for r in records],
    )


@router.delete("/topics/{topic_id}", response_model=DeleteResponse)
async def delete_topic(topic_id: str):
    """删掉整个话题。"""
    deleted = get_history_store().delete_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"话题不存在: {topic_id}")
    return DeleteResponse(deleted=deleted)


@router.get("/status", response_model=HistoryStatusResponse)
async def history_status():
    """存储概况。**打开「回响」页时会调它，顺带触发机会式清理。**"""
    return HistoryStatusResponse(**get_history_store().status())


@router.delete("/{record_id}", response_model=DeleteResponse)
async def delete_history(record_id: int):
    """删掉一条。"""
    if not get_history_store().delete(record_id):
        raise HTTPException(status_code=404, detail=f"记录不存在: id={record_id}")
    return DeleteResponse(deleted=1)


@router.delete("", response_model=DeleteResponse)
async def clear_history():
    """清空全部记录。"""
    return DeleteResponse(deleted=get_history_store().clear())
