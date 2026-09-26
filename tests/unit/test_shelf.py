"""个人书架：加书、列表、改状态、删除、申请公开、用户隔离。

联网检索与详情一律换成固定数据——测试绝不真的去打 OpenLibrary。
"""

from __future__ import annotations

import pytest

from server.routers import shelf as shelf_router
from server.services import book_search
from server.services.book_search import BookCandidate, SearchOutcome

PASSWORD = "goodpass123"
ALICE = "alice@example.com"
BOB = "bob@example.com"

BOOK = BookCandidate(
    title="活着",
    author="余华",
    year="2012",
    cover_url="https://covers.openlibrary.org/b/id/11973290-M.jpg",
    source_key="OL25129388W",
    source="openlibrary",
    summary="一个人和他命运之间的友情。",
    subjects=("Fiction", "China"),
)


def sign_in(client, email):
    """注册并返回该用户的 Authorization 头。

    用 header 而不是 cookie：一个 TestClient 只有一个 cookie jar，测用户隔离时
    两个身份会互相覆盖。
    """
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    token = client.cookies.get("rsds_session")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def offline(monkeypatch):
    """把联网检索与详情换成固定数据。"""
    monkeypatch.setattr(
        book_search, "search_books", lambda title="", author="", **kw: SearchOutcome((BOOK,))
    )
    monkeypatch.setattr(book_search, "fetch_detail", lambda key, **kw: None)


def add(client, headers, **overrides):
    payload = {
        "title": BOOK.title,
        "author": BOOK.author,
        "year": BOOK.year,
        "cover_url": BOOK.cover_url,
        "source_key": BOOK.source_key,
        "source": BOOK.source,
        "summary": BOOK.summary,
        "subjects": list(BOOK.subjects),
    }
    payload.update(overrides)
    return client.post("/api/shelf/books", json=payload, headers=headers)


class TestAuthRequired:
    """书架是私人功能，未登录一律 401。"""

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/shelf"),
        ("post", "/api/shelf/search"),
        ("get", "/api/shelf/books/1"),
        ("delete", "/api/shelf/books/1"),
        ("post", "/api/shelf/books/1/submit"),
    ])
    def test_requires_login(self, anon_client, method, path):
        # 用**不带身份**的客户端。默认那个 `client` 是已登录的，拿它来断言 401
        # 只会得到"一个登录用户也能看到自己的书架"——什么也没证明。
        # 只有 post 需要 body；get/delete 不接受 json 参数
        kwargs = {"json": {}} if method == "post" else {}
        resp = getattr(anon_client, method)(path, **kwargs)
        assert resp.status_code == 401


class TestSearch:
    def test_search_returns_candidates(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = client.post("/api/shelf/search", json={"title": "活着", "author": "余华"},
                           headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == ""
        assert len(body["results"]) == 1
        assert body["results"][0]["title"] == "活着"
        assert body["results"][0]["source_key"] == "OL25129388W"

    def test_search_surfaces_upstream_error(self, client, monkeypatch):
        """上游查不到时把原因带给前端，而不是假装"没有结果"。"""
        headers = sign_in(client, ALICE)
        monkeypatch.setattr(
            book_search, "search_books",
            lambda title="", author="", **kw: SearchOutcome((), "检索服务请求过于频繁，请稍后再试"),
        )
        body = client.post("/api/shelf/search", json={"title": "活着"}, headers=headers).json()
        assert body["results"] == []
        assert "频繁" in body["error"]


class TestAddBook:
    def test_add_and_list(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers)
        assert resp.status_code == 201
        book = resp.json()
        assert book["title"] == "活着"
        assert book["author"] == "余华"
        assert book["status"] == "wish"
        assert book["visibility"] == "private"
        assert book["has_guide"] is False  # 模型未配置，导读留空

        listing = client.get("/api/shelf", headers=headers).json()
        assert listing["total"] == 1
        assert listing["counts"]["wish"] == 1
        assert listing["books"][0]["id"] == book["id"]

    def test_duplicate_is_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        assert add(client, headers).status_code == 201
        resp = add(client, headers)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "duplicate"

    def test_same_book_from_different_users_is_fine(self, client, offline):
        """同一本书两个人各加一份，互不影响。"""
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        assert add(client, alice).status_code == 201
        assert add(client, bob).status_code == 201

    def test_empty_title_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers, title="   ")
        assert resp.status_code == 400

    def test_bad_status_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers, status="whatever")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "bad_status"

    def test_books_without_source_key_do_not_collide(self, client, offline):
        """没有来源标识的书（手工录入）不该因为"key 都是空串"而互相顶掉。"""
        headers = sign_in(client, ALICE)
        assert add(client, headers, title="甲书", source_key="").status_code == 201
        assert add(client, headers, title="乙书", source_key="").status_code == 201
        assert client.get("/api/shelf", headers=headers).json()["total"] == 2

    def test_guide_is_filled_in_the_background(self, client, offline, monkeypatch):
        """模型可用时，后台任务把导读补上。"""
        monkeypatch.setattr(
            shelf_router, "generate_guide", lambda c: ("## 这本书在讲什么\n\n一个普通人的一生。", "test-model")
        )
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]

        fresh = client.get(f"/api/shelf/books/{book_id}", headers=headers).json()
        assert fresh["has_guide"] is True
        assert "普通人的一生" in fresh["guide"]

    def test_guide_failure_does_not_break_add(self, client, offline, monkeypatch):
        """导读生成炸了也不该让加书失败——书已经在架上了。"""
        def boom(candidate):
            raise RuntimeError("模型炸了")

        monkeypatch.setattr(shelf_router, "generate_guide", boom)
        headers = sign_in(client, ALICE)
        resp = add(client, headers)
        assert resp.status_code == 201
        assert resp.json()["has_guide"] is False


