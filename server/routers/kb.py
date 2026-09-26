"""知识库 API 路由：薄 HTTP 层，只做参数校验与响应建模。

业务在 ``services/kb/service.py``；这里一个规则都不写。

坐标不在这里算——图的布局是**渲染**问题，交给前端。后端只回答
"有哪些节点、哪些边、谁连谁"。这样同一份图既能画成力导向图，
也能在别的场合画成矩阵或列表。

「知识库」要登录（它在前端路由表 `RequireAuth` 那一组里）。
这一组原本**完全没有鉴权**——不是"可选登录"，是彻底敞开，收紧了才算对齐。
理由与做法见 `deps.py`。

图谱从语料文件构建、不碰数据库，所以错误声明里没有 503。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_user
from ..errors import LOGGED_IN
from ..schemas.kb import (
    CrossRefModel,
    GraphResponse,
    KbEdgeModel,
    KbLinkModel,
    KbNodeModel,
    NodeDetailResponse,
    ThemeRowModel,
)
from ..services.kb import SEARCH_LIMIT, Graph, get_kb

router = APIRouter(
    prefix="/api/kb",
    tags=["knowledge base"],
    dependencies=[Depends(require_user)],
    responses=LOGGED_IN,
)


def _missing_node(node_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "node_not_found", "message": f"节点不存在: {node_id}"},
    )


def _to_node(node) -> KbNodeModel:
    return KbNodeModel(
        id=node.node_id,
        kind=node.kind,
        label=node.label,
        degree=node.degree,
        meta=dict(node.meta),
    )


def _to_link(link) -> KbLinkModel:
    return KbLinkModel(
        node_id=link.node_id,
        label=link.label,
        kind=link.kind,
        edge_label=link.edge_label,
        direction=link.direction,
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
        raise _missing_node(node_id)
    return NodeDetailResponse(
        node=_to_node(detail.node),
        outgoing=[_to_link(l) for l in detail.outgoing],
        backlinks=[_to_link(l) for l in detail.backlinks],
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
        raise _missing_node(node_id)
    return _to_graph(graph)


@router.get("/search", response_model=list[KbNodeModel])
async def search_nodes(
    q: str = Query("", description="书名或主题名；留空则返回关联最多的若干节点"),
    limit: int = Query(SEARCH_LIMIT, ge=1, le=100),
):
    """按名字找节点。"""
    return [_to_node(n) for n in get_kb().search(q, limit=limit)]
