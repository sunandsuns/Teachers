"""后台管理：权限边界、总览、用户管理、审核流、直接操作数据库。

数据库操作那部分测的是**安全闸门**——表名白名单、列名白名单、保护列，
以及"这些校验不过时必须拒绝，而不是把库改坏"。
"""

from __future__ import annotations

import pytest

from server.services import book_search
from server.services.book_search import BookCandidate, SearchOutcome

PASSWORD = "goodpass123"
ALICE = "alice@example.com"
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "admin-test-pw"

BOOK = BookCandidate(
    title="活着", author="余华", year="2012", source_key="OL25129388W",
    summary="一个人和他命运之间的友情。", subjects=("Fiction",),
)


def _token(client, email, password):
    client.post("/api/auth/login", json={"email": email, "password": password})
    token = client.cookies.get("rsds_session")
    client.cookies.clear()
    return token


def sign_in(client, email):
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {_token(client, email, PASSWORD)}"}


def as_admin(client):
    return {"Authorization": f"Bearer {_token(client, ADMIN_EMAIL, ADMIN_PASSWORD)}"}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        book_search, "search_books", lambda title="", author="", **kw: SearchOutcome((BOOK,))
    )
    monkeypatch.setattr(book_search, "fetch_detail", lambda key, **kw: None)


def add_book(client, headers, **overrides):
    payload = {
        "title": BOOK.title, "author": BOOK.author, "year": BOOK.year,
        "source_key": BOOK.source_key, "source": "openlibrary",
        "summary": BOOK.summary, "subjects": list(BOOK.subjects),
    }
    payload.update(overrides)
    return client.post("/api/shelf/books", json=payload, headers=headers)


def pending_book(client, offline):
    """造一本"已申请公开"的书，返回 (book_id, 作者头)。"""
    alice = sign_in(client, ALICE)
    book_id = add_book(client, alice).json()["id"]
    client.post(f"/api/shelf/books/{book_id}/submit", headers=alice)
    return book_id, alice


class TestAccessControl:
    """后台的入口必须是关着的。"""

    @pytest.mark.parametrize("path", [
        "/api/admin/overview",
        "/api/admin/users",
        "/api/admin/review",
        "/api/admin/public",
        "/api/admin/db/tables",
        "/api/admin/audit",
    ])
    def test_anonymous_is_401(self, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", [
        "/api/admin/overview",
        "/api/admin/users",
        "/api/admin/review",
        "/api/admin/public",
        "/api/admin/db/tables",
        "/api/admin/audit",
    ])
    def test_normal_user_is_403(self, client, path):
        """已登录但不是管理员 → 403（"你没权限"），而不是 401（"你去登录"）。"""
        headers = sign_in(client, ALICE)
        assert client.get(path, headers=headers).status_code == 403

    def test_normal_user_cannot_write(self, client):
        headers = sign_in(client, ALICE)
        assert client.post("/api/admin/review/1", json={"approve": True},
                           headers=headers).status_code == 403
        assert client.delete("/api/admin/db/tables/meta/rows/1",
                             headers=headers).status_code == 403


