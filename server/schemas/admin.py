"""admin 接口的出入参。

从 ``routers/admin.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

class UserRow(BaseModel):

    model_config = ConfigDict(title="AdminUserRow")

    id: int
    email: str
    name: str
    display_name: str
    is_admin: bool
    created_at: str
    shelf_books: int = Field(0, description="这个人的藏书数")


class UpdateUserRequest(BaseModel):
    is_admin: bool


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., max_length=200)


class ReviewRow(BaseModel):
    id: int = Field(..., description="用户书架里那条记录的 id")
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


# ── 总览 ────────────────────────────────────────────────────────────────────


class OverviewResponse(BaseModel):
    """数据总览。

    前 12 个字段是库层面的统计（由 ``services/admin.py`` 出），后 5 个由路由层
    补上——语料规模是**内容层**的事，库不该知道。

    这个接口先前在 OpenAPI 里是一个空对象：调用方无从知道后台到底统计了什么。
    """

    model_config = ConfigDict(title="AdminOverview")

    users: int
    admins: int
    history: int
    history_today: int
    traits: int
    shelf_books: int
    shelf_books_today: int
    pending_review: int
    public_contributions: int
    sessions: int
    db_bytes: int
    tables: int
    corpus_books: int
    corpus_chapters: int
    corpus_categories: list[str]
    db_path: str
    server_time: str


# ── 公共书架 ────────────────────────────────────────────────────────────────


class PublicBookRow(BaseModel):
    """公共书架里由用户贡献的一本书。

    ``from_user_id`` 可以是 ``null``：管理员手动加的书没有贡献者
    （见 ``public_books`` 表的注释）。类型写成 ``int`` 会在那种行上校验失败，
    把一次正常的读取变成 500。
    """

    id: int
    book_id: str = Field(..., description="公共书号，形如 u01——u 前缀把它与内置的 01…15 区分开")
    title: str
    author: str
    category: str
    from_user_id: Optional[int] = None
    created_at: str


# ── 直接操作数据库 ──────────────────────────────────────────────────────────


class TableInfo(BaseModel):
    """一张可操作的表。"""

    model_config = ConfigDict(title="DbTable")

    name: str
    rows: int


class TableColumn(BaseModel):
    """表的一列。``protected`` 为真时后台不允许改写它。"""

    model_config = ConfigDict(title="DbColumn")

    name: str
    type: str
    notnull: bool
    pk: bool
    protected: bool


class TableDetailResponse(BaseModel):
    """一张表的结构与数据（分页）。

    ``rows`` 里是**任意列**——这是数据库浏览器，列随表变，没法也不该逐个建模。
    值可能是 ``null``（库里存的就是 NULL，与空串不是一回事）。
    """

    model_config = ConfigDict(title="DbTableData")

    table: str
    columns: list[TableColumn]
    total: int
    rows: list[dict[str, Any]]


# ── 操作痕迹 ────────────────────────────────────────────────────────────────


class AuditRow(BaseModel):
    """一条后台操作痕迹。

    ``user_id`` 可以是 ``null``：那表示系统动作，不是某个人做的
    （见 ``admin_audit`` 表的注释）。
    """

    model_config = ConfigDict(title="AuditEntry")

    id: int
    user_id: Optional[int] = None
    action: str
    target: str
    detail: str
    created_at: str
