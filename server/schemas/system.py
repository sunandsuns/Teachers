"""探活与根索引的出入参。

这两个接口**不需要登录**：部署平台拿 ``/api/health`` 判断服务起没起来，
它要是也要身份，平台就永远等不到那个 200。

原先它们返回裸 dict，在 OpenAPI 里是一片空白——而探活恰恰是外部系统唯一会
直接依赖的接口，契约最不该缺的就是它。
"""

from __future__ import annotations

from pydantic import BaseModel


class IndexProgress(BaseModel):
    """建索引的进度快照。启动画面的进度条读它。"""

    ratio: float
    stage: str


class HealthResponse(BaseModel):
    """健康检查：已加载的书目规模与索引规模。

    ``ready`` 表示检索索引是否已建好（服务可用）；``indexing`` 说的是"此刻建到
    哪一步了"，所以服务就绪之后它仍然有值——惰性构建时前端靠它显示进度。
    """

    status: str
    ready: bool
    indexing: IndexProgress
    books_loaded: int
    books_with_source: int
    total_chapters: int
    total_passages: int
    source_indexed: int
    source_skipped: list[str]
    categories: list[str]


class RootResponse(BaseModel):
    """没有前端产物时的根路径索引（开发态页面走 Vite 的 5173，这里不出现）。"""

    name: str
    version: str
    endpoints: dict[str, str]
