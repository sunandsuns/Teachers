"""个人书架 API：联网检索、加书、改状态、申请公开。

导读为什么放后台生成
--------------------------------------------------------------------------
一份导读要等模型跑十几到几十秒（上游故障时还要走完整个探活预算）。把这段
等待压在"添加"这个动作上，用户点了按钮就得盯着转圈——而他真正要的只是
"这本书进我的书架了"。所以顺序是：**先入库并立刻返回**，导读交给后台任务，
前端过几秒重新拉一次列表就能看到。

错误怎么回
--------------------------------------------------------------------------
这里**一个 try/except 都没有**。``UserBookError`` 是业务错误（400 + ``code``）、
``DatabaseUnavailable`` 是库故障（503），两者都由 ``server/errors.py`` 的全局
出口统一转换——原先这两条各有各的写法，而"库不可用"那一句在三个 router 里
抄了三遍。

登录
--------------------------------------------------------------------------
**全组都要登录**，挂在路由级 ``dependencies`` 上而不是每个 handler 各写一遍
（理由见 ``deps.py``）。这个 router 原先正是全项目唯一的例外——逐个 handler 手
写，而漏掉一个不会报错，只会安静地对匿名开放。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..deps import require_user
from ..errors import DB_BACKED
from ..formatting import iso_time
from ..schemas.common import OkResponse
from ..schemas.shelf import (
    AddBookRequest,
    BookSearchResponse,
    CandidateIn,
    SearchRequest,
    ShelfBookOut,
    ShelfResponse,
    UpdateBookRequest,
)
from ..services import book_search
from ..services.auth import User
from ..services.book_search import BookCandidate
from ..services.guide import generate_guide
from ..services.user_books import STATUSES, ShelfBook, get_user_book_store

router = APIRouter(
    prefix="/api/shelf",
    tags=["shelf"],
    dependencies=[Depends(require_user)],
    responses=DB_BACKED,
)

#: 一次列表最多返回几本。已满的话前端靠 ``total`` 知道还有更多。
MAX_PAGE = 200


# ── 出入参转换 ──────────────────────────────────────────────────────────────
# 放在 router 而不是模型上：``schemas/`` 是纯数据，不该反过来 import 服务层。


def _to_candidate(payload: CandidateIn) -> BookCandidate:
    """入参 → 服务层的书本对象。顺手把各字段两边的空白剪掉。"""
    return BookCandidate(
        title=payload.title.strip(),
        author=payload.author.strip(),
        year=payload.year.strip(),
        cover_url=payload.cover_url.strip(),
        source_key=payload.source_key.strip(),
        source=payload.source.strip() or "openlibrary",
        summary=payload.summary.strip(),
        subjects=tuple(s.strip() for s in payload.subjects if s.strip())[:20],
    )


def _out(book: ShelfBook) -> ShelfBookOut:
    """服务层的书 → 响应模型。

    时间戳统一走 ``formatting.iso_time``（本地时区带偏移量）。这两个字段以前用的是
    另一套 UTC 格式——同一个项目里两种时间写法，是 `_iso` 被抄了四份留下的。
    """
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
        created_at=iso_time(book.created_ts) or "",
        updated_at=iso_time(book.updated_ts) or "",
    )


# ── 后台任务 ────────────────────────────────────────────────────────────────


def _fill_guide(book_id: int, candidate: BookCandidate) -> None:
    """后台补导读。任何失败都只吞掉——书已经在架上了，导读是加分项。"""
    try:
        guide, _ = generate_guide(candidate)
        if guide:
            get_user_book_store().set_guide(book_id, guide)
    except Exception:  # noqa: BLE001 — 后台任务，失败不该冒泡到任何地方
        pass


# ── 路由 ────────────────────────────────────────────────────────────────────


@router.post("/search", response_model=BookSearchResponse)
def search_books(payload: SearchRequest):
    """联网检索书籍，返回候选列表供用户挑。

    只检索、不入库。用户挑中哪本由他在前端决定。检索不碰数据库，所以上游
    挂掉时这里返回的是 ``error`` 有值、``results`` 为空——不是 503。
    """
    outcome = book_search.search_books(payload.title, payload.author, limit=payload.limit)
    return BookSearchResponse(
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
    limit: int = Query(100, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
):
    """我的书架。"""
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_status", "message": "阅读状态不合法"},
        )
    store = get_user_book_store()
    total, books = store.list_for(user.id, status=status, limit=limit, offset=offset)
    counts = store.counts_for_user(user.id)
    return ShelfResponse(total=total, counts=counts, books=[_out(b) for b in books])


@router.post("/books", response_model=ShelfBookOut, status_code=201)
def add_book(payload: AddBookRequest, background: BackgroundTasks, user: User = Depends(require_user)):
    """把一本书加进我的书架。

    流程：补详情（联网，约 1 秒）→ 入库并立刻返回 → 后台生成导读。
    """
    store = get_user_book_store()
    candidate = _to_candidate(payload)
    if not candidate.title:
        raise HTTPException(
            status_code=400, detail={"code": "bad_title", "message": "书名不能为空"}
        )

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

    book = store.add(user.id, candidate, guide="", status=payload.status)
    if payload.with_guide:
        background.add_task(_fill_guide, book.id, candidate)
    return _out(book)


@router.get("/books/{book_id}", response_model=ShelfBookOut)
def get_book(book_id: int, user: User = Depends(require_user)):
    """取一本书的完整信息（含导读）。前端加完书后靠它轮询导读是否生成好了。"""
    book = get_user_book_store().get(book_id, user_id=user.id)
    if book is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )
    return _out(book)


@router.patch("/books/{book_id}", response_model=ShelfBookOut)
def update_book(book_id: int, payload: UpdateBookRequest, user: User = Depends(require_user)):
    """改阅读状态或书名/作者。"""
    book = get_user_book_store().update(
        book_id, user.id, status=payload.status, title=payload.title, author=payload.author
    )
    if book is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )
    return _out(book)


@router.delete("/books/{book_id}", response_model=OkResponse)
def remove_book(book_id: int, user: User = Depends(require_user)):
    """从我的书架上删掉一本。"""
    if not get_user_book_store().remove(book_id, user.id):
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )
    return OkResponse()


@router.post("/books/{book_id}/submit", response_model=ShelfBookOut)
def submit_for_review(book_id: int, user: User = Depends(require_user)):
    """申请把这本书放进公共书架，等管理员审核。"""
    book = get_user_book_store().submit_for_review(book_id, user.id)
    if book is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )
    return _out(book)


@router.post("/books/{book_id}/cancel", response_model=ShelfBookOut)
def cancel_review(book_id: int, user: User = Depends(require_user)):
    """撤回公开申请。"""
    book = get_user_book_store().cancel_review(book_id, user.id)
    if book is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )
    return _out(book)
