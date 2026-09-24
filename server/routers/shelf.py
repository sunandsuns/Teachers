"""个人书架 API：联网检索、加书、改状态、申请公开。

导读为什么放后台生成
--------------------------------------------------------------------------
一份导读要等模型跑十几到几十秒（上游故障时还要走完整个探活预算）。把这段
等待压在"添加"这个动作上，用户点了按钮就得盯着转圈——而他真正要的只是
"这本书进我的书架了"。所以顺序是：**先入库并立刻返回**，导读交给后台任务，
前端过几秒重新拉一次列表就能看到。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import require_user
from ..services import book_search
from ..services.auth import User
from ..services.book_search import BookCandidate
from ..services.db import DatabaseUnavailable
from ..services.guide import generate_guide
from ..services.user_books import (
    STATUSES,
    ShelfBook,
    UserBookError,
    get_user_book_store,
)

router = APIRouter(prefix="/api/shelf", tags=["shelf"])


# ── 出入参 ──────────────────────────────────────────────────────────────


class CandidateIn(BaseModel):
    """一本书的元信息。前端把用户选中的候选原样回传。"""

    title: str = Field(..., max_length=300)
    author: str = Field("", max_length=300)
    year: str = Field("", max_length=20)
    cover_url: str = Field("", max_length=500)
    source_key: str = Field("", max_length=100)
    source: str = Field("openlibrary", max_length=50)
    summary: str = Field("", max_length=4000)
    subjects: list[str] = Field(default_factory=list, max_length=20)

    def to_candidate(self) -> BookCandidate:
        return BookCandidate(
            title=self.title.strip(),
            author=self.author.strip(),
            year=self.year.strip(),
            cover_url=self.cover_url.strip(),
            source_key=self.source_key.strip(),
            source=self.source.strip() or "openlibrary",
            summary=self.summary.strip(),
            subjects=tuple(s.strip() for s in self.subjects if s.strip())[:20],
        )


class SearchRequest(BaseModel):
    title: str = Field("", max_length=300)
    author: str = Field("", max_length=300)
    limit: int = Field(6, ge=1, le=20)


class SearchResponse(BaseModel):
    results: list[CandidateIn]
    error: str = ""


class AddBookRequest(CandidateIn):
    status: str = Field("wish", description="wish / reading / done")
    with_guide: bool = Field(True, description="是否让模型生成导读")


class UpdateBookRequest(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = Field(None, max_length=300)
    author: Optional[str] = Field(None, max_length=300)


class ShelfBookOut(BaseModel):
    id: int
    title: str
    author: str
    year: str
    cover_url: str
    source_key: str
    summary: str
    subjects: list[str]
    guide: str
    has_guide: bool
    status: str
    visibility: str
    review_note: str
    created_at: str
    updated_at: str


class ShelfResponse(BaseModel):
    total: int
    counts: dict[str, int]
    books: list[ShelfBookOut]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _out(book: ShelfBook) -> ShelfBookOut:
    return ShelfBookOut(
        id=book.id,
        title=book.title,
        author=book.author,
        year=book.year,
        cover_url=book.cover_url,
        source_key=book.source_key,
        summary=book.summary,
        subjects=list(book.subjects),
        guide=book.guide,
        has_guide=book.has_guide,
        status=book.status,
        visibility=book.visibility,
        review_note=book.review_note,
        created_at=_iso(book.created_ts),
        updated_at=_iso(book.updated_ts),
    )


def _shelf_error(exc: UserBookError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="数据库暂不可用，请稍后再试")


# ── 后台任务 ────────────────────────────────────────────────────────────


def _fill_guide(book_id: int, candidate: BookCandidate) -> None:
    """后台补导读。任何失败都只吞掉——书已经在架上了，导读是加分项。"""
    try:
        guide, _ = generate_guide(candidate)
        if guide:
            get_user_book_store().set_guide(book_id, guide)
    except Exception:  # noqa: BLE001 — 后台任务，失败不该冒泡到任何地方
        pass


# ── 路由 ────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
def search_books(payload: SearchRequest, user: User = Depends(require_user)):
    """联网检索书籍，返回候选列表供用户挑。

    只检索、不入库。用户挑中哪本由他在前端决定。
    """
    outcome = book_search.search_books(payload.title, payload.author, limit=payload.limit)
    return SearchResponse(
        results=[
            CandidateIn(
                title=c.title, author=c.author, year=c.year, cover_url=c.cover_url,
                source_key=c.source_key, source=c.source, summary=c.summary,
                subjects=list(c.subjects),
            )
            for c in outcome.results
        ],
        error=outcome.error,
    )


@router.get("", response_model=ShelfResponse)
def list_shelf(
    status: Optional[str] = Query(None, description="按阅读状态过滤"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
):
    """我的书架。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="阅读状态不合法")
    store = get_user_book_store()
    try:
        total, books = store.list_for(user.id, status=status, limit=limit, offset=offset)
        counts = store.counts_for_user(user.id)
    except DatabaseUnavailable as exc:
        raise _db_unavailable(exc) from exc
    return ShelfResponse(total=total, counts=counts, books=[_out(b) for b in books])


