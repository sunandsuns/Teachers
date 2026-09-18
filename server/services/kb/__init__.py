"""知识库模块：把 15 部书与 8 个主题装配成一张可按双链导航的图。

对外只暴露 ``KnowledgeBase`` 与视图模型；正文解析（``parse``）与
节点/边的形状（``model``）由本模块统一转出，调用方不必知道文件布局。
"""

from .model import (
    BOOK,
    CHAPTER,
    CROSS_EDGE,
    EDGE_KINDS,
    IN,
    OUT,
    PART_EDGE,
    THEME,
    THEME_EDGE,
    Graph,
    KbEdge,
    KbLink,
    KbNode,
    book_node_id,
    chapter_node_id,
    node_kind,
    theme_node_id,
)
from .parse import BOOK_ALIASES, BookNameIndex, CrossRef, ThemeRow
from .service import (
    SEARCH_LIMIT,
    KnowledgeBase,
    NodeDetail,
    ThemeRowView,
    get_kb,
    reset_kb,
)

__all__ = [
    "BOOK",
    "BOOK_ALIASES",
    "BookNameIndex",
    "CHAPTER",
    "CROSS_EDGE",
    "CrossRef",
    "EDGE_KINDS",
    "Graph",
    "IN",
    "KbEdge",
    "KbLink",
    "KbNode",
    "KnowledgeBase",
    "NodeDetail",
    "OUT",
    "PART_EDGE",
    "SEARCH_LIMIT",
    "THEME",
    "THEME_EDGE",
    "ThemeRow",
    "ThemeRowView",
    "book_node_id",
    "chapter_node_id",
    "get_kb",
    "node_kind",
    "reset_kb",
    "theme_node_id",
]
