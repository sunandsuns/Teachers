"""shelf 接口的出入参。

从 ``routers/shelf.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class CandidateIn(BaseModel):
    """一本书的元信息。前端把用户选中的候选原样回传。"""

    model_config = ConfigDict(title="BookCandidate")

    title: str = Field(..., max_length=300)
    author: str = Field("", max_length=300)
    year: str = Field("", max_length=20)
    cover_url: str = Field("", max_length=500)
    source_key: str = Field("", max_length=100)
    source: str = Field("openlibrary", max_length=50, description="数据源标识，目前只有 openlibrary")
    summary: str = Field("", max_length=4000)
    subjects: list[str] = Field(default_factory=list, max_length=20)


class SearchRequest(BaseModel):
    title: str = Field("", max_length=300)
    author: str = Field("", max_length=300)
    limit: int = Field(6, ge=1, le=20)


class BookSearchResponse(BaseModel):
    """找书的候选结果。

    名字里带 ``Book`` 是为了与 ``search.SearchResponse``（全站检索）分开：
    两者曾同名，FastAPI 只好把其中一个导出成
    ``server__schemas__shelf__SearchResponse``，对读接口文档的人是纯粹的噪音。
    """

    results: list[CandidateIn]
    error: str = ""


class AddBookRequest(CandidateIn):

    model_config = ConfigDict(title="AddBookRequest")

    status: str = Field("wish", description="wish / reading / done")
    with_guide: bool = Field(True, description="是否让模型生成导读")


class UpdateBookRequest(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = Field(None, max_length=300)
    author: Optional[str] = Field(None, max_length=300)


class ShelfBookOut(BaseModel):

    model_config = ConfigDict(title="ShelfBook")

    id: int
    title: str
    author: str
    year: str
    cover_url: str
    source_key: str
    summary: str
    subjects: list[str]
    guide: str = Field(..., description="模型写的导读（Markdown）。加书是异步补的，刚加完可能还是空串")
    has_guide: bool = Field(..., description="导读是否已生成。为 false 时前端值得过几秒再拉一次")
    status: str
    visibility: str
    review_note: str = Field(..., description="驳回原因，只有 visibility 为 rejected 时有内容")
    created_at: str
    updated_at: str


class ShelfResponse(BaseModel):
    total: int
    counts: dict[str, int]
    books: list[ShelfBookOut]
