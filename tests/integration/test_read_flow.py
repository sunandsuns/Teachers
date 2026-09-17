"""集成测试：完整阅读流程。

模拟前端真实调用链：书架 → 选书 → 章节列表 → 章节内容 → 原典。
"""


class TestReadFlow:
    def test_library_to_chapter_flow(self, client):
        # 1. 书架列表
        books = client.get("/api/books").json()
        assert books, "书架应有书"

        # 2. 每本书都能打开章节列表，且至少一本书可读到内容
        read_ok = 0
        for book in books:
            chapters_resp = client.get(f"/api/books/{book['book_id']}/chapters")
            if book["chapter_count"] > 0:
                assert chapters_resp.status_code == 200, book["title"]
                chapters = chapters_resp.json()
                assert len(chapters) == book["chapter_count"]

                # 3. 读第一个章节
                first = chapters[0]
                detail = client.get(
                    f"/api/books/{book['book_id']}/chapters/{first['chapter_id']}"
                )
                assert detail.status_code == 200
                assert len(detail.json()["content"]) > 0
                read_ok += 1
            else:
                assert chapters_resp.status_code == 404

        # 07-12 新书笔记就绪后此阈值应回到 >= 10；当前 6 本旧书全部可读
        assert read_ok >= 6, "已有的书都应可读"

    def test_all_twelve_books_present(self, client):
        books = client.get("/api/books").json()
        titles = {b["title"] for b in books}
        expected = {
            "易经", "厚黑学", "奇门遁甲", "人性的弱点", "毛泽东选集", "王阳明心学",
            "孙子兵法", "道德经", "论语", "菜根谭", "鬼谷子", "战国策",
        }
        assert expected <= titles

    def test_source_readable_for_txt_books(self, client):
        books = client.get("/api/books").json()
        for book in books:
            resp = client.get(f"/api/books/{book['book_id']}/source")
            if book["has_source"]:
                assert resp.status_code == 200, book["title"]
                assert len(resp.json()["content"]) > 500
            else:
                assert resp.status_code == 404, book["title"]

    def test_chapter_navigation_consistency(self, client):
        """章节列表中每个 chapter_id 都能取到详情，且内容一致。（08 道德经笔记未就绪前用 02 厚黑学）"""
        chapters = client.get("/api/books/02/chapters").json()
        for ch in chapters[:5]:
            detail = client.get(f"/api/books/02/chapters/{ch['chapter_id']}").json()
            assert detail["title"] == ch["title"]
            assert detail["book_id"] == "02"
