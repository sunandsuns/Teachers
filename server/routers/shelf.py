"""个人书架 API：联网检索、加书、改状态、申请公开。

导读为什么放后台生成
--------------------------------------------------------------------------
一份导读要等模型跑十几到几十秒（上游故障时还要走完整个探活预算）。把这段
等待压在"添加"这个动作上，用户点了按钮就得盯着转圈——而他真正要的只是
"这本书进我的书架了"。所以顺序是：**先入库并立刻返回**，导读交给后台任务，
前端过几秒重新拉一次列表就能看到。

后台生成失败为什么要落库、还要给一个重试入口
--------------------------------------------------------------------------
书架上的书**没有正文**（联网检索只拿得到书名、作者、封面、简介），导读是它唯一
可读的内容。而这次后台生成只跑一次，不会自己重来——模型当时挂了，这本书就
永远是一张空卡片。所以两件事缺一不可：失败写进 ``guide_error``（界面上说得出
缘由），再加一个 ``POST /books/{id}/guide`` 让人点一下重来。原先失败被整个吞掉，
用户看到的是「这本书还没有导读」，既不知道出了什么事，也没有下一步。

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
        # **不做兜底**。缺省成某个具体源会让"客户端没说是哪个源"被当成"这是
        # OpenLibrary 的书"，于是 `fetch_detail` 拿一串微信读书的 bookId 去拼
        # `/works/…`，白等一次超时。空串就是"不知道"，那边直接返回 None。
        source=payload.source.strip(),
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
        guide_error=book.guide_error,
        status=book.status,
        visibility=book.visibility,
        review_note=book.review_note,
        created_at=iso_time(book.created_ts) or "",
        updated_at=iso_time(book.updated_ts) or "",
    )


# ── 后台任务 ────────────────────────────────────────────────────────────────


def _fill_guide(book_id: int, candidate: BookCandidate) -> None:
    """后台补导读。

    失败**不抛**——书已经在架上了，导读是加分项，不该让加书这个动作回报失败。
    但也不静默：原因写进 ``guide_error``。这两条必须同时成立，理由是这个页面的
    形状——书架上的书没有正文，导读就是唯一能读的东西。它空了之后，用户手上
    是一张除了状态药丸什么都没有的卡片，连"要不要重试"都无从判断。
    """
    try:
        outcome = generate_guide(candidate)
        text, error = (outcome.text, "") if outcome.ok else ("", outcome.error)
    except Exception as exc:  # noqa: BLE001 — 生成器自己炸了，同样要留下原因
        text, error = "", f"导读生成异常：{exc}"

    try:
        store = get_user_book_store()
        if text:
            store.set_guide(book_id, text)
        else:
            store.set_guide_error(book_id, error)
    except Exception:  # noqa: BLE001 — 后台任务，落库失败不该冒泡到任何地方
        pass


def _candidate_of(book: ShelfBook) -> BookCandidate:
    """把书架上的一行还原成"生成导读"要的那几个字段。

    重新生成走的是与首次生成**同一条**提示词路径，所以这里要原样把元信息还回去：
    换一条路径就等于让同一本书前后两份导读出自两套输入，差异解释不清。
    """
    return BookCandidate(
        title=book.title,
        author=book.author,
        year=book.year,
        cover_url=book.cover_url,
        source_key=book.source_key,
        source=book.source,
        summary=book.summary,
        subjects=book.subjects,
    )


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
        unavailable=outcome.unavailable,
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

    # 补详情：只有 OpenLibrary 的书需要单独取简介（微信读书的简介在搜索响应里
    # 就带上了，豆瓣不提供）。`fetch_detail` 对不支持的源直接返回 None，不白跑。
    if candidate.source_key:
        detail = book_search.fetch_detail(candidate.source, candidate.source_key)
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


@router.post("/books/{book_id}/guide", response_model=ShelfBookOut)
def regenerate_guide(
    book_id: int, background: BackgroundTasks, user: User = Depends(require_user)
):
    """重新生成这本书的导读。

    导读失败是**一次性**的：加书时那次后台任务不会自己重来，于是模型当时挂了，
    这本书的导读就永远是空的——而它是这本书在架子上唯一可读的内容。这个接口
    就是那个人工重试的落脚点。

    顺序是"先清掉上一次的失败原因，再起任务"：不清的话，从点了重新生成到这次
    跑完之间，界面会一边说"生成中"、一边还挂着上次的失败。

    返回的是**当前**这条记录（``has_guide`` 多半仍是 false）——生成在后台跑，
    前端过几秒重新拉一次列表就能看到，不必把这个请求挂上十几秒。
    """
    store = get_user_book_store()
    book = store.get(book_id, user_id=user.id)
    if book is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_on_shelf", "message": "书架里没有这本书"}
        )

    store.set_guide_error(book.id, "")
    background.add_task(_fill_guide, book.id, _candidate_of(book))
    return _out(store.get(book.id, user_id=user.id) or book)


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
