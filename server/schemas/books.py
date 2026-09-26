"""books 接口的出入参。

从 ``routers/books.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

class BookSummary(BaseModel):
    """书目摘要（列表用）。"""
    book_id: str
    title: str
    author: str
    category: str
    chapter_count: int
    has_source: bool


class ChapterSummary(BaseModel):
    """章节摘要（列表用）。"""
    chapter_id: str
    title: str
    book_id: str


class ChapterDetail(BaseModel):
    """章节详情（阅读用）。"""
    chapter_id: str
    title: str
    book_id: str
    content: str


class SourceResponse(BaseModel):
    """原典分块。``has_more`` 为真时前端可继续请求下一块。"""

    model_config = ConfigDict(title="SourceChunk")

    book_id: str
    title: str
    content: str
    offset: int
    limit: int
    total: int
    has_more: bool
