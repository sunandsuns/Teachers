"""后台管理 API。**每一个端点都需要管理员身份。**

分四块：数据总览、用户管理、新书审核、直接操作数据库。前三块是常规的
运营动作，最后一块是运维口子——它的安全边界写在 ``services/admin.py``
的模块注释里。

错误怎么回
--------------------------------------------------------------------------
这里**一个 try/except 都没有**：``AdminError``（表不存在、动了保护列）由全局
出口转成 400，``DatabaseUnavailable`` 转成 503。原先这一组把"数据库暂不可用"
那句话抄了六遍，文案还与认证、书架两处的略有不同。

为什么这一组不降级成空列表
--------------------------------------------------------------------------
``/api/admin/users`` 是**没有 ``available`` 字段**的裸列表，库读不到时返回 200
加空列表，管理员看到的是"一个用户都没有"——那比报错危险得多，他会以为数据没了。
降级只放在响应能说清"我读不到"的地方（回响、画像），见 ``routers/history.py``。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..deps import require_admin
from ..errors import ADMIN_DB
from ..formatting import iso_time
from ..schemas.admin import (
    AuditRow,
    OverviewResponse,
    PublicBookRow,
    ResetPasswordRequest,
    ReviewRequest,
    ReviewRow,
    TableColumn,
    TableDetailResponse,
    TableInfo,
    UpdateUserRequest,
    UserRow,
)
from ..schemas.common import MessageResponse, OkResponse, RowMutationResponse
from ..services.admin import get_admin_store
from ..services.auth import User, get_auth_store
from ..services.content_loader import get_loader
from ..services.user_books import get_user_book_store

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses=ADMIN_DB,
)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _user_row(user: User, *, shelf_books: int = 0) -> UserRow:
    return UserRow(
        id=user.id,
        email=user.email,
        name=user.name,
        display_name=user.display_name,
        is_admin=user.is_admin,
        created_at=iso_time(user.created_ts) or "",
        shelf_books=shelf_books,
    )


def _review_row(book, user_email: str) -> ReviewRow:
    return ReviewRow(
        id=book.id,
        user_id=book.user_id,
        user_email=user_email,
        title=book.title,
        author=book.author,
        year=book.year,
        cover_url=book.cover_url,
        summary=book.summary,
        subjects=list(book.subjects),
        guide=book.guide,
        has_guide=book.has_guide,
        visibility=book.visibility,
        review_note=book.review_note,
        created_at=iso_time(book.created_ts) or "",
    )


# ── 总览 ────────────────────────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewResponse)
def overview(admin: User = Depends(require_admin)):
    """数据总览：用户、书库、问答、待审、语料规模。

    "今日" 按本机时区的 0 点算——管理员看的是自己这台机器的日历。
    """
    store = get_admin_store()
    data = store.overview()

    loader = get_loader()
    books = loader.get_books()
    data.update({
        "corpus_books": len(books),
        "corpus_chapters": sum(len(b.chapters) for b in books),
        "corpus_categories": loader.categories(),
        "db_path": store.db_path,
        "server_time": iso_time(time.time()) or "",
    })
    return OverviewResponse(**data)


# ── 用户管理 ────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserRow])
def list_users(admin: User = Depends(require_admin)):
    """所有用户，附带各自的藏书数。

    ***原先这个接口在库不可用时会 500***：``auth.list_users()`` 不吞
    ``DatabaseUnavailable``，而它当时写在 try 之外——只有取藏书数那一步被包住。
    现在整条路径都交给全局出口，库挂了就是干净的 503。
    """
    auth = get_auth_store()
    shelf = get_user_book_store()
    return [
        _user_row(user, shelf_books=shelf.counts_for_user(user.id).get("total", 0))
        for user in auth.list_users()
    ]


@router.patch("/users/{user_id}", response_model=UserRow)
def update_user(user_id: int, payload: UpdateUserRequest, admin: User = Depends(require_admin)):
    """授予或取消管理员。

    **不允许取消自己**：那会让最后一个管理员把自己锁在门外，而这个系统没有
    命令行工具能把他放回来。
    """
    if user_id == admin.id and not payload.is_admin:
        raise HTTPException(
            status_code=400,
            detail={"code": "self_demote", "message": "不能取消自己的管理员权限"},
        )
    auth = get_auth_store()
    if not auth.set_admin(user_id, payload.is_admin):
        raise _not_found("user_not_found", "用户不存在")

    get_admin_store().audit(
        user_id=admin.id, action="set_admin",
        target=f"user:{user_id}", detail=f"is_admin={payload.is_admin}",
    )
    return _user_row(auth.get_user(user_id))


@router.post("/users/{user_id}/password", response_model=MessageResponse)
def reset_password(
    user_id: int, payload: ResetPasswordRequest, admin: User = Depends(require_admin)
):
    """重置某人的密码。会同时踢掉他的所有会话。"""
    auth = get_auth_store()
    if auth.get_user(user_id) is None:
        raise _not_found("user_not_found", "用户不存在")
    auth.update_password(user_id, payload.new_password)
    get_admin_store().audit(
        user_id=admin.id, action="reset_password", target=f"user:{user_id}"
    )
    return MessageResponse(message="密码已重置，该用户需要重新登录")


@router.delete("/users/{user_id}", response_model=OkResponse)
def delete_user(user_id: int, admin: User = Depends(require_admin)):
    """删除用户（连带他的会话与私人书架）。"""
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail={"code": "self_delete", "message": "不能删除自己"},
        )
    if not get_auth_store().delete_user(user_id):
        raise _not_found("user_not_found", "用户不存在")
    get_admin_store().audit(user_id=admin.id, action="delete_user", target=f"user:{user_id}")
    return OkResponse()


# ── 新书审核 ────────────────────────────────────────────────────────────────


@router.get("/review", response_model=list[ReviewRow])
def review_queue(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
):
    """待审队列：用户申请公开的书。先进先出。"""
    _, books = get_user_book_store().list_pending(limit=limit, offset=offset)
    auth = get_auth_store()
    emails: dict[int, str] = {}
    for book in books:
        if book.user_id not in emails:
            owner = auth.get_user(book.user_id)
            emails[book.user_id] = owner.email if owner else f"#{book.user_id}"
    return [_review_row(book, emails[book.user_id]) for book in books]


@router.post("/review/{book_id}", response_model=ReviewRow)
def review_book(book_id: int, payload: ReviewRequest, admin: User = Depends(require_admin)):
    """批准（写进公共书架）或驳回（记下原因）。

    批准之后这本书立刻参与全库检索——不需要重启，检索层每次查询都会重新
    装配用户与公共贡献书的那部分文档。
    """
    book = get_user_book_store().review(
        book_id, approve=payload.approve, note=payload.note, category=payload.category
    )
    if book is None:
        raise _not_found("book_not_found", "没有这本书")
    get_admin_store().audit(
        user_id=admin.id,
        action="approve_book" if payload.approve else "reject_book",
        target=f"user_book:{book_id}",
        detail=payload.note,
    )
    owner = get_auth_store().get_user(book.user_id)
    return _review_row(book, owner.email if owner else f"#{book.user_id}")


@router.get("/public", response_model=list[PublicBookRow])
def list_public_books(admin: User = Depends(require_admin)):
    """公共书架里由用户贡献的书。"""
    return [
        PublicBookRow(
            id=b.id,
            book_id=b.book_id,
            title=b.title,
            author=b.author,
            category=b.category,
            from_user_id=b.from_user_id,
            created_at=iso_time(b.created_ts) or "",
        )
        for b in get_user_book_store().public_books()
    ]


@router.delete("/public/{public_id}", response_model=OkResponse)
def remove_public(public_id: int, admin: User = Depends(require_admin)):
    """从公共书架撤下一本贡献书。原作者的可见性跟着退回 private。"""
    if not get_user_book_store().remove_public(public_id):
        raise _not_found("public_book_not_found", "没有这条贡献记录")
    get_admin_store().audit(
        user_id=admin.id, action="remove_public", target=f"public_book:{public_id}"
    )
    return OkResponse()


# ── 直接操作数据库 ──────────────────────────────────────────────────────────


def _audit_row_change(admin: User, action: str, table: str, rowid: Any, values: dict) -> None:
    """记一笔改动。``values`` 只摘前 8 个键——审计行不该比被改的数据还长。"""
    get_admin_store().audit(
        user_id=admin.id, action=action, target=f"{table}#{rowid}",
        detail=", ".join(f"{k}={v!r}" for k, v in list(values.items())[:8]),
    )


@router.get("/db/tables", response_model=list[TableInfo])
def list_tables(admin: User = Depends(require_admin)):
    """所有可操作的表及行数。"""
    return [TableInfo(**item) for item in get_admin_store().list_tables()]


@router.get("/db/tables/{table}", response_model=TableDetailResponse)
def read_table(
    table: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
):
    """看一张表的结构与数据（分页）。"""
    store = get_admin_store()
    columns = store.describe_table(table)
    total, rows = store.read_rows(table, limit=limit, offset=offset)
    return TableDetailResponse(
        table=table,
        columns=[TableColumn(**column) for column in columns],
        total=total,
        rows=rows,
    )


@router.patch("/db/tables/{table}/rows/{rowid}", response_model=OkResponse)
def update_row(
    table: str,
    rowid: int,
    values: dict[str, Any] = Body(..., description="列名 → 新值"),
    admin: User = Depends(require_admin),
):
    """改一行。列名与保护列都会被校验。"""
    store = get_admin_store()
    if not store.update_row(table, rowid, values):
        raise _not_found("row_not_found", "没有这一行")
    _audit_row_change(admin, "update_row", table, rowid, values)
    return OkResponse()


@router.post("/db/tables/{table}/rows", response_model=RowMutationResponse, status_code=201)
def insert_row(
    table: str,
    values: dict[str, Any] = Body(..., description="列名 → 值"),
    admin: User = Depends(require_admin),
):
    """插一行。``users`` 表不开放（密码哈希得由认证模块算）。"""
    store = get_admin_store()
    rowid = store.insert_row(table, values)
    _audit_row_change(admin, "insert_row", table, rowid, values)
    return RowMutationResponse(rowid=rowid)


@router.delete("/db/tables/{table}/rows/{rowid}", response_model=OkResponse)
def delete_row(table: str, rowid: int, admin: User = Depends(require_admin)):
    """删一行。"""
    store = get_admin_store()
    if not store.delete_row(table, rowid):
        raise _not_found("row_not_found", "没有这一行")
    store.audit(user_id=admin.id, action="delete_row", target=f"{table}#{rowid}")
    return OkResponse()


@router.get("/audit", response_model=list[AuditRow])
def recent_audit(
    limit: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_admin),
):
    """最近的后台操作痕迹。"""
    return [
        AuditRow(
            id=row.get("id"),
            user_id=row.get("user_id"),
            action=row.get("action"),
            target=row.get("target"),
            detail=row.get("detail"),
            created_at=iso_time(row.get("created_ts")) or "",
        )
        for row in get_admin_store().recent_audit(limit)
    ]
