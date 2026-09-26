"""kb 接口的出入参。

从 ``routers/kb.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class KbNodeModel(BaseModel):
    """图上的一个节点。``meta`` 内容随 kind 变化，见服务层说明。"""

    model_config = ConfigDict(title="KbNode")

    id: str
    kind: str
    label: str
    degree: int = Field(..., description="关联边数。界面据它决定节点大小")
    meta: dict[str, Any]


class KbEdgeModel(BaseModel):
    """一条边。``label`` 为空的边表示"关系成立但没有留下说明"。"""

    model_config = ConfigDict(title="KbEdge")

    source: str
    target: str
    kind: str
    label: str = Field(..., description="边上的说明。空串表示「关系成立但没留下说明」")
    weight: int


class GraphResponse(BaseModel):
    """一张可渲染的图。"""

    model_config = ConfigDict(title="KbGraph")

    nodes: list[KbNodeModel]
    edges: list[KbEdgeModel]
    stats: dict[str, Any]


class KbLinkModel(BaseModel):
    """一条双链。``direction`` 为 ``out`` 时 ``node_id`` 是目标，``in`` 时是来源。"""

    model_config = ConfigDict(title="KbLink")

    node_id: str
    label: str
    kind: str
    edge_label: str
    direction: str


class ThemeRowModel(BaseModel):
    """某书在某主题下的判断与代表章句。"""

    model_config = ConfigDict(title="KbThemeRow")

    theme: str
    book_id: str
    book_title: str
    judgment: str
    quote: str


class CrossRefModel(BaseModel):
    """笔记里写下的一句互参原文。"""

    model_config = ConfigDict(title="KbCrossRef")

    name: str
    detail: str


class NodeDetailResponse(BaseModel):
    """一个节点打开后的全部内容。"""

    model_config = ConfigDict(title="KbNodeDetail")

    node: KbNodeModel
    outgoing: list[KbLinkModel]
    backlinks: list[KbLinkModel]
    theme_rows: list[ThemeRowModel]
    cross_refs: list[CrossRefModel]
