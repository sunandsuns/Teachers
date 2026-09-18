"""知识库的数据模型：节点、边、双链、图。

只描述"知识库里存在哪些形状的东西"，不含解析与装配逻辑——
正文解析在 `parse.py`，装配与查询在 `service.py`。

设计要点
--------------------------------------------------------------------------
**节点 ID 是带类型前缀的字符串**（``book:08``、``theme:逆境``、
``chapter:08:04``），而不是裸的自增数字。这样一座图可以直接丢给前端，
不需要再维护一张 id→含义 的对照表；新增一种节点类型也不会撞号。

**边是单向记录、双向可查**。图里每条边只存一份（source→target），
但"出链"与"反向链接"是两个不同的查询——这正是双链的核心：
A 引用了 B，B 就知道自己被 A 引用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# ── 节点类型 ────────────────────────────────────────────────────────────

BOOK = "book"        # 一部经典
THEME = "theme"      # 八大主题之一
CHAPTER = "chapter"  # 某书的一章

NODE_KINDS: tuple[str, ...] = (BOOK, THEME, CHAPTER)

# ── 边类型 ──────────────────────────────────────────────────────────────

THEME_EDGE = "theme"  # 书 — 主题：这本书在这个主题下主张什么
CROSS_EDGE = "cross"  # 书 — 书：两书之间的对照关系（笔记里写明的）
PART_EDGE = "part"    # 书 — 章节：组成关系，不是引用

#: 每种边的语义说明，用于前端图例与调试输出
EDGE_KINDS: Mapping[str, str] = {
    THEME_EDGE: "主题归属",
    CROSS_EDGE: "经典互参",
    PART_EDGE: "章节构成",
}

#: 双链方向
OUT = "out"  # 出链：我从这里引出去
IN = "in"    # 反链：别人引到了我这里


def book_node_id(book_id: str) -> str:
    """书节点 ID，形如 ``book:08``。"""
    return f"{BOOK}:{book_id}"


def theme_node_id(theme: str) -> str:
    """主题节点 ID，形如 ``theme:逆境``。"""
    return f"{THEME}:{theme}"


def chapter_node_id(book_id: str, chapter_id: str) -> str:
    """章节节点 ID，形如 ``chapter:08:04``。

    章节号本身可能含冒号吗？不会——它由加载器统一生成（``00``/``01``/文件名）。
    故用 ``split(":", 2)`` 一定能还原成三段。
    """
    return f"{CHAPTER}:{book_id}:{chapter_id}"


def node_kind(node_id: str) -> str:
    """取节点类型前缀；无法识别时返回空串（不抛异常，交给调用方判断）。"""
    head = node_id.split(":", 1)[0]
    return head if head in NODE_KINDS else ""


# ── 图元素 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KbNode:
    """图上的一个节点。

    Attributes:
        node_id: 带类型前缀的稳定 ID。
        kind:    ``book`` / ``theme`` / ``chapter``。
        label:   展示名。书是书名，主题是主题名，章节是章节标题。
        degree:  关联边数（出入合计），前端据此决定字号与半径。
        meta:    类型专属信息。书→作者/类目/章数/是否有原典；
                 主题→覆盖书数；章节→所属书与章节号。

    `meta` 不参与相等比较：它是附属信息，同一个节点在不同装配轮次里
    `meta` 可能带上增量统计（如度数），拿它参与比较会让测试变得脆。
    """

    node_id: str
    kind: str
    label: str
    degree: int = 0
    meta: Mapping[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class KbEdge:
    """一条有向边。

    Attributes:
        label:  边上的说明。主题边取笔记里的"判断"句，互参边取那一整条对照。
                空串表示"有这条关系，但没留下说明"——不编造。
        weight: 强度。主题边 = 支撑证据条数（笔记表 1 条 + 每句金句 1 条），
                互参边固定 1。前端据此调节线宽。
    """

    source: str
    target: str
    kind: str
    label: str = ""
    weight: int = 1


@dataclass(frozen=True)
class KbLink:
    """站在某个节点上看出去的一条双链。

    `direction` 为 ``out`` 时 `node_id` 指的是目标节点，``in`` 时指来源节点——
    两种情况都表达"我和 `node_id` 之间有这条边"，方向由字段区分，
    这样出链与反链可以用同一个渲染分支。
    """

    node_id: str
    label: str
    kind: str
    edge_label: str = ""
    direction: str = OUT


@dataclass(frozen=True)
class Graph:
    """一张可渲染的图。节点与边都是扁平元组，前端拿去直接画。"""

    nodes: tuple[KbNode, ...] = ()
    edges: tuple[KbEdge, ...] = ()
    stats: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)


__all__ = [
    "BOOK",
    "CHAPTER",
    "CROSS_EDGE",
    "EDGE_KINDS",
    "Graph",
    "IN",
    "KbEdge",
    "KbLink",
    "KbNode",
    "NODE_KINDS",
    "OUT",
    "PART_EDGE",
    "THEME",
    "THEME_EDGE",
    "book_node_id",
    "chapter_node_id",
    "node_kind",
    "theme_node_id",
]
