"""知识库 API 的集成测试：走真实语料，覆盖 HTTP 边界。

刻意**不钉死具体条数**（除了"15 部书 + 8 个主题"这个结构性事实）：
将来往语料里加一篇笔记就会多几条边，测试不该因此变红。
真正该守住的是"图自洽"——每条边的两端都在节点表里、
每本书都连得上、双链两侧能对上。
"""

import pytest

from server.services.kb import book_node_id, theme_node_id

BOOK_IDS = [f"{i:02d}" for i in range(1, 16)]
KNOWLEDGE_THEMES = ["逆境", "进退", "修心", "立志", "处世", "谋略", "谦逊", "恒心"]


@pytest.fixture
def graph(client):
    return client.get("/api/kb/graph").json()


# ── 全图 ────────────────────────────────────────────────────────────────

class TestGraphEndpoint:
    def test_has_fifteen_books_and_eight_themes(self, graph):
        kinds = [n["kind"] for n in graph["nodes"]]
        assert kinds.count("book") == 15
        assert kinds.count("theme") == 8

    def test_every_book_is_present(self, graph):
        ids = {n["id"] for n in graph["nodes"]}
        assert {book_node_id(b) for b in BOOK_IDS} <= ids

    def test_every_theme_is_present(self, graph):
        ids = {n["id"] for n in graph["nodes"]}
        assert {theme_node_id(t) for t in KNOWLEDGE_THEMES} <= ids

    def test_edge_endpoints_all_exist(self, graph):
        ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            assert edge["source"] in ids, edge
            assert edge["target"] in ids, edge

    def test_no_self_loops(self, graph):
        assert all(e["source"] != e["target"] for e in graph["edges"])

    def test_no_isolated_book(self, graph):
        """每部书都该至少与一个主题或一部书相连。出现孤岛意味着语料断链。"""
        connected = {e["source"] for e in graph["edges"]} | {e["target"] for e in graph["edges"]}
        books = [n for n in graph["nodes"] if n["kind"] == "book"]
        assert [n["label"] for n in books if n["id"] not in connected] == []

    def test_edge_kinds_are_known(self, graph):
        assert {e["kind"] for e in graph["edges"]} <= {"theme", "cross", "part"}

    def test_cross_edges_exist_between_books(self, graph):
        cross = [e for e in graph["edges"] if e["kind"] == "cross"]
        assert len(cross) >= 20
        assert all(e["label"] for e in cross), "互参边必须带着原文，不能是空说明"

    def test_theme_edges_carry_evidence(self, graph):
        theme_edges = [e for e in graph["edges"] if e["kind"] == "theme"]
        assert theme_edges
        assert all(e["weight"] >= 1 and e["label"] for e in theme_edges)

    def test_stats_report_corpus_scale(self, graph):
        stats = graph["stats"]
        assert stats["books"] == 15
        assert stats["themes"] == 8
        assert stats["chapters"] >= 300

    def test_corpus_has_no_unresolved_reference(self, graph):
        """语料里的每一处"与《X》"都该认得出来。认不出就是笔记写错了书名。"""
        # 后端返回的是元组，经 JSON 变成列表
        assert graph["stats"]["unresolved_refs"] == []

    def test_corpus_uses_only_known_themes(self, graph):
        assert graph["stats"]["unknown_themes"] == []

    def test_chapters_are_opt_in(self, graph):
        assert all(n["kind"] != "chapter" for n in graph["nodes"])

    def test_chapters_can_be_expanded(self, client):
        expanded = client.get("/api/kb/graph?chapters=true").json()
        chapters = [n for n in expanded["nodes"] if n["kind"] == "chapter"]
        assert len(chapters) >= 300
        part_edges = [e for e in expanded["edges"] if e["kind"] == "part"]
        assert len(part_edges) == len(chapters)

    def test_degrees_are_consistent_with_edges(self, graph):
        counted: dict[str, int] = {}
        for edge in graph["edges"]:
            counted[edge["source"]] = counted.get(edge["source"], 0) + 1
            counted[edge["target"]] = counted.get(edge["target"], 0) + 1
        for node in graph["nodes"]:
            assert node["degree"] == counted.get(node["id"], 0), node["id"]


# ── 节点详情（双链） ────────────────────────────────────────────────────

