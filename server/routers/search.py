"""全文检索 API 路由。"""

from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services.content_loader import get_loader
from ..services.retriever import build_retriever_from_loader, get_retriever

router = APIRouter(prefix="/api/search", tags=["search"])

#: 来源过滤：不限 / 只看深读笔记 / 只看原典全文
KindFilter = Literal["all", "notes", "source"]


class SearchResponseItem(BaseModel):
    """单条检索结果。"""
    book_id: str
    book_title: str
    chapter_id: str
    chapter_title: str
    content: str
    score: float
    source: str
    kind: str
    offset: int


class SearchResponse(BaseModel):
    """检索响应。"""
    query: str
    total: int
    results: list[SearchResponseItem]


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="搜索关键词", min_length=1),
    top_k: int = Query(5, ge=1, le=20, description="返回结果数"),
    kind: KindFilter = Query("all", description="来源过滤：all / notes / source"),
):
    """全文检索：在深读笔记与原典全文中搜索关键词。

    ``kind`` 可用于只看解读或只看经文原句。
    """
    retriever = get_retriever()
    if not retriever.documents:
        loader = get_loader()
        retriever = build_retriever_from_loader(loader)

    results = retriever.search(q, top_k=top_k, kind=None if kind == "all" else kind)
    return SearchResponse(
        query=q,
        total=len(results),
        results=[
            SearchResponseItem(
                book_id=r.book_id,
                book_title=r.book_title,
                chapter_id=r.chapter_id,
                chapter_title=r.chapter_title,
                content=r.content,
                score=r.score,
                source=r.source,
                kind=r.kind,
                offset=r.offset,
            )
            for r in results
        ],
    )
