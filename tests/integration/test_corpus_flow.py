"""集成测试：语料层的完整性 + 新书目的端到端可用性。

覆盖三个用户可见能力：
1. 看书籍内容  —— 每本书都能列出章节并读到正文
2. 智能体问答  —— 能检索到新语料（史记 / 资治通鉴 / 贞观政要等）
3. 感悟模块    —— 感悟与书目、主题的关联一致
"""

import pytest

from server.services.content_loader import NOTES, BOOK_REGISTRY

#: 本次扩充的书目（历史文献 + 补齐原典的六本）
NEW_BOOK_IDS = ["07", "08", "09", "10", "11", "12", "13", "14", "15"]
HISTORY_BOOK_IDS = ["13", "14", "15"]


class TestEveryBookIsReadable:
    """逐本遍历注册表：这是防止"登记了却打不开"的核心保护。"""

    def test_all_books_listed_by_api(self, client):
        listed = {b["book_id"] for b in client.get("/api/books").json()}
        assert listed == {spec.book_id for spec in BOOK_REGISTRY}

    def test_every_book_can_be_opened(self, client):
        for spec in BOOK_REGISTRY:
            detail = client.get(f"/api/books/{spec.book_id}")
            assert detail.status_code == 200, spec.title
            assert detail.json()["chapter_count"] > 0, f"{spec.title} 无章节"

    def test_every_book_has_readable_first_chapter(self, client):
        for spec in BOOK_REGISTRY:
            chapters = client.get(f"/api/books/{spec.book_id}/chapters").json()
            first = chapters[0]
            body = client.get(
                f"/api/books/{spec.book_id}/chapters/{first['chapter_id']}"
            ).json()
            assert body["title"] == first["title"]
            assert len(body["content"]) > 50, f"{spec.title} 首章内容过短"


class TestNewBooksAvailable:
    @pytest.mark.parametrize("book_id", NEW_BOOK_IDS)
    def test_new_book_has_chapters(self, client, book_id):
        chapters = client.get(f"/api/books/{book_id}/chapters").json()
        assert len(chapters) >= 3
        assert all(c["book_id"] == book_id for c in chapters)

    def test_history_category_books_are_registered(self, client):
        by_id = {b["book_id"]: b for b in client.get("/api/books").json()}
        for book_id in HISTORY_BOOK_IDS:
            assert by_id[book_id]["category"] == "历史文献"

    def test_reading_a_history_book_chapter(self, client):
        chapters = client.get("/api/books/13/chapters").json()
        by_title = {c["title"]: c["chapter_id"] for c in chapters}

        meta_id = next(cid for title, cid in by_title.items() if "元信息" in title)
        assert "司马迁" in client.get(f"/api/books/13/chapters/{meta_id}").json()["content"]

        highlights_id = next(cid for title, cid in by_title.items() if "名篇" in title)
        assert "项羽" in client.get(f"/api/books/13/chapters/{highlights_id}").json()["content"]


class TestRetrievalReachesNewCorpus:
    """检索必须真的能命中新补的语料，否则新增内容等于没加。"""

    @pytest.mark.parametrize(
        ("query", "expected_book"),
        [
            ("才者，德之资也；德者，才之帅也", "资治通鉴"),
            ("上善若水，水善利万物而不争", "道德经"),
            ("知彼知己，百战不殆", "孙子兵法"),
            ("狡兔三窟", "战国策"),
            ("桃李不言，下自成蹊", "史记"),
            ("兼听则明，偏信则暗", "贞观政要"),
        ],
    )
    def test_search_hits_expected_book(self, client, query, expected_book):
        results = client.get("/api/search", params={"q": query, "top_k": 10}).json()["results"]
        titles = [r["book_title"] for r in results]
        assert expected_book in titles, f"{query!r} 未命中《{expected_book}》，实际：{titles}"

    def test_ask_can_cite_new_corpus(self, client):
        body = client.post("/api/ask", json={"question": "用人应该看重才能还是品德", "top_k": 8}).json()
        assert body["retrieved_count"] > 0
        assert "《" in body["answer"]

    def test_index_covers_many_books(self, client):
        """广度查询应能召回多本书，防止某本书整体漏建索引。

        注意：检索层的分词要求 ≥2 字，因此这里全部使用双字查询。
        """
        assert client.get("/api/health").json()["total_passages"] > 1000

        indexed = {
            r["book_id"]
            for q in ("天下", "君子", "不可", "知足", "用人", "进退")
            for r in client.get("/api/search", params={"q": q, "top_k": 20}).json()["results"]
        }
        assert len(indexed) >= 8, f"索引覆盖书目过少：{sorted(indexed)}"


class TestInsightConsistency:
    def test_all_insights_point_to_registered_books(self, client):
        """感悟引用的书目必须真实存在，避免出现悬空引用。"""
        known = {b["book_id"] for b in client.get("/api/books").json()}
        themes = client.get("/api/insight/themes").json()["themes"]
        for theme in themes:
            for item in client.get(f"/api/insight/by-theme/{theme}").json()["items"]:
                assert item["book_id"] in known

    def test_insights_of_notes_books_load(self, client):
        """NOTES 策略书目中，凡有感悟引用的都应能打开。"""
        notes_ids = {spec.book_id for spec in BOOK_REGISTRY if spec.loader == NOTES}
        for book_id in sorted(notes_ids):
            assert client.get(f"/api/books/{book_id}/chapters").status_code == 200
