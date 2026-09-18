"""知识库服务层的单元测试。

用一份**临时语料**（三本书，正文写死在本文件里）装配知识库，
好处是每条断言都能手算：节点几个、边几条、权重几，不依赖真实语料的规模。

真实语料上的表现由 ``tests/integration/test_kb_api.py`` 覆盖——
那里只断言"结构成立"（每个边的两端都在节点里、没有孤立书），
不断言具体条数，免得加一本新书就要改测试。
"""

import pytest

from server.services.content_loader import NOTES, BookSpec, ContentLoader
from server.services.insight import InsightView
from server.services.kb import KnowledgeBase, get_kb, reset_kb
from server.services.kb.model import BOOK, CHAPTER, CROSS_EDGE, IN, OUT, PART_EDGE, THEME, THEME_EDGE

# ── 临时语料 ────────────────────────────────────────────────────────────

NOTES_A = """# 甲书深度理解笔记

> 引言段，会成为一个"导言"章。

---

## 一、元信息与本书定位

| 项目 | 内容 |
| --- | --- |
| 书名 | 《甲书》 |

## 四、八大主题归纳

| 主题 | 甲书的判断 | 代表章句 |
| --- | --- | --- |
| 谋略 | 柔弱胜刚强，以退为进 | "反者道之动"（40）|
| 修心 | 致虚守静，知足知止 | "为道日损"（48）|
| 玄学 | 集合外的主题，不该进图 | "无" |

## 六、与项目内其他经典的交叉点

- **与《乙书》**：乙书的守拙与甲书的以退为进同源。
- **与《丙书》**：丙书讲势，甲书讲反。
- **与《甲书》**：自我引用，不进图但应留档。
- **与《不存在的书》**：解析不出来，要记进统计。
"""

NOTES_B = """# 乙书深度理解笔记

## 一、元信息

这本书刻意不写主题表和交叉点——用来验证"只靠金句库也能有边"。
"""

NOTES_C = """# 丙书深度理解笔记

## 一、元信息

这本书既没有主题表、也没有金句，只能被别人引用到。
"""


@pytest.fixture
def corpus(tmp_path):
    """三本书的临时语料。丙书有原典文件，甲乙两本没有。"""
    notes_dir = tmp_path / "理解笔记"
    notes_dir.mkdir()
    (notes_dir / "01-甲书.md").write_text(NOTES_A, encoding="utf-8")
    (notes_dir / "02-乙书.md").write_text(NOTES_B, encoding="utf-8")
    (notes_dir / "03-丙书.md").write_text(NOTES_C, encoding="utf-8")

    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "丙书.txt").write_text("丙书原典全文。", encoding="utf-8")

    registry = (
        BookSpec("01", "甲书", "作者甲", "哲学", NOTES, source="甲书.txt"),
        BookSpec("02", "乙书", "作者乙", "处世", NOTES),
        BookSpec("03", "丙书", "作者丙", "兵学", NOTES, source="丙书.txt"),
    )
    instance = ContentLoader(root=tmp_path, registry=registry)
    instance.load()
    return instance


@pytest.fixture
def insights():
    """三条金句。第三条挂在注册表里没有的书上，必须被丢掉。"""
    return [
        InsightView(0, "反者道之动。", "", "《甲书》·第四十章", "01", ("谋略", "进退")),
        InsightView(1, "守拙。", "", "《乙书》·一", "02", ("谋略",)),
        InsightView(2, "无中生有。", "", "《丙书》·一", "99", ("谋略",)),
    ]


@pytest.fixture
def kb(corpus, insights) -> KnowledgeBase:
    return KnowledgeBase(loader=corpus, insights=insights)


# ── 装配 ────────────────────────────────────────────────────────────────