class TestOverview:
    def test_counts(self, client, offline):
        admin = as_admin(client)
        sign_in(client, ALICE)
        data = client.get("/api/admin/overview", headers=admin).json()
        assert data["users"] == 2          # alice + 内置管理员
        assert data["admins"] == 1
        assert data["shelf_books"] == 0
        assert data["corpus_books"] > 0    # 语料规模由内容层补上
        assert data["corpus_chapters"] > 0

    def test_today_counters_move(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        add_book(client, alice)
        data = client.get("/api/admin/overview", headers=admin).json()
        assert data["shelf_books"] == 1
        assert data["shelf_books_today"] == 1


class TestUserManagement:
    def test_list_users(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        add_book(client, alice)
        rows = client.get("/api/admin/users", headers=admin).json()
        by_email = {r["email"]: r for r in rows}
        assert ADMIN_EMAIL in by_email and ALICE in by_email
        assert by_email[ADMIN_EMAIL]["is_admin"] is True
        assert by_email[ALICE]["is_admin"] is False
        assert by_email[ALICE]["shelf_books"] == 1

    def test_grant_and_revoke_admin(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        alice_id = next(
            r["id"] for r in client.get("/api/admin/users", headers=admin).json()
            if r["email"] == ALICE
        )
        assert client.patch(f"/api/admin/users/{alice_id}", json={"is_admin": True},
                            headers=admin).json()["is_admin"] is True
        # 她现在是管理员了
        assert client.get("/api/admin/overview", headers=alice).status_code == 200
        assert client.patch(f"/api/admin/users/{alice_id}", json={"is_admin": False},
                            headers=admin).json()["is_admin"] is False

    def test_cannot_demote_self(self, client):
        """最后一个管理员把自己降级 = 把自己锁在门外，而这个系统没有后门。"""
        admin = as_admin(client)
        me_id = next(
            r["id"] for r in client.get("/api/admin/users", headers=admin).json()
            if r["email"] == ADMIN_EMAIL
        )
        resp = client.patch(f"/api/admin/users/{me_id}", json={"is_admin": False}, headers=admin)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "self_demote"

    def test_cannot_delete_self(self, client):
        admin = as_admin(client)
        me_id = next(
            r["id"] for r in client.get("/api/admin/users", headers=admin).json()
            if r["email"] == ADMIN_EMAIL
        )
        assert client.delete(f"/api/admin/users/{me_id}", headers=admin).status_code == 400

    def test_reset_password_kicks_sessions(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        alice_id = next(
            r["id"] for r in client.get("/api/admin/users", headers=admin).json()
            if r["email"] == ALICE
        )
        resp = client.post(f"/api/admin/users/{alice_id}/password",
                           json={"new_password": "reset-by-admin"}, headers=admin)
        assert resp.status_code == 200
        # 旧 token 立刻失效
        assert client.get("/api/auth/me", headers=alice).json()["user"] is None
        assert client.post("/api/auth/login",
                           json={"email": ALICE, "password": "reset-by-admin"}).status_code == 200

    def test_delete_user_removes_shelf(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        add_book(client, alice)
        alice_id = next(
            r["id"] for r in client.get("/api/admin/users", headers=admin).json()
            if r["email"] == ALICE
        )
        assert client.delete(f"/api/admin/users/{alice_id}", headers=admin).status_code == 200
        assert client.get("/api/admin/overview", headers=admin).json()["shelf_books"] == 0

    def test_unknown_user_is_404(self, client):
        admin = as_admin(client)
        assert client.delete("/api/admin/users/99999", headers=admin).status_code == 404
        assert client.patch("/api/admin/users/99999", json={"is_admin": True},
                            headers=admin).status_code == 404


class TestReviewFlow:
    def test_queue_only_shows_pending(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        add_book(client, alice)                       # 私有的，不该出现在队列里
        book_id = add_book(client, alice, source_key="OL2", title="许三观卖血记").json()["id"]
        client.post(f"/api/shelf/books/{book_id}/submit", headers=alice)

        queue = client.get("/api/admin/review", headers=admin).json()
        assert len(queue) == 1
        assert queue[0]["title"] == "许三观卖血记"
        assert queue[0]["user_email"] == ALICE

    def test_approve_puts_book_into_public_shelf(self, client, offline):
        admin = as_admin(client)
        book_id, _ = pending_book(client, offline)

        resp = client.post(f"/api/admin/review/{book_id}",
                           json={"approve": True, "note": "内容扎实"}, headers=admin)
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "public"

        public = client.get("/api/admin/public", headers=admin).json()
        assert len(public) == 1
        assert public[0]["title"] == "活着"
        assert public[0]["book_id"] == "u01"          # 前缀 u 与内置 01..15 分开

    def test_approve_is_idempotent(self, client, offline):
        """重复批准不该在公共书架里留下两条。"""
        admin = as_admin(client)
        book_id, _ = pending_book(client, offline)
        for _ in range(2):
            client.post(f"/api/admin/review/{book_id}", json={"approve": True}, headers=admin)
        assert len(client.get("/api/admin/public", headers=admin).json()) == 1

    def test_reject_records_note(self, client, offline):
        admin = as_admin(client)
        book_id, alice = pending_book(client, offline)
        resp = client.post(f"/api/admin/review/{book_id}",
                           json={"approve": False, "note": "简介太薄"}, headers=admin)
        assert resp.json()["visibility"] == "rejected"
        assert resp.json()["review_note"] == "简介太薄"
        # 作者自己看得到驳回原因
        mine = client.get(f"/api/shelf/books/{book_id}", headers=alice).json()
        assert mine["visibility"] == "rejected"
        assert mine["review_note"] == "简介太薄"
        assert client.get("/api/admin/public", headers=admin).json() == []

    def test_second_approval_gets_next_book_id(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        ids = []
        for i, title in enumerate(["甲", "乙"]):
            bid = add_book(client, alice, source_key=f"OL{i}", title=title).json()["id"]
            client.post(f"/api/shelf/books/{bid}/submit", headers=alice)
            client.post(f"/api/admin/review/{bid}", json={"approve": True}, headers=admin)
            ids.append(bid)
        codes = [b["book_id"] for b in client.get("/api/admin/public", headers=admin).json()]
        assert sorted(codes) == ["u01", "u02"]

    def test_remove_public_reverts_visibility(self, client, offline):
        admin = as_admin(client)
        book_id, alice = pending_book(client, offline)
        client.post(f"/api/admin/review/{book_id}", json={"approve": True}, headers=admin)
        public_id = client.get("/api/admin/public", headers=admin).json()[0]["id"]

        assert client.delete(f"/api/admin/public/{public_id}", headers=admin).status_code == 200
        assert client.get("/api/admin/public", headers=admin).json() == []
        # 作者的可见性退回 private，可以再申请
        assert client.get(f"/api/shelf/books/{book_id}",
                          headers=alice).json()["visibility"] == "private"

    def test_review_unknown_book_is_404(self, client):
        admin = as_admin(client)
        assert client.post("/api/admin/review/99999", json={"approve": True},
                           headers=admin).status_code == 404


class TestDatabaseAccess:
    def test_list_tables(self, client):
        admin = as_admin(client)
        names = {t["name"] for t in client.get("/api/admin/db/tables", headers=admin).json()}
        assert {"users", "user_books", "public_books", "history", "admin_audit"} <= names
        # sqlite 内部表不该露出来
        assert not any(n.startswith("sqlite_") for n in names)

    def test_describe_and_read(self, client):
        admin = as_admin(client)
        data = client.get("/api/admin/db/tables/users", headers=admin).json()
        assert data["table"] == "users"
        assert data["total"] == 1
        cols = {c["name"]: c for c in data["columns"]}
        assert cols["email"]["name"] == "email"
        assert cols["password_hash"]["protected"] is True
        assert cols["email"]["protected"] is False
        # 每行都带 _rowid，改/删靠它定位
        assert "_rowid" in data["rows"][0]

    def test_unknown_table_rejected(self, client):
        admin = as_admin(client)
        resp = client.get("/api/admin/db/tables/not_a_table", headers=admin)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unknown_table"

    def test_sqlite_internal_table_rejected(self, client):
        """sqlite_sequence 之类的内部表不该能被操作。"""
        admin = as_admin(client)
        assert client.get("/api/admin/db/tables/sqlite_sequence",
                          headers=admin).status_code == 400

    def test_update_row(self, client, offline):
        admin = as_admin(client)
        sign_in(client, ALICE)
        rows = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        alice_row = next(r for r in rows if r["email"] == ALICE)

        resp = client.patch(
            f"/api/admin/db/tables/users/rows/{alice_row['_rowid']}",
            json={"display_name": "爱丽丝"}, headers=admin,
        )
        assert resp.status_code == 200
        fresh = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        assert next(r for r in fresh if r["email"] == ALICE)["display_name"] == "爱丽丝"

    def test_protected_columns_rejected(self, client, offline):
        """密码哈希与 salt 不能直接改——写进去的值只会让人永远登不上。"""
        admin = as_admin(client)
        sign_in(client, ALICE)
        rows = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        rowid = next(r for r in rows if r["email"] == ALICE)["_rowid"]

        for column in ("password_hash", "salt"):
            resp = client.patch(
                f"/api/admin/db/tables/users/rows/{rowid}",
                json={column: "whatever"}, headers=admin,
            )
            assert resp.status_code == 400
            assert resp.json()["detail"]["code"] == "protected_column"

    def test_unknown_column_rejected(self, client, offline):
        admin = as_admin(client)
        sign_in(client, ALICE)
        rows = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        rowid = rows[0]["_rowid"]
        resp = client.patch(
            f"/api/admin/db/tables/users/rows/{rowid}",
            json={"no_such_column": 1}, headers=admin,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unknown_column"

    def test_empty_update_rejected(self, client, offline):
        admin = as_admin(client)
        sign_in(client, ALICE)
        rows = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        resp = client.patch(
            f"/api/admin/db/tables/users/rows/{rows[0]['_rowid']}", json={}, headers=admin
        )
        assert resp.status_code == 400

    def test_delete_row(self, client, offline):
        admin = as_admin(client)
        alice = sign_in(client, ALICE)
        add_book(client, alice)
        rows = client.get("/api/admin/db/tables/user_books", headers=admin).json()["rows"]
        assert len(rows) == 1
        resp = client.delete(
            f"/api/admin/db/tables/user_books/rows/{rows[0]['_rowid']}", headers=admin
        )
        assert resp.status_code == 200
        assert client.get("/api/admin/db/tables/user_books", headers=admin).json()["total"] == 0

    def test_delete_missing_row_is_404(self, client):
        admin = as_admin(client)
        assert client.delete("/api/admin/db/tables/meta/rows/99999",
                             headers=admin).status_code == 404

    def test_insert_row(self, client):
        admin = as_admin(client)
        resp = client.post("/api/admin/db/tables/meta/rows",
                           json={"key": "manual_note", "value": "hello"}, headers=admin)
        assert resp.status_code == 201
        rows = client.get("/api/admin/db/tables/meta", headers=admin).json()["rows"]
        assert any(r["key"] == "manual_note" for r in rows)

    def test_insert_into_users_is_blocked(self, client):
        """users 表不开放插入：密码哈希得由认证模块算出来。"""
        admin = as_admin(client)
        resp = client.post(
            "/api/admin/db/tables/users/rows",
            json={"email": "x@y.com", "password_hash": "h", "salt": "s", "created_ts": 1},
            headers=admin,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "protected_table"

    def test_paging(self, client):
        admin = as_admin(client)
        for i in range(5):
            client.post("/api/admin/db/tables/meta/rows",
                        json={"key": f"k{i}", "value": str(i)}, headers=admin)
        first = client.get("/api/admin/db/tables/meta?limit=2&offset=0", headers=admin).json()
        second = client.get("/api/admin/db/tables/meta?limit=2&offset=2", headers=admin).json()
        assert first["total"] == 5
        assert len(first["rows"]) == 2
        assert len(second["rows"]) == 2
        assert first["rows"][0]["_rowid"] != second["rows"][0]["_rowid"]


class TestAudit:
    def test_writes_are_recorded(self, client, offline):
        """直接改库这件事必须留痕：谁、什么时候、动了哪一行。"""
        admin = as_admin(client)
        sign_in(client, ALICE)
        rows = client.get("/api/admin/db/tables/users", headers=admin).json()["rows"]
        rowid = rows[0]["_rowid"]
        client.patch(f"/api/admin/db/tables/users/rows/{rowid}",
                     json={"display_name": "改过了"}, headers=admin)

        entries = client.get("/api/admin/audit", headers=admin).json()
        assert any(e["action"] == "update_row" and "users#" in (e["target"] or "")
                   for e in entries)

    def test_approval_is_recorded(self, client, offline):
        admin = as_admin(client)
        book_id, _ = pending_book(client, offline)
        client.post(f"/api/admin/review/{book_id}", json={"approve": True}, headers=admin)
        entries = client.get("/api/admin/audit", headers=admin).json()
        assert any(e["action"] == "approve_book" for e in entries)

    def test_reads_are_not_recorded(self, client):
        """读操作不记——不然审计表会被刷爆，真正要查的那几条反而淹了。"""
        admin = as_admin(client)
        client.get("/api/admin/overview", headers=admin)
        client.get("/api/admin/users", headers=admin)
        assert client.get("/api/admin/audit", headers=admin).json() == []
