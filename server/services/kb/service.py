"""知识库业务层：把语料装配成一张可以按链接导航的图。

一次装配，长期只读
--------------------------------------------------------------------------
图在第一次查询时惰性构建，之后不再变化（语料是只读的），因此对外接口
全是纯查询。构建走双重检查锁，和 ``retriever`` 用同一套写法。

图里有什么
--------------------------------------------------------------------------
**节点**：15 部书 + 8 个主题（宏观图），可选展开每章的章节节点。
**边**（三种来源，各自独立、互不冒充）：

1. ``theme`` 书—主题 —— 来自深读笔记的「八大主题归纳」表，以及金句库
   里每句金句的主题标签。两者是**独立证据**，都记在 ``weight`` 里。
2. ``cross`` 书—书 —— 来自深读笔记的「与项目内其他经典的交叉点」段。
3. ``part``  书—章节 —— 组成关系。它让"这本书由哪些章构成"也能顺着图查到，
   但它不是引用，前端据此单独着色。

为什么以书和主题为骨
--------------------------------------------------------------------------
因为语料里**真的只写了这些链接**。笔记没有在章与章之间画线，硬连出来的章节
关系图是假的。反过来，"书—主题"和"书—书"是作者明写的关系，一条也不虚。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..content_loader import Book, ContentLoader, get_loader
from ..insight import InsightView, VALID_THEMES, get_insight_service
from .model import (
    BOOK,
    CHAPTER,
    CROSS_EDGE,
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
from .parse import BookNameIndex, CrossRef, ThemeRow, parse_cross_refs, parse_theme_table

#: 默认返回的搜索结果条数
SEARCH_LIMIT = 20


@dataclass(frozen=True)
class ThemeRowView:
    """「某书在某主题下」的一条明细，用于节点详情页。

    两个方向共用同一个结构：书节点看它是"我的八个主题各自怎么说"，
    主题节点看它是"这个主题下每本书各自怎么说"。
    """

    theme: str
    book_id: str
    book_title: str
    judgment: str
    quote: str


@dataclass(frozen=True)
class NodeDetail:
    """一个节点打开后的全部内容：身份 + 双链 + 证据。"""

    node: KbNode
    outgoing: tuple[KbLink, ...] = ()
    backlinks: tuple[KbLink, ...] = ()
    theme_rows: tuple[ThemeRowView, ...] = ()
    cross_refs: tuple[CrossRef, ...] = ()

    @property
    def node_id(self) -> str:
        return self.node.node_id


# ── 内部构建器 ──────────────────────────────────────────────────────────

class _EdgeBuilder:
    """按 ``(source, target, kind)`` 归并同类边，避免同一对节点出现两条平行边。

    比如"道德经—谋略"这条边，笔记表贡献 1 条证据、金句库贡献 2 条，
    归并成一条 `weight=3` 的边比画三条重叠的线可读得多。
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, str, str], list[Any]] = {}

    def add(self, source: str, target: str, kind: str, label: str = "", weight: int = 1) -> None:
        if source == target:
            # 自环在图上只是一坨噪声，而且语料里出现过（论语那篇写了"与《论语》"）
            return
        key = (source, target, kind)
        bucket = self._data.setdefault(key, [0, ""])
        bucket[0] += weight
        if not bucket[1] and label:
            bucket[1] = label

    def freeze(self) -> list[KbEdge]:
        edges = [
            KbEdge(source=s, target=t, kind=k, label=label, weight=weight)
            for (s, t, k), (weight, label) in self._data.items()
        ]
        edges.sort(key=lambda e: (e.kind, e.source, e.target))
        return edges


# ── 服务 ────────────────────────────────────────────────────────────────

