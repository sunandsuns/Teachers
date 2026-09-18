"""知识库 API 路由：薄 HTTP 层，只做参数校验与响应建模。

业务在 ``services/kb/service.py``；这里一个规则都不写。

坐标不在这里算——图的布局是**渲染**问题，交给前端。后端只回答
"有哪些节点、哪些边、谁连谁"。这样同一份图既能画成力导向图，
也能在别的场合画成矩阵或列表。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.kb import SEARCH_LIMIT, Graph, get_kb

router = APIRouter(prefix="/api/kb", tags=["knowledge base"])


# ── 响应模型 ────────────────────────────────────────────────────────────

class KbNodeModel(BaseModel):
    """图上的一个节点。``meta`` 内容随 kind 变化，见服务层说明。"""

    id: str
    kind: str
    label: str
    degree: int
    meta: dict[str, Any]


class KbEdgeModel(BaseModel):
    """一条边。``label`` 为空的边表示"关系成立但没有留下说明"。"""

    source: str
    target: str
    kind: str
    label: str
    weight: int


class GraphResponse(BaseModel):
    """一张可渲染的图。"""

    nodes: list[KbNodeModel]
    edges: list[KbEdgeModel]
    stats: dict[str, Any]


class KbLinkModel(BaseModel):
    """一条双链。``direction`` 为 ``out`` 时 ``node_id`` 是目标，``in`` 时是来源。"""

    node_id: str
    label: str
    kind: str
    edge_label: str
    direction: str


class ThemeRowModel(BaseModel):
    """某书在某主题下的判断与代表章句。"""

    theme: str
    book_id: str
    book_title: str
    judgment: str
    quote: str


class CrossRefModel(BaseModel):
    """笔记里写下的一句互参原文。"""

    name: str
    detail: str


class NodeDetailResponse(BaseModel):
    """一个节点打开后的全部内容。"""

    node: KbNodeModel
    outgoing: list[KbLinkModel]
    backlinks: list[KbLinkModel]
    theme_rows: list[ThemeRowModel]
    cross_refs: list[CrossRefModel]


# ── 转换 ────────────────────────────────────────────────────────────────

def _to_node(node) -> KbNodeModel:
    return KbNodeModel(
        id=node.node_id,
        kind=node.kind,
        label=node.label,
        degree=node.degree,
        meta=dict(node.meta),
    )


def _to_graph(graph: Graph) -> GraphResponse:
    return GraphResponse(
        nodes=[_to_node(n) for n in graph.nodes],
        edges=[
            KbEdgeModel(
                source=e.source,
                target=e.target,
                kind=e.kind,
                label=e.label,
                weight=e.weight,
            )
            for e in graph.edges
        ],
        stats=dict(graph.stats),
    )


# ── 端点 ────────────────────────────────────────────────────────────────

@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    chapters: bool = Query(
        False,
        description="是否展开章节节点。352 章全铺上去会淹掉书与书之间的结构，故默认不展开",
    ),
):
    """全图：15 部书 + 8 个主题（可选含章节）。"""
    return _to_graph(get_kb().graph(chapters=chapters))


@router.get("/nodes/{node_id}", response_model=NodeDetailResponse)
async def get_node(node_id: str):
    """节点详情：出链、反向链接、主题明细与互参原文。

    这是双链的核心接口——同一份数据既回答"我引了谁"，也回答"谁引了我"。
    """
    detail = get_kb().detail(node_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")
    return NodeDetailResponse(
        node=_to_node(detail.node),
        outgoing=[
            KbLinkModel(
                node_id=l.node_id,
                label=l.label,
                kind=l.kind,
                edge_label=l.edge_label,
                direction=l.direction,
            )
            for l in detail.outgoing
        ],
        backlinks=[
            KbLinkModel(
                node_id=l.node_id,
                label=l.label,
                kind=l.kind,
                edge_label=l.edge_label,
                direction=l.direction,
            )
            for l in detail.backlinks
        ],
        theme_rows=[
            ThemeRowModel(
                theme=r.theme,
                book_id=r.book_id,
                book_title=r.book_title,
                judgment=r.judgment,
                quote=r.quote,
            )
            for r in detail.theme_rows
        ],
        cross_refs=[CrossRefModel(name=c.name, detail=c.detail) for c in detail.cross_refs],
    )


@router.get("/nodes/{node_id}/local", response_model=GraphResponse)
async def get_local_graph(
    node_id: str,
    chapters: bool = Query(True, description="焦点是书时，是否带上它自己的章节"),
):
    """局部图：焦点 + 邻居 + 与焦点直接相连的边。"""
    graph = get_kb().local(node_id, chapters=chapters)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")
    return _to_graph(graph)


@router.get("/search", response_model=list[KbNodeModel])
async def search_nodes(
    q: str = Query("", description="书名或主题名；留空则返回关联最多的若干节点"),
    limit: int = Query(SEARCH_LIMIT, ge=1, le=100),
):
    """按名字找节点。"""
    return [_to_node(n) for n in get_kb().search(q, limit=limit)]
