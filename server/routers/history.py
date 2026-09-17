"""历史记录 API 路由（界面上的「回响」）。

与前几个路由同一个套路：只做参数校验与响应建模，存取规则全在
``services/history.py``。这里唯一需要动脑的地方是**"库不可用"该回什么**——
答案是 200 而不是 500，理由见下方各接口的说明。
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
    created_at: str = Field(..., description="本地时区的 ISO 8601")
    created_ts: float = Field(..., description="Unix 时间戳（秒）")


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
        created_at=record.created_at,
        created_ts=record.created_ts,
    )


@router.get("", response_model=HistoryListResponse)
async def list_history(
    limit: int = Query(20, ge=1, le=MAX_LIMIT, description="本页条数"),
    offset: int = Query(0, ge=0, description="跳过的条数，用于翻页"),
):
    """按时间倒序列出历史记录。

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