class TestListAndUpdate:
    def test_filter_by_status(self, client, offline):
        headers = sign_in(client, ALICE)
        add(client, headers, source_key="A1", title="甲")
        add(client, headers, source_key="A2", title="乙", status="done")

        assert client.get("/api/shelf?status=done", headers=headers).json()["total"] == 1
        assert client.get("/api/shelf?status=wish", headers=headers).json()["total"] == 1
        assert client.get("/api/shelf", headers=headers).json()["total"] == 2

    def test_bad_status_filter_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        assert client.get("/api/shelf?status=nope", headers=headers).status_code == 400

    def test_update_status(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"status": "reading"},
                            headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "reading"
        assert client.get("/api/shelf", headers=headers).json()["counts"]["reading"] == 1

    def test_update_title_and_author(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}",
                            json={"title": "活着（修订版）", "author": "余华 著"}, headers=headers)
        assert resp.json()["title"] == "活着（修订版）"
        assert resp.json()["author"] == "余华 著"

    def test_empty_title_on_update_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"title": "  "}, headers=headers)
        assert resp.status_code == 400

    def test_delete(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        assert client.delete(f"/api/shelf/books/{book_id}", headers=headers).status_code == 200
        assert client.get("/api/shelf", headers=headers).json()["total"] == 0

    def test_missing_book_is_404(self, client, offline):
        headers = sign_in(client, ALICE)
        assert client.delete("/api/shelf/books/99999", headers=headers).status_code == 404
        assert client.get("/api/shelf/books/99999", headers=headers).status_code == 404


class TestReviewFlow:
    def test_submit_and_cancel(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]

        resp = client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "pending"

        resp = client.post(f"/api/shelf/books/{book_id}/cancel", headers=headers)
        assert resp.json()["visibility"] == "private"

    def test_submit_is_idempotent(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert client.post(
            f"/api/shelf/books/{book_id}/submit", headers=headers
        ).json()["visibility"] == "pending"

    def test_rejected_book_can_apply_again(self, client, offline):
        """驳回不是终局——用户应当有机会改好了再来。"""
        from server.services.user_books import get_user_book_store

        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        get_user_book_store().review(book_id, approve=False, note="内容太薄")

        assert client.get(f"/api/shelf/books/{book_id}", headers=headers).json()[
            "visibility"] == "rejected"
        resp = client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert resp.json()["visibility"] == "pending"
        assert resp.json()["review_note"] == ""


class TestIsolation:
    """用户之间的边界。"""

    def test_cannot_see_other_users_books(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        add(client, alice)
        assert client.get("/api/shelf", headers=alice).json()["total"] == 1
        assert client.get("/api/shelf", headers=bob).json()["total"] == 0

    def test_cannot_read_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.get(f"/api/shelf/books/{book_id}", headers=bob).status_code == 404

    def test_cannot_update_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"status": "done"},
                            headers=bob)
        assert resp.status_code == 404
        # 原主人的数据没被动过
        assert client.get(f"/api/shelf/books/{book_id}", headers=alice).json()["status"] == "wish"

    def test_cannot_delete_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.delete(f"/api/shelf/books/{book_id}", headers=bob).status_code == 404
        assert client.get("/api/shelf", headers=alice).json()["total"] == 1

    def test_cannot_submit_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.post(
            f"/api/shelf/books/{book_id}/submit", headers=bob
        ).status_code == 404