class TestBuild:
    def test_nodes_are_books_plus_themes(self, kb):
        graph = kb.graph()
        assert graph.node_count() == 3 + 8
        assert sum(1 for n in graph.nodes if n.kind == BOOK) == 3
        assert sum(1 for n in graph.nodes if n.kind == THEME) == 8

    def test_book_node_carries_meta(self, kb):
        node = kb.node("book:01")
        assert node.label == "甲书"
        assert node.meta["author"] == "作者甲"
        assert node.meta["category"] == "哲学"
        assert node.meta["chapter_count"] == 4  # 导言 + 一 + 四 + 六
        assert node.meta["has_source"] is False

    def test_has_source_reflects_actual_file(self, kb):
        assert kb.node("book:03").meta["has_source"] is True

    def test_theme_edges_merge_two_evidence_sources(self, kb):
        """甲书—谋略：笔记表 1 条 + 金句库 1 条 = 权重 2。"""
        edges = {(e.source, e.target): e for e in kb.graph().edges}
        edge = edges[("book:01", "theme:谋略")]
        assert edge.kind == THEME_EDGE
        assert edge.weight == 2
        # 说明取第一条到达的证据：笔记表那张表先被读到
        assert edge.label == "柔弱胜刚强，以退为进"

    def test_theme_edge_from_insight_only(self, kb):
        """乙书没写主题表，它的"谋略"边完全来自金句库。"""
        edges = {(e.source, e.target): e for e in kb.graph().edges}
        assert edges[("book:02", "theme:谋略")].weight == 1
        assert edges[("book:02", "theme:谋略")].label == "守拙。"

    def test_cross_edges_are_directed(self, kb):
        edges = {(e.source, e.target) for e in kb.graph().edges}
        assert ("book:01", "book:02") in edges
        assert ("book:01", "book:03") in edges
        assert ("book:02", "book:01") not in edges

    def test_cross_edge_keeps_the_original_sentence(self, kb):
        edges = {(e.source, e.target): e for e in kb.graph().edges}
        assert edges[("book:01", "book:02")].kind == CROSS_EDGE
        assert edges[("book:01", "book:02")].label.startswith("乙书的守拙")

    def test_self_reference_never_becomes_an_edge(self, kb):
        assert all(e.source != e.target for e in kb.graph().edges)

    def test_self_reference_is_still_archived(self, kb):
        """不进图，但"这本书提到了自己"是语料事实，详情里要能看到。"""
        names = [r.name for r in kb.cross_refs("01")]
        assert "甲书" in names

    def test_unknown_theme_is_dropped_and_recorded(self, kb):
        assert [e for e in kb.graph().edges if e.target == "theme:玄学"] == []
        assert "玄学" in kb.stats()["unknown_themes"]

    def test_unresolved_reference_is_recorded_not_guessed(self, kb):
        assert "不存在的书" in kb.stats()["unresolved_refs"]
        assert len([e for e in kb.graph().edges if e.kind == CROSS_EDGE]) == 2

    def test_insight_on_unregistered_book_is_dropped(self, kb):
        """金句挂在"99"上，图里没有这本书，这条边就没有落点。"""
        assert all("book:99" not in (e.source, e.target) for e in kb.graph().edges)

    def test_stats_counts(self, kb):
        stats = kb.stats()
        assert stats["books"] == 3
        assert stats["themes"] == 8
        # 甲书 4 章（导言 + 三节）、乙书 2 章、丙书 2 章
        assert stats["chapters"] == 4 + 2 + 2
        # 甲-谋略、甲-修心（笔记表）+ 甲-进退、乙-谋略（金句库）
        assert stats["theme_edges"] == 4
        assert stats["cross_edges"] == 2
        assert stats["edges"] == 6

    def test_building_twice_is_idempotent(self, kb):
        assert kb.graph() == kb.graph()

    def test_degrees_match_incident_edge_count(self, kb):
        graph = kb.graph()
        for node in graph.nodes:
            incident = sum(
                1 for e in graph.edges if node.node_id in (e.source, e.target)
            )
            assert node.degree == incident, node.node_id

    def test_no_book_is_isolated(self, kb):
        """丙书没有任何主题表与金句，但仍被甲书引用到——图里不该有孤立的书。"""
        isolated = [n.label for n in kb.graph().nodes if n.kind == BOOK and n.degree == 0]
        assert isolated == []

    def test_empty_theme_set_yields_only_books(self, corpus, insights):
        """主题集合为空时只剩书—书互参：主题既不是节点，也不该有边指向它。"""
        kb = KnowledgeBase(loader=corpus, insights=insights, themes=())
        graph = kb.graph()
        assert graph.node_count() == 3
        assert [e.kind for e in graph.edges] == [CROSS_EDGE, CROSS_EDGE]


