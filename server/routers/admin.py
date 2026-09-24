"""后台管理 API。**每一个端点都需要管理员身份。**

分四块：数据总览、用户管理、新书审核、直接操作数据库。前三块是常规的
运营动作，最后一块是运维口子——它的安全边界写在 ``services/admin.py``
的模块注释里。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import require_admin
from ..services.admin import AdminError, get_admin_store
from ..services.auth import AuthError, User, get_auth_store
from ..services.content_loader import get_loader
from ..services.db import DatabaseUnavailable
from ..services.user_books import get_user_book_store

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _iso(ts: Optional[float]) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _admin_error(exc: AdminError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


# ── 总览 ────────────────────────────────────────────────────────────────


@router.get("/overview")
def overview(admin: User = Depends(require_admin)):
    """数据总览：用户、书库、问答、待审、语料规模。

    "今日" 按本机时区的 0 点算——管理员看的是自己这台机器的日历。
    """
    store = get_admin_store()
    try:
        data = store.overview()
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc

    loader = get_loader()
    books = loader.get_books()
    data.update({
        "corpus_books": len(books),
        "corpus_chapters": sum(len(b.chapters) for b in books),
        "corpus_categories": loader.categories(),
        "db_path": store.db_path,
        "server_time": _iso(time.time()),
    })
    return data


# ── 用户管理 ────────────────────────────────────────────────────────────


class UserRow(BaseModel):
    id: int
    email: str
    name: str
    display_name: str
    is_admin: bool
    created_at: str
    shelf_books: int = 0


class UpdateUserRequest(BaseModel):
    is_admin: bool


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., max_length=200)


@router.get("/users", response_model=list[UserRow])
def list_users(admin: User = Depends(require_admin)):
    """所有用户，附带各自的藏书数。"""
    auth = get_auth_store()
    shelf = get_user_book_store()
    rows = []
    for user in auth.list_users():
        try:
            _, books = shelf.list_for(user.id, limit=1)
            counts = shelf.counts_for_user(user.id)
        except DatabaseUnavailable:
            counts = {"total": 0}
        rows.append(UserRow(
            id=user.id, email=user.email, name=user.name,
            display_name=user.display_name, is_admin=user.is_admin,
            created_at=_iso(user.created_ts), shelf_books=counts.get("total", 0),
        ))
    return rows


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
        raise HTTPException(status_code=404, detail="用户不存在")

    get_admin_store().audit(
        user_id=admin.id, action="set_admin",
        target=f"user:{user_id}", detail=f"is_admin={payload.is_admin}",
    )
    user = auth.get_user(user_id)
    return UserRow(
        id=user.id, email=user.email, name=user.name, display_name=user.display_name,
        is_admin=user.is_admin, created_at=_iso(user.created_ts),
    )


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: int, payload: ResetPasswordRequest, admin: User = Depends(require_admin)
):
    """重置某人的密码。会同时踢掉他的所有会话。"""
    auth = get_auth_store()
    if auth.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        auth.update_password(user_id, payload.new_password)
    except AuthError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    get_admin_store().audit(
        user_id=admin.id, action="reset_password", target=f"user:{user_id}"
    )
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin)):
    """删除用户（连带他的会话与私人书架）。"""
    if user_id == admin.id:
        raise HTTPException(
            status_code=400, detail={"code": "self_delete", "message": "不能删除自己"}
        )
    if not get_auth_store().delete_user(user_id):
        raise HTTPException(status_code=404, detail="用户不存在")
    get_admin_store().audit(user_id=admin.id, action="delete_user", target=f"user:{user_id}")
    return {"ok": True}


# ── 新书审核 ────────────────────────────────────────────────────────────


class ReviewRow(BaseModel):
    id: int
    user_id: int
    user_email: str
    title: str
    author: str
    year: str
    cover_url: str
    summary: str
    subjects: list[str]
    guide: str
    has_guide: bool
    visibility: str
    review_note: str
    created_at: str


class ReviewRequest(BaseModel):
    approve: bool
    note: str = Field("", max_length=300)
    category: str = Field("", max_length=40, description="进公共书架时归入的分类")


@router.get("/review", response_model=list[ReviewRow])
def review_queue(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
):
    """待审队列：用户申请公开的书。先进先出。"""
    total, books = get_user_book_store().list_pending(limit=limit, offset=offset)
    auth = get_auth_store()
    emails: dict[int, str] = {}
    rows = []
    for book in books:
        if book.user_id not in emails:
            owner = auth.get_user(book.user_id)
            emails[book.user_id] = owner.email if owner else f"#{book.user_id}"
        rows.append(ReviewRow(
            id=book.id, user_id=book.user_id, user_email=emails[book.user_id],
            title=book.title, author=book.author, year=book.year,
            cover_url=book.cover_url, summary=book.summary,
            subjects=list(book.subjects), guide=book.guide,
            has_guide=book.has_guide, visibility=book.visibility,
            review_note=book.review_note, created_at=_iso(book.created_ts),
        ))
    return rows


@router.post("/review/{book_id}", response_model=ReviewRow)
def review_book(
    book_id: int, payload: ReviewRequest, admin: User = Depends(require_admin)
):
    """批准（写进公共书架）或驳回（记下原因）。

    批准之后这本书立刻参与全库检索——不需要重启，检索层每次查询都会重新
    装配用户与公共贡献书的那部分文档。
    """
    store = get_user_book_store()
    book = store.review(
        book_id, approve=payload.approve, note=payload.note, category=payload.category
    )
    if book is None:
        raise HTTPException(status_code=404, detail="没有这本书")
    get_admin_store().audit(
        user_id=admin.id,
        action="approve_book" if payload.approve else "reject_book",
        target=f"user_book:{book_id}",
        detail=payload.note,
    )
    owner = get_auth_store().get_user(book.user_id)
    return ReviewRow(
        id=book.id, user_id=book.user_id,
        user_email=owner.email if owner else f"#{book.user_id}",
        title=book.title, author=book.author, year=book.year,
        cover_url=book.cover_url, summary=book.summary, subjects=list(book.subjects),
        guide=book.guide, has_guide=book.has_guide, visibility=book.visibility,
        review_note=book.review_note, created_at=_iso(book.created_ts),
    )


@router.get("/public")
def list_public_books(admin: User = Depends(require_admin)):
    """公共书架里由用户贡献的书。"""
    books = get_user_book_store().public_books()
    return [
        {
            "id": b.id, "book_id": b.book_id, "title": b.title, "author": b.author,
            "category": b.category, "from_user_id": b.from_user_id,
            "created_at": _iso(b.created_ts),
        }
        for b in books
    ]


@router.delete("/public/{public_id}")
def remove_public(public_id: int, admin: User = Depends(require_admin)):
    """从公共书架撤下一本贡献书。原作者的可见性跟着退回 private。"""
    if not get_user_book_store().remove_public(public_id):
        raise HTTPException(status_code=404, detail="没有这条贡献记录")
    get_admin_store().audit(
        user_id=admin.id, action="remove_public", target=f"public_book:{public_id}"
    )
    return {"ok": True}


# ── 直接操作数据库 ──────────────────────────────────────────────────────


@router.get("/db/tables")
def list_tables(admin: User = Depends(require_admin)):
    """所有可操作的表及行数。"""
    try:
        return get_admin_store().list_tables()
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc


@router.get("/db/tables/{table}")
def read_table(
    table: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
):
    """看一张表的结构与数据（分页）。"""
    store = get_admin_store()
    try:
        columns = store.describe_table(table)
        total, rows = store.read_rows(table, limit=limit, offset=offset)
    except AdminError as exc:
        raise _admin_error(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    return {"table": table, "columns": columns, "total": total, "rows": rows}


@router.patch("/db/tables/{table}/rows/{rowid}")
def update_row(
    table: str,
    rowid: int,
    values: dict[str, Any] = Body(..., description="列名 → 新值"),
    admin: User = Depends(require_admin),
):
    """改一行。列名与保护列都会被校验。"""
    store = get_admin_store()
    try:
        changed = store.update_row(table, rowid, values)
    except AdminError as exc:
        raise _admin_error(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    if not changed:
        raise HTTPException(status_code=404, detail="没有这一行")
    store.audit(
        user_id=admin.id, action="update_row", target=f"{table}#{rowid}",
        detail=", ".join(f"{k}={v!r}" for k, v in list(values.items())[:8]),
    )
    return {"ok": True}


@router.post("/db/tables/{table}/rows", status_code=201)
def insert_row(
    table: str,
    values: dict[str, Any] = Body(..., description="列名 → 值"),
    admin: User = Depends(require_admin),
):
    """插一行。``users`` 表不开放（密码哈希得由认证模块算）。"""
    store = get_admin_store()
    try:
        rowid = store.insert_row(table, values)
    except AdminError as exc:
        raise _admin_error(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    store.audit(
        user_id=admin.id, action="insert_row", target=f"{table}#{rowid}",
        detail=", ".join(f"{k}={v!r}" for k, v in list(values.items())[:8]),
    )
    return {"ok": True, "rowid": rowid}


@router.delete("/db/tables/{table}/rows/{rowid}")
def delete_row(table: str, rowid: int, admin: User = Depends(require_admin)):
    """删一行。"""
    store = get_admin_store()
    try:
        deleted = store.delete_row(table, rowid)
    except AdminError as exc:
        raise _admin_error(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="没有这一行")
    store.audit(user_id=admin.id, action="delete_row", target=f"{table}#{rowid}")
    return {"ok": True}


@router.get("/audit")
def recent_audit(
    limit: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_admin),
):
    """最近的后台操作痕迹。"""
    store = get_admin_store()
    return [
        {
            "id": row.get("id"), "user_id": row.get("user_id"),
            "action": row.get("action"), "target": row.get("target"),
            "detail": row.get("detail"), "created_at": _iso(row.get("created_ts")),
        }
        for row in store.recent_audit(limit)
    ]
