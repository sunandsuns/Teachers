"""books / search / insight API 单元级测试（TestClient，覆盖路由 + 校验）。"""

from server.services.content_loader import BOOK_REGISTRY

#: 期望书目数直接对齐注册表，新增书目时无需再改测试
EXPECTED_BOOKS = len(BOOK_REGISTRY)


class TestBooksApi:
    def test_list_books(self, client):
        resp = client.get("/api/books")
        assert resp.status_code == 200
        books = resp.json()
        assert len(books) == EXPECTED_BOOKS
        ids = {b["book_id"] for b in books}
        assert {"01", "06", "12"} <= ids
        for field in ("book_id", "title", "author", "category", "chapter_count", "has_source"):
            assert field in books[0]

    def test_get_book_found(self, client):
        resp = client.get("/api/books/01")
        assert resp.status_code == 200
        assert resp.json()["title"] == "易经"

    def test_get_book_not_found(self, client):
        assert client.get("/api/books/99").status_code == 404

    def test_list_chapters(self, client):
        resp = client.get("/api/books/02/chapters")
        assert resp.status_code == 200
        chapters = resp.json()
        assert len(chapters) >= 5
        assert {"chapter_id", "title", "book_id"} <= set(chapters[0])

    def test_list_chapters_unknown_book(self, client):
        assert client.get("/api/books/99/chapters").status_code == 404

    def test_get_chapter_content(self, client):
        chapters = client.get("/api/books/02/chapters").json()
        cid = chapters[0]["chapter_id"]
        resp = client.get(f"/api/books/02/chapters/{cid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chapter_id"] == cid
        assert len(body["content"]) > 50

    def test_get_chapter_unknown(self, client):
        assert client.get("/api/books/02/chapters/zzz").status_code == 404

    def test_source_endpoint(self, client):
        resp = client.get("/api/books/02/source")
        assert resp.status_code == 200
        assert len(resp.json()["content"]) > 1000

    def test_source_not_available(self, client):
        # 毛选没有 books/ 下的原典 txt
        assert client.get("/api/books/05/source").status_code == 404


class TestSearchApi:
    def test_search_returns_results(self, client):
        resp = client.get("/api/search", params={"q": "自强不息"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] > 0
        assert all("source" in r and "score" in r for r in body["results"])

    def test_search_respects_top_k(self, client):
        resp = client.get("/api/search", params={"q": "道", "top_k": 2})
        assert resp.json()["total"] <= 2

    def test_search_requires_query(self, client):
        assert client.get("/api/search").status_code == 422

    def test_search_empty_query_rejected(self, client):
        assert client.get("/api/search", params={"q": ""}).status_code == 422


class TestInsightApi:
    def test_daily_default(self, client):
        resp = client.get("/api/insight/daily")
        assert resp.status_code == 200
        assert resp.json()["text"]

    def test_daily_specific_day(self, client):
        a = client.get("/api/insight/daily", params={"day": "2026-09-16"}).json()
        b = client.get("/api/insight/daily", params={"day": "2026-09-16"}).json()
        assert a == b

    def test_daily_bad_day_400(self, client):
        assert client.get("/api/insight/daily", params={"day": "not-a-date"}).status_code == 400

    def test_random(self, client):
        assert client.get("/api/insight/random").status_code == 200

    def test_themes(self, client):
        resp = client.get("/api/insight/themes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["themes"]) > 0
        assert all(t in body["counts"] for t in body["themes"])

    def test_by_theme(self, client):
        resp = client.get("/api/insight/by-theme/逆境")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] > 0

    def test_by_theme_unknown_404(self, client):
        assert client.get("/api/insight/by-theme/不存在").status_code == 404

    def test_by_book(self, client):
        resp = client.get("/api/insight/by-book/01")
        assert resp.status_code == 200
        assert resp.json()["total"] > 0

    def test_get_by_id(self, client):
        item = client.get("/api/insight/0")
        assert item.status_code == 200
        assert client.get("/api/insight/99999").status_code == 404


class TestSourcePagination:
    """原典分块：小书一次取完，大书按 has_more 翻页。

    《资治通鉴》321 万字，一次性返回会让浏览器卡死——这个类锁住分块契约。
    """

    def test_small_book_fits_in_one_chunk(self, client):
        body = client.get("/api/books/08/source").json()  # 道德经约 7700 字
        assert body["total"] == len(body["content"])
        assert body["offset"] == 0
        assert body["has_more"] is False

    def test_large_book_reports_more(self, client):
        body = client.get("/api/books/14/source").json()  # 资治通鉴
        assert body["total"] > 1_000_000
        assert len(body["content"]) == body["limit"]
        assert body["has_more"] is True

    def test_offset_walks_forward(self, client):
        first = client.get("/api/books/13/source").json()
        second = client.get("/api/books/13/source", params={"offset": first["limit"]}).json()
        assert second["offset"] == first["limit"]
        assert second["content"] and second["content"] != first["content"]

    def test_offset_beyond_end_returns_empty(self, client):
        body = client.get("/api/books/08/source", params={"offset": 10_000_000}).json()
        assert body["content"] == ""
        assert body["has_more"] is False

    def test_custom_limit_respected(self, client):
        body = client.get("/api/books/13/source", params={"limit": 100}).json()
        assert len(body["content"]) == 100
        assert body["limit"] == 100

    def test_source_missing_returns_404(self, client):
        assert client.get("/api/books/05/source").status_code == 404

    def test_negative_offset_rejected(self, client):
        assert client.get("/api/books/13/source", params={"offset": -1}).status_code == 422


class TestAskApi:
    """问答接口。测试环境已隔离 LLM（见 conftest.isolate_llm），因此走本地检索降级路径。"""

    def test_ask_returns_answer_and_metadata(self, client):
        body = client.post("/api/ask", json={"question": "如何面对挫折？", "top_k": 3}).json()
        assert body["question"] == "如何面对挫折？"
        assert body["answer"]
        assert body["retrieved_count"] == 3
        # 未配置密钥时模型字段应为 null，而不是谎报用了 LLM
        assert body["llm_used"] is False
        assert body["model"] is None

    def test_ask_rejects_empty_question(self, client):
        assert client.post("/api/ask", json={"question": ""}).status_code == 422

    def test_ask_rejects_top_k_out_of_range(self, client):
        assert client.post("/api/ask", json={"question": "问", "top_k": 0}).status_code == 422
        assert client.post("/api/ask", json={"question": "问", "top_k": 99}).status_code == 422

    def test_ask_status_reports_disabled(self, client):
        body = client.get("/api/ask/status").json()
        assert body["enabled"] is False
        assert body["available_models"] == 0
        assert isinstance(body["cooling_down"], list)


class TestRootAndHealth:
    def test_root_info(self, client):
        body = client.get("/").json()
        assert body["name"] == "人生导师 API"

    def test_health_counts(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["books_loaded"] == EXPECTED_BOOKS
        assert body["total_chapters"] > 100
        assert body["total_passages"] > 0
        assert "历史文献" in body["categories"]