# ── 双链 ────────────────────────────────────────────────────────────────

class TestLinks:
    def test_outgoing_covers_both_edge_kinds(self, kb):
        targets = {link.node_id for link in kb.outgoing("book:01")}
        assert targets == {"theme:谋略", "theme:修心", "theme:进退", "book:02", "book:03"}

    def test_outgoing_marks_direction(self, kb):
        assert all(link.direction == OUT for link in kb.outgoing("book:01"))

    def test_backlinks_are_the_mirror(self, kb):
        backlinks = kb.backlinks("book:02")
        assert [l.node_id for l in backlinks] == ["book:01"]
        assert backlinks[0].direction == IN

    def test_backlinks_can_be_asymmetric(self, kb):
        """丙书只被引用、不引用别人——这正是双链要暴露的信息。"""
        assert kb.backlinks("book:03") != []
        assert kb.outgoing("book:03") == []

    def test_theme_node_lists_its_books(self, kb):
        assert {l.node_id for l in kb.backlinks("theme:谋略")} == {"book:01", "book:02"}

    def test_missing_node_has_no_links(self, kb):
        assert kb.node("book:99") is None
        assert kb.detail("book:99") is None
        assert kb.outgoing("book:99") == []
        assert kb.backlinks("book:99") == []


# ── 节点详情 ────────────────────────────────────────────────────────────

class TestDetail:
    def test_book_detail_lists_themes_it_covers(self, kb):
        """甲书的主题来自两处：笔记表给了谋略/修心，金句库另给了进退。"""
        detail = kb.detail("book:01")
        assert {r.theme for r in detail.theme_rows} == {"谋略", "修心", "进退"}
        assert detail.node.node_id == "book:01"

    def test_book_detail_keeps_judgment_and_quote(self, kb):
        row = next(r for r in kb.detail("book:01").theme_rows if r.theme == "谋略")
        assert row.judgment == "柔弱胜刚强，以退为进"
        assert row.quote == '"反者道之动"（40）'
        assert row.book_title == "甲书"

    def test_theme_row_falls_back_to_insight_when_notes_are_silent(self, kb):
        """乙书的"谋略"没有笔记判断，详情里退回金句原文与出处。"""
        row = next(r for r in kb.detail("book:02").theme_rows if r.theme == "谋略")
        assert row.judgment == "守拙。"
        assert row.quote == "《乙书》·一"

    def test_theme_detail_spans_books(self, kb):
        detail = kb.detail("theme:谋略")
        assert [r.book_title for r in detail.theme_rows] == ["甲书", "乙书"]

    def test_theme_detail_never_invents_a_row(self, kb):
        """没有任何书归属的主题，明细为空——图上有边才该有明细。"""
        assert kb.detail("theme:逆境").theme_rows == ()

    def test_theme_node_has_type_label(self, kb):
        detail = kb.detail("theme:谋略")
        assert detail.node.kind == THEME
        assert detail.node.label == "谋略"

    def test_cross_refs_are_kept_in_document_order(self, kb):
        """保持原文顺序；认不出对方是谁的那条不进列表（它进 stats）。"""
        assert [r.name for r in kb.detail("book:01").cross_refs] == [
            "乙书", "丙书", "甲书",
        ]

    def test_book_without_cross_section_has_none(self, kb):
        assert kb.detail("book:02").cross_refs == ()


# ── 局部图 ──────────────────────────────────────────────────────────────