class KnowledgeBase:
    """知识库：图 + 双链查询。

    Args:
        loader:   内容加载器。测试可注入临时语料构造的实例。
        insights: 金句视图列表。默认取全局感悟服务。
        themes:   参与建图的主题集合。默认 ``VALID_THEMES``——
                  笔记里若写了集合外的主题，那条边会被丢掉并记进统计，
                  而不是悄悄混进图里。
    """

    def __init__(
        self,
        loader: Optional[ContentLoader] = None,
        insights: Optional[Sequence[InsightView]] = None,
        themes: Iterable[str] = VALID_THEMES,
    ) -> None:
        self._loader = loader if loader is not None else get_loader()
        self._insights = list(
            insights if insights is not None else get_insight_service().all()
        )
        self._themes: tuple[str, ...] = tuple(themes)

        self._lock = threading.Lock()
        self._built = False

        self._nodes: dict[str, KbNode] = {}
        self._edges: tuple[KbEdge, ...] = ()
        self._out: dict[str, list[KbLink]] = {}
        self._in: dict[str, list[KbLink]] = {}
        self._theme_rows: dict[str, dict[str, ThemeRow]] = {}
        self._theme_insights: dict[tuple[str, str], list[InsightView]] = {}
        self._cross_refs: dict[str, list[CrossRef]] = {}
        self._chapter_meta: dict[str, list[tuple[str, str]]] = {}  # book_id -> [(chapter_id, title)]
        self._stats: dict[str, Any] = {}

    # ── 构建 ────────────────────────────────────────────────────────

    def warm_up(self) -> None:
        """把建图提前做掉。

        建图本身只要十几毫秒（实测量过），但它是**惰性**的：不预热，用户第一次
        点开「知识库」就要现等这一下。应用启动时反正已经为建索引等了七秒，
        顺手把它做掉，用户点进去就是现成的。

        做成公开方法而不是让调用方去碰 ``_ensure_built``：后者是内部实现，
        改起来不该牵扯到 ``main.py``。失败也不抛——知识库建不出来不该拦住启动。
        """
        try:
            self._ensure_built()
        except Exception:  # noqa: BLE001 — 预热失败留给首次真实请求去报错
            pass

    def _ensure_built(self) -> None:
        if self._built:
            return
        with self._lock:
            if self._built:
                return
            self._build()
            self._built = True

    def _build(self) -> None:
        books = self._loader.get_books()
        index = BookNameIndex({book.book_id: book.title for book in books})
        edges = _EdgeBuilder()
        unknown_themes: set[str] = set()
        unresolved: list[str] = []

        for book in books:
            self._chapter_meta[book.book_id] = [
                (chapter.chapter_id, chapter.title) for chapter in book.chapters
            ]
            self._nodes[book_node_id(book.book_id)] = KbNode(
                node_id=book_node_id(book.book_id),
                kind=BOOK,
                label=book.title,
                meta={
                    "book_id": book.book_id,
                    "author": book.author,
                    "category": book.category,
                    "chapter_count": len(book.chapters),
                    "has_source": book.source_file is not None,
                },
            )
            self._collect_notes(book, edges, unknown_themes)
            self._collect_cross_refs(book, index, edges, unresolved)

        self._collect_theme_insights(edges)

        for theme in self._themes:
            self._nodes[theme_node_id(theme)] = KbNode(
                node_id=theme_node_id(theme),
                kind=THEME,
                label=theme,
                meta={"theme": theme},
            )

        self._edges = tuple(edges.freeze())
        self._index_links(self._edges)
        self._refresh_degrees()
        self._stats = {
            "books": len(books),
            "themes": len(self._themes),
            "chapters": sum(len(v) for v in self._chapter_meta.values()),
            "edges": len(self._edges),
            "theme_edges": sum(1 for e in self._edges if e.kind == THEME_EDGE),
            "cross_edges": sum(1 for e in self._edges if e.kind == CROSS_EDGE),
            # 「认不出的引用」与「集合外的主题」都留下名字，便于发现语料笔误
            "unresolved_refs": tuple(sorted(set(unresolved))),
            "unknown_themes": tuple(sorted(unknown_themes)),
        }

    def _collect_notes(
        self, book: Book, edges: _EdgeBuilder, unknown_themes: set[str]
    ) -> None:
        """从一本书的全部章节里找「八大主题归纳」表，生成 书—主题 边。"""
        for chapter in book.chapters:
            for row in parse_theme_table(chapter.content):
                if row.theme not in self._themes:
                    unknown_themes.add(row.theme)
                    continue
                self._theme_rows.setdefault(book.book_id, {})[row.theme] = row
                edges.add(
                    book_node_id(book.book_id),
                    theme_node_id(row.theme),
                    THEME_EDGE,
                    label=row.judgment,
                )

    def _collect_cross_refs(
        self,
        book: Book,
        index: BookNameIndex,
        edges: _EdgeBuilder,
        unresolved: list[str],
    ) -> None:
        """从「交叉点」段生成 书—书 边；认不出的名字记进统计。"""
        for chapter in book.chapters:
            for ref in parse_cross_refs(chapter.content):
                target_id = index.resolve(ref.name)
                if target_id is None:
                    unresolved.append(ref.name)
                    continue
                self._cross_refs.setdefault(book.book_id, []).append(ref)
                if target_id == book.book_id:
                    continue  # 自我引用：不进图，但仍留在 cross_refs 里可查
                edges.add(
                    book_node_id(book.book_id),
                    book_node_id(target_id),
                    CROSS_EDGE,
                    label=ref.detail,
                )

    def _collect_theme_insights(self, edges: _EdgeBuilder) -> None:
        """金句库的主题标签，是「书—主题」的第二路证据。"""
        for insight in self._insights:
            for theme in insight.themes:
                if theme not in self._themes:
                    continue
                # 金句可能挂到注册表里没有的书上：那种边没有落点，跳过
                if book_node_id(insight.book_id) not in self._nodes:
                    continue
                self._theme_insights.setdefault((insight.book_id, theme), []).append(insight)
                edges.add(
                    book_node_id(insight.book_id),
                    theme_node_id(theme),
                    THEME_EDGE,
                    label=insight.text,
                )

    def _index_links(self, edges: Sequence[KbEdge]) -> None:
        """建出链 / 反链两张邻接表。"""
        for edge in edges:
            self._out.setdefault(edge.source, []).append(
                KbLink(
                    node_id=edge.target,
                    label=self._label_of(edge.target),
                    kind=edge.kind,
                    edge_label=edge.label,
                    direction=OUT,
                )
            )
            self._in.setdefault(edge.target, []).append(
                KbLink(
                    node_id=edge.source,
                    label=self._label_of(edge.source),
                    kind=edge.kind,
                    edge_label=edge.label,
                    direction=IN,
                )
            )
        for table in (self._out, self._in):
            for links in table.values():
                # 度数高的排前面：它更可能是这张图的主干
                links.sort(key=lambda l: l.label)

    def _label_of(self, node_id: str) -> str:
        node = self._nodes.get(node_id)
        return node.label if node else node_id

    def _refresh_degrees(self) -> None:
        for node_id, node in list(self._nodes.items()):
            degree = len(self._out.get(node_id, ())) + len(self._in.get(node_id, ()))
            if degree != node.degree:
                self._nodes[node_id] = KbNode(
                    node_id=node.node_id,
                    kind=node.kind,
                    label=node.label,
                    degree=degree,
                    meta=node.meta,
                )

    # ── 图查询 ──────────────────────────────────────────────────────

    def graph(self, *, chapters: bool = False) -> Graph:
        """全图。``chapters=True`` 时把章节节点一并放进来。

        默认不含章节：15 部书共 352 章，全铺上去会把"书与书之间怎么互相照亮"
        这层结构淹掉。章节属于局部视图。
        """
        self._ensure_built()
        nodes: list[KbNode] = list(self._nodes.values())
        edges: list[KbEdge] = list(self._edges)

        if chapters:
            part_nodes, part_edges = self._chapter_layer()
            nodes.extend(part_nodes)
            edges.extend(part_edges)

        return Graph(
            nodes=tuple(nodes),
            edges=tuple(edges),
            stats={**self._stats, "chapters_shown": chapters},
        )

    def local(self, node_id: str, *, chapters: bool = True) -> Optional[Graph]:
        """以某个节点为中心的局部图（焦点 + 邻居）。

        **只保留与焦点直接相连的边**，不画邻居之间的连边。理由是这里的图
        只有 23 个宏观节点，"道德经"的 20 个邻居彼此之间几乎两两相连
        （谁都归属那 8 个主题），把那些边也画上会立刻糊成一团毛线，
        焦点反而看不见了。邻居之间的关系属于整张图的结构，想看得退回去看全图。

        章节是**组成关系**而非邻居，因此只在焦点本身是书、且 ``chapters=True``
        时并入该书自己的章节——别人的章节不属于这张图。

        节点不存在时返回 None（由路由层翻成 404）。
        """
        self._ensure_built()
        if node_id not in self._nodes:
            return None

        neighbours = {link.node_id for link in self._out.get(node_id, ())}
        neighbours.update(link.node_id for link in self._in.get(node_id, ()))
        allowed = {node_id} | neighbours

        nodes = [self._nodes[n] for n in self._nodes if n in allowed]
        edges = [e for e in self._edges if e.source == node_id or e.target == node_id]

        if chapters and node_kind(node_id) == BOOK:
            part_nodes, part_edges = self._chapter_layer(book_ids={node_id.split(":", 1)[1]})
            nodes.extend(part_nodes)
            edges.extend(part_edges)

        return Graph(
            nodes=tuple(nodes),
            edges=tuple(edges),
            stats={
                **self._stats,
                "focus": node_id,
                "chapters_shown": chapters,
                "neighbors": len(neighbours),
                "edges": len(edges),
            },
        )

    def _chapter_layer(
        self, book_ids: Optional[Iterable[str]] = None
    ) -> tuple[list[KbNode], list[KbEdge]]:
        """构造章节节点及其 ``part`` 边。``book_ids`` 给定时只展开这几本书。"""
        wanted = set(book_ids) if book_ids is not None else None
        nodes: list[KbNode] = []
        edges: list[KbEdge] = []

        for book_id, chapters in self._chapter_meta.items():
            if wanted is not None and book_id not in wanted:
                continue
            book = self._loader.get_book(book_id)
            title = book.title if book else book_id
            for chapter_id, chapter_title in chapters:
                cid = chapter_node_id(book_id, chapter_id)
                nodes.append(
                    KbNode(
                        node_id=cid,
                        kind=CHAPTER,
                        label=chapter_title,
                        degree=1,
                        meta={
                            "book_id": book_id,
                            "book_title": title,
                            "chapter_id": chapter_id,
                        },
                    )
                )
                edges.append(
                    KbEdge(
                        source=book_node_id(book_id),
                        target=cid,
                        kind=PART_EDGE,
                        label="",
                        weight=1,
                    )
                )
        return nodes, edges

    # ── 双链查询 ────────────────────────────────────────────────────

    def node(self, node_id: str) -> Optional[KbNode]:
        """按 ID 取节点；不存在返回 None。"""
        self._ensure_built()
        return self._nodes.get(node_id)

    def outgoing(self, node_id: str) -> list[KbLink]:
        """出链：这个节点指向了谁。"""
        self._ensure_built()
        return list(self._out.get(node_id, ()))

    def backlinks(self, node_id: str) -> list[KbLink]:
        """反向链接：谁指向了这个节点。

        和出链不对称是常态——《厚黑学》没写自己跟谁相通，
        但《道德经》写了它。这正是双链要暴露的信息。
        """
        self._ensure_built()
        return list(self._in.get(node_id, ()))

    def detail(self, node_id: str) -> Optional[NodeDetail]:
        """节点详情：身份 + 出链 + 反链 + 主题明细 + 互参原文。"""
        node = self.node(node_id)
        if node is None:
            return None

        theme_rows: tuple[ThemeRowView, ...] = ()
        cross_refs: tuple[CrossRef, ...] = ()

        if node.kind == BOOK:
            book_id = str(node.meta.get("book_id", ""))
            theme_rows = self._rows_for_book(book_id)
            cross_refs = tuple(self._cross_refs.get(book_id, ()))
        elif node.kind == THEME:
            theme_rows = self._rows_for_theme(str(node.meta.get("theme", "")))

        return NodeDetail(
            node=node,
            outgoing=tuple(self.outgoing(node_id)),
            backlinks=tuple(self.backlinks(node_id)),
            theme_rows=theme_rows,
            cross_refs=cross_refs,
        )

    def _rows_for_book(self, book_id: str) -> tuple[ThemeRowView, ...]:
        book = self._loader.get_book(book_id)
        title = book.title if book else book_id
        rows: list[ThemeRowView] = []
        for theme in self._themes:
            view = self._theme_row_view(book_id, theme, title)
            if view is not None:
                rows.append(view)
        return tuple(rows)

    def _rows_for_theme(self, theme: str) -> tuple[ThemeRowView, ...]:
        rows: list[ThemeRowView] = []
        for book_id in self._book_ids():
            book = self._loader.get_book(book_id)
            title = book.title if book else book_id
            view = self._theme_row_view(book_id, theme, title)
            if view is not None:
                rows.append(view)
        return tuple(rows)

    def _theme_row_view(
        self, book_id: str, theme: str, book_title: str
    ) -> Optional[ThemeRowView]:
        """合成一条主题明细：笔记表优先，没有就退回金句库。

        两者都不存在时返回 None——图上有这条边就一定有一处出处，
        这里查不到说明数据被外部改过，宁可少显示也不编。
        """
        row = self._theme_rows.get(book_id, {}).get(theme)
        quotes = self._theme_insights.get((book_id, theme), ())
        if row is None:
            if not quotes:
                return None
            first = quotes[0]
            return ThemeRowView(
                theme=theme,
                book_id=book_id,
                book_title=book_title,
                judgment=first.text,
                quote=first.source,
            )
        return ThemeRowView(
            theme=theme,
            book_id=book_id,
            book_title=book_title,
            judgment=row.judgment,
            quote=row.quote,
        )

    def _book_ids(self) -> list[str]:
        return [
            node.meta["book_id"]
            for node in self._nodes.values()
            if node.kind == BOOK
        ]

    # ── 检索 ────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[KbNode]:
        """按名字找节点（Obsidian 的 quick switcher）。

        空白查询返回度数最高的若干节点——相当于"先看看这张图的主干"。
        """
        self._ensure_built()
        needle = (query or "").strip()
        if not needle:
            return self.ranked(limit)

        lowered = needle.lower()
        hits = [
            node
            for node in self._nodes.values()
            if lowered in node.label.lower() or lowered in node.node_id.lower()
        ]
        hits.sort(key=lambda n: (-n.degree, n.label))
        return hits[:limit]

    def ranked(self, limit: int = SEARCH_LIMIT) -> list[KbNode]:
        """按度数排序的全部节点（度数相同按类型、名字稳定排序）。"""
        self._ensure_built()
        nodes = sorted(self._nodes.values(), key=lambda n: (-n.degree, n.kind, n.label))
        return nodes[:limit]

    def stats(self) -> Mapping[str, Any]:
        """构建统计。含"认不出的引用"与"未知主题"，便于暴露语料笔误。"""
        self._ensure_built()
        return dict(self._stats)

    def theme_rows(self, book_id: str) -> tuple[ThemeRowView, ...]:
        """某书的八大主题明细（供其它模块复用）。"""
        self._ensure_built()
        return self._rows_for_book(book_id)

    def cross_refs(self, book_id: str) -> tuple[CrossRef, ...]:
        """某书写下的互参原文。

        只含**解析得出对方是谁**的那些——展示层要把每一条渲染成指向另一本书的
        链接，认不出名字的条目点了没有去处。它们不会丢：``stats()`` 的
        ``unresolved_refs`` 里留着，用来暴露语料笔误。
        """
        self._ensure_built()
        return tuple(self._cross_refs.get(book_id, ()))


# ── 全局单例 ────────────────────────────────────────────────────────────

_kb: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    """获取全局知识库单例。"""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


def reset_kb() -> None:
    """丢弃全局单例（测试与热重载用）。"""
    global _kb
    _kb = None


__all__ = [
    "KnowledgeBase",
    "NodeDetail",
    "SEARCH_LIMIT",
    "ThemeRowView",
    "get_kb",
    "reset_kb",
]