class TestNodeEndpoint:
    def test_book_node_has_meta_and_links(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        assert data["node"]["label"] == "道德经"
        assert data["node"]["meta"]["author"] == "老子"
        assert data["node"]["meta"]["has_source"] is True
        assert data["outgoing"] and data["backlinks"]

    def test_outgoing_and_backlinks_are_marked_with_direction(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        assert {l["direction"] for l in data["outgoing"]} == {"out"}
        assert {l["direction"] for l in data["backlinks"]} == {"in"}

    def test_backlinks_name_the_referring_books(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        referrers = {l["label"] for l in data["backlinks"]}
        # 语料里这几本都写了"与《道德经》"
        assert {"论语", "菜根谭", "贞观政要"} <= referrers

    def test_outgoing_contains_cross_refs_this_book_wrote(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        cross = {l["label"] for l in data["outgoing"] if l["kind"] == "cross"}
        assert {"易经", "厚黑学", "孙子兵法"} <= cross

    def test_book_detail_covers_all_eight_themes(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        assert {r["theme"] for r in data["theme_rows"]} == set(KNOWLEDGE_THEMES)
        assert all(r["judgment"] for r in data["theme_rows"])

    def test_book_detail_keeps_original_cross_reference_sentences(self, client):
        data = client.get("/api/kb/nodes/book:08").json()
        assert data["cross_refs"]
        assert all(r["name"] and r["detail"] for r in data["cross_refs"])

    def test_theme_node_spans_many_books(self, client):
        data = client.get("/api/kb/nodes/theme:谋略").json()
        assert data["node"]["label"] == "谋略"
        assert len(data["theme_rows"]) >= 8
        assert all(r["judgment"] for r in data["theme_rows"])

    def test_book_with_insights_only_still_lists_theme_rows(self, client):
        """《厚黑学》的笔记没写主题表，它的主题明细来自金句库。"""
        data = client.get("/api/kb/nodes/book:02").json()
        assert data["theme_rows"], "至少该有一行，否则这条边没有出处"

    def test_unknown_node_returns_404(self, client):
        assert client.get("/api/kb/nodes/book:99").status_code == 404
        assert client.get("/api/kb/nodes/nonsense").status_code == 404

    def test_theme_node_with_no_book_is_not_a_404(self, client):
        """八个主题都是合法节点，哪怕某本书不覆盖它。"""
        assert client.get("/api/kb/nodes/theme:逆境").status_code == 200


# ── 局部图 ──────────────────────────────────────────────────────────────

class TestLocalEndpoint:
    def test_focus_book_returns_star_with_chapters(self, client):
        data = client.get("/api/kb/nodes/book:08/local").json()
        focus = data["stats"]["focus"]
        assert focus == "book:08"
        assert all(
            e["source"] == focus or e["target"] == focus for e in data["edges"]
        ), "局部图只留与焦点相连的边"
        assert [n for n in data["nodes"] if n["kind"] == "chapter"]

    def test_chapters_can_be_switched_off(self, client):
        data = client.get("/api/kb/nodes/book:08/local?chapters=false").json()
        assert all(n["kind"] != "chapter" for n in data["nodes"])

    def test_theme_focus_has_no_chapters(self, client):
        data = client.get("/api/kb/nodes/theme:谋略/local").json()
        assert all(n["kind"] != "chapter" for n in data["nodes"])

    def test_local_edges_are_subset_of_full_graph(self, client):
        local = client.get("/api/kb/nodes/book:08/local").json()
        full = client.get("/api/kb/graph?chapters=true").json()
        full_edges = {(e["source"], e["target"], e["kind"]) for e in full["edges"]}
        local_edges = {(e["source"], e["target"], e["kind"]) for e in local["edges"]}
        assert local_edges <= full_edges

    def test_unknown_node_returns_404(self, client):
        assert client.get("/api/kb/nodes/book:99/local").status_code == 404


# ── 检索 ────────────────────────────────────────────────────────────────

class TestSearchEndpoint:
    def test_finds_book_by_partial_name(self, client):
        labels = [n["label"] for n in client.get("/api/kb/search?q=道德").json()]
        assert "道德经" in labels

    def test_finds_theme(self, client):
        ids = [n["id"] for n in client.get("/api/kb/search?q=谋略").json()]
        assert "theme:谋略" in ids

    def test_empty_query_returns_the_backbone(self, client):
        nodes = client.get("/api/kb/search").json()
        assert nodes
        assert nodes[0]["degree"] >= nodes[-1]["degree"]

    def test_limit_is_respected(self, client):
        assert len(client.get("/api/kb/search?limit=3").json()) == 3

    def test_no_match_returns_empty_list(self, client):
        assert client.get("/api/kb/search?q=山海经").json() == []

    def test_punctuation_only_query_is_treated_as_empty(self, client):
        """空白查询走"返回主干"的分支，不该被当成一次匹配。"""
        assert client.get("/api/kb/search?q=%20").json() != []