@router.post("/books", response_model=ShelfBookOut, status_code=201)
def add_book(
    payload: AddBookRequest,
    background: BackgroundTasks,
    user: User = Depends(require_user),
):
    """把一本书加进我的书架。

    流程：补详情（联网，约 1 秒）→ 入库并立刻返回 → 后台生成导读。
    """
    store = get_user_book_store()
    candidate = payload.to_candidate()
    if not candidate.title:
        raise HTTPException(status_code=400, detail="书名不能为空")

    # 补详情：列表阶段只带了书名/作者/主题，简介要单独取。拿不到就用现有的。
    if candidate.source_key:
        detail = book_search.fetch_detail(candidate.source_key)
        if detail is not None:
            candidate = BookCandidate(
                title=candidate.title,
                author=candidate.author or detail.author,
                year=candidate.year or detail.year,
                cover_url=candidate.cover_url,
                source_key=candidate.source_key,
                source=candidate.source,
                summary=candidate.summary or detail.summary,
                subjects=candidate.subjects or detail.subjects,
            )

    try:
        book = store.add(user.id, candidate, guide="", status=payload.status)
    except UserBookError as exc:
        raise _shelf_error(exc) from exc
    except DatabaseUnavailable as exc:
        raise _db_unavailable(exc) from exc

    if payload.with_guide:
        background.add_task(_fill_guide, book.id, candidate)
    return _out(book)


@router.get("/books/{book_id}", response_model=ShelfBookOut)
def get_book(book_id: int, user: User = Depends(require_user)):
    """取一本书的完整信息（含导读）。前端加完书后靠它轮询导读是否生成好了。"""
    book = get_user_book_store().get(book_id, user_id=user.id)
    if book is None:
        raise HTTPException(status_code=404, detail="书架里没有这本书")
    return _out(book)


@router.patch("/books/{book_id}", response_model=ShelfBookOut)
def update_book(book_id: int, payload: UpdateBookRequest, user: User = Depends(require_user)):
    """改阅读状态或书名/作者。"""
    try:
        book = get_user_book_store().update(
            book_id, user.id, status=payload.status, title=payload.title, author=payload.author
        )
    except UserBookError as exc:
        raise _shelf_error(exc) from exc
    if book is None:
        raise HTTPException(status_code=404, detail="书架里没有这本书")
    return _out(book)


@router.delete("/books/{book_id}")
def remove_book(book_id: int, user: User = Depends(require_user)):
    """从我的书架上删掉一本。"""
    if not get_user_book_store().remove(book_id, user.id):
        raise HTTPException(status_code=404, detail="书架里没有这本书")
    return {"ok": True}


@router.post("/books/{book_id}/submit", response_model=ShelfBookOut)
def submit_for_review(book_id: int, user: User = Depends(require_user)):
    """申请把这本书放进公共书架，等管理员审核。"""
    book = get_user_book_store().submit_for_review(book_id, user.id)
    if book is None:
        raise HTTPException(status_code=404, detail="书架里没有这本书")
    return _out(book)


@router.post("/books/{book_id}/cancel", response_model=ShelfBookOut)
def cancel_review(book_id: int, user: User = Depends(require_user)):
    """撤回公开申请。"""
    book = get_user_book_store().cancel_review(book_id, user.id)
    if book is None:
        raise HTTPException(status_code=404, detail="书架里没有这本书")
    return _out(book)
