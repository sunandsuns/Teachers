"""search 接口的出入参。

从 ``routers/search.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

class SearchResponseItem(BaseModel):
    """单条检索结果。"""

    model_config = ConfigDict(title="SearchResultItem")

    book_id: str
    book_title: str
    chapter_id: str
    chapter_title: str
    content: str
    score: float
    source: str
    kind: str = Field(..., description="来源类型：notes 深读笔记 / source 原典全文 / shelf 我自己的书架")
    offset: int = Field(..., description="kind 为 source 时，该段在原典全文中的字符位置")


class SearchResponse(BaseModel):
    """检索响应。"""
    query: str
    total: int
    results: list[SearchResponseItem]
