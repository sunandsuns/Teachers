"""insight 接口的出入参。

从 ``routers/insight.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

class InsightItem(BaseModel):
    """单条感悟的响应模型。"""
    id: int
    text: str
    interpretation: str
    source: str
    book_id: str
    themes: list[str]


class InsightListResponse(BaseModel):
    """感悟列表响应。"""
    total: int
    items: list[InsightItem]


class ThemeListResponse(BaseModel):
    """主题列表响应。"""
    themes: list[str]
    counts: dict[str, int]