class TestLocalGraph:
    def test_unknown_node_returns_none(self, kb):
        assert kb.local("book:99") is None

    def test_book_focus_includes_its_chapters(self, kb):
        graph = kb.local("book:01")
        chapters = [n for n in graph.nodes if n.kind == CHAPTER]
        assert len(chapters) == 4
        assert all(e.kind == PART_EDGE for e in graph.edges if e.target.startswith("chapter:"))

    def test_chapters_can_be_switched_off(self, kb):
        graph = kb.local("book:01", chapters=False)
        assert all(n.kind != CHAPTER for n in graph.nodes)

    def test_focus_node_is_included(self, kb):
        graph = kb.local("theme:谋略")
        assert "theme:谋略" in {n.node_id for n in graph.nodes}

    def test_theme_focus_does_not_drag_in_chapters(self, kb):
        """章节是"组成部分"而非邻居，别人的章节不属于这张图。"""
        graph = kb.local("theme:谋略", chapters=True)
        assert all(n.kind != CHAPTER for n in graph.nodes)

    def test_neighbour_edges_are_left_out(self, kb):
        """局部图是星形：只留与焦点相连的边，否则邻居之间两两相连会糊成一团。"""
        graph = kb.local("book:01", chapters=False)
        assert all(e.source == "book:01" or e.target == "book:01" for e in graph.edges)

    def test_local_edges_are_a_subset_of_global_edges(self, kb):
        local = kb.local("book:01")
        global_edges = set(kb.graph(chapters=True).edges)
        assert set(local.edges) <= global_edges

    def test_focus_is_reported_in_stats(self, kb):
        assert kb.local("book:01").stats["focus"] == "book:01"


# ── 章节层 ──────────────────────────────────────────────────────────────

class TestChapterLayer:
    def test_full_graph_can_include_chapters(self, kb):
        graph = kb.graph(chapters=True)
        assert graph.node_count() == 3 + 8 + 8
        assert sum(1 for e in graph.edges if e.kind == PART_EDGE) == 8

    def test_default_graph_stays_macro(self, kb):
        assert all(n.kind != CHAPTER for n in kb.graph().nodes)

    def test_chapter_node_carries_its_own_locator(self, kb):
        graph = kb.graph(chapters=True)
        chapter = next(n for n in graph.nodes if n.kind == CHAPTER and n.meta["book_id"] == "01")
        assert chapter.node_id == f"chapter:01:{chapter.meta['chapter_id']}"
        assert chapter.meta["book_title"] == "甲书"


# ── 检索 ────────────────────────────────────────────────────────────────

class TestSearch:
    def test_finds_by_label(self, kb):
        assert [n.label for n in kb.search("甲")] == ["甲书"]

    def test_finds_theme_by_name(self, kb):
        assert [n.node_id for n in kb.search("谋略")] == ["theme:谋略"]

    def test_empty_query_returns_most_connected_first(self, kb):
        ranked = kb.search("")
        assert ranked[0].label == "甲书"  # 度数最高
        assert ranked == sorted(ranked, key=lambda n: (-n.degree, n.kind, n.label))

    def test_no_match_returns_empty(self, kb):
        assert kb.search("山海经") == []

    def test_limit_is_respected(self, kb):
        assert len(kb.search("", limit=3)) == 3

    def test_whitespace_query_is_treated_as_empty(self, kb):
        assert kb.search("   ") == kb.search("")


# ── 单例 ────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_reset_clears_the_singleton(self):
        first = get_kb()
        assert first is get_kb()
        reset_kb()
        assert get_kb() is not first
        reset_kb()

    def test_singleton_uses_real_corpus(self, loader):
        """真实语料上至少要认得出一批书——这里只验"通得上"，不钉具体条数。"""
        kb = get_kb()
        try:
            graph = kb.graph()
            assert graph.node_count() >= 15 + 8
            assert kb.stats()["unresolved_refs"] == ()
        finally:
            reset_kb()
