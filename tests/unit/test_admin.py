"""后台管理：权限边界、总览、用户管理、审核流、直接操作数据库。

数据库操作那部分测的是**安全闸门**——表名白名单、列名白名单、保护列，
以及"这些校验不过时必须拒绝，而不是把库改坏"。
"""

from __future__ import annotations

import pytest

from server.services import book_search
from server.services.book_search import BookCandidate, SearchOutcome
from server.services.history import get_history_store
from server.services.profile import get_profile_store

PASSWORD = "goodpass123"
ALICE = "alice@example.com"
BOB = "bob@example.com"
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "admin-test-pw"

TRAIT = {
    "category": "性格",
    "content": "做事偏谨慎",
    "evidence": "我说我总要犹豫很久",
    "confidence": 0.7,
}

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


def identity(client, email):
    """注册并返回 ``(headers, user_id)``。

    **id 不能写死**：启动时会先建内置管理员，它占掉 id=1。拿写死的 1 去查
    详情，查到的是管理员名下那一份（空），测试会"通过"得毫无意义。所以从
    ``/api/auth/me`` 现取。
    """
    headers = sign_in(client, email)
    user_id = client.get("/api/auth/me", headers=headers).json()["user"]["id"]
    return headers, user_id


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
        "/api/admin/users/1",      # 单个用户的详情，与列表页同一道门禁
        "/api/admin/review",
        "/api/admin/public",
        "/api/admin/db/tables",
        "/api/admin/audit",
    ])
    def test_anonymous_is_401(self, anon_client, path):
        # 用不带身份的客户端。默认的 `client` 是已登录的，而且是个普通用户
        # ——拿它断言 401 只会拿到 403（"你没权限"），那是另一回事。
        assert anon_client.get(path).status_code == 401

    @pytest.mark.parametrize("path", [
        "/api/admin/overview",
        "/api/admin/users",
        "/api/admin/users/1",      # 单个用户的详情，与列表页同一道门禁
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
        # 三个：夹具预置的那个（`client` 一起来就注册的 tester@example.com）、
        # alice、以及内置管理员
        assert data["users"] == 3
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

    def test_delete_user_takes_his_questions_and_portrait_with_him(self, client, offline):
        """删人要删干净：问答与画像一起走，别在库里留没人认领的行。

        早先这里只删会话与书架。实测清一次冒烟账号，就在 ``history`` 里留下
        15 条孤儿——它们谁也读不到（自增 id 不会复用），只是白占着库，而后台
        的数据库页还看得见，像是"删了个寂寞"。

        但**匿名那一格不能顺手带走**：``user_id IS NULL`` 是访客共用的公共
        数据，不属于被删的这个人。
        """
        admin = as_admin(client)
        alice, alice_id = identity(client, ALICE)
        client.post("/api/ask", json={"question": "我最近很焦虑"}, headers=alice)
        get_profile_store().upsert([TRAIT], user_id=alice_id)
        get_history_store().save("匿名的困惑", "答", user_id=None)

        assert client.delete(f"/api/admin/users/{alice_id}", headers=admin).status_code == 200

        assert get_history_store().list(user_id=alice_id)[0] == 0
        assert get_profile_store().list(user_id=alice_id) == []
        assert get_history_store().list(user_id=None)[0] == 1

    def test_unknown_user_is_404(self, client):
        admin = as_admin(client)
        assert client.delete("/api/admin/users/99999", headers=admin).status_code == 404
        assert client.patch("/api/admin/users/99999", json={"is_admin": True},
                            headers=admin).status_code == 404


class TestUserSearch:
    """用户列表的搜索（`GET /api/admin/users?q=`）。

    背景很朴素：冒烟脚本每跑一次就注册两个账号，本地攒到 30 个之后，后台这一页
    已经需要**找**人了。筛选放在后端：数据在这边，而且先筛后算——藏书数要按人
    查一次库，把不匹配的筛掉就不必为他们各查一遍。
    """

    def _emails(self, client, headers, q):
        resp = client.get("/api/admin/users", params={"q": q}, headers=headers)
        assert resp.status_code == 200, resp.text
        return [row["email"] for row in resp.json()]

    def test_matches_email_without_caring_about_case(self, client, offline):
        admin = as_admin(client)
        identity(client, ALICE)
        identity(client, BOB)

        assert self._emails(client, admin, "bob@") == [BOB]
        assert self._emails(client, admin, "BOB@EXAMPLE.COM") == [BOB]

    def test_matches_display_name(self, client, offline):
        """昵称也要能搜——邮箱是账号，但管理员脑子里记的往往是名字。"""
        admin = as_admin(client)
        client.post("/api/auth/register", json={
            "email": ALICE, "password": PASSWORD, "display_name": "张三",
        })
        identity(client, BOB)

        hits = self._emails(client, admin, "张三")
        assert hits == [ALICE]
        assert self._emails(client, admin, "李四") == []

    def test_pure_number_matches_that_user_id(self, client, offline):
        """纯数字额外按**恰好等于**的用户 id 匹配。

        审计与数据库页都用 `user:35` 这种口径说话，管理员照着它想知道"35 是谁"
        时，不该只能去翻列表。
        """
        admin = as_admin(client)
        _, alice_id = identity(client, ALICE)

        assert ALICE in self._emails(client, admin, str(alice_id))

    def test_wildcards_are_escaped(self, client, offline):
        """`%` 不是通配符：搜索框里打一个百分号，不该等于"列出所有人"。

        转义没做的话，这条会返回全部用户，而界面上完全看不出发生过什么。
        """
        admin = as_admin(client)
        identity(client, ALICE)

        assert self._emails(client, admin, "%") == []
        assert self._emails(client, admin, "_") == []

    def test_empty_query_still_returns_everyone(self, client, offline):
        """不填搜索框 = 与从前完全一样（这个参数是**追加**的，不改变旧行为）。"""
        admin = as_admin(client)
        identity(client, ALICE)
        identity(client, BOB)

        for query in ("", "   "):
            emails = self._emails(client, admin, query)
            assert ADMIN_EMAIL in emails
            assert ALICE in emails and BOB in emails

    def test_needs_admin(self, client, offline):
        alice = sign_in(client, ALICE)
        assert client.get("/api/admin/users", params={"q": "a"},
                           headers=alice).status_code == 403


class TestUserDetail:
    """用户详情：把一个人散在四张表里的东西聚到一处，且一样都不串到别人头上。

    最后一层隐私边界在这里：管理员**可以**看所有人的数据（这正是这个页面的
    用途），但"可以看"不等于"可以看错"——把他的问答和别人的混在一起，
    管理员会据此做出完全错误的处置。
    """

    def test_gathers_questions_shelf_and_traits(self, client, offline):
        admin = as_admin(client)
        alice, alice_id = identity(client, ALICE)
        client.post("/api/ask", json={"question": "我最近很焦虑"}, headers=alice)
        add_book(client, alice)
        get_profile_store().upsert([TRAIT], user_id=alice_id)

        data = client.get(f"/api/admin/users/{alice_id}", headers=admin).json()

        assert data["user"]["email"] == ALICE
        assert data["stats"] == {
            "history": 1, "shelf_books": 1, "traits": 1, "public_books": 0,
        }
        assert [h["question"] for h in data["history"]] == ["我最近很焦虑"]
        assert [b["title"] for b in data["books"]] == [BOOK.title]
        assert [t["content"] for t in data["traits"]] == ["做事偏谨慎"]
        # 画像要带上依据：管理员看到"做事偏谨慎"，得能知道模型是凭什么判的
        assert data["traits"][0]["evidence"] == "我说我总要犹豫很久"

    def test_does_not_mix_in_another_users_records(self, client, offline):
        admin = as_admin(client)
        alice, alice_id = identity(client, ALICE)
        bob, _ = identity(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)
        client.post("/api/ask", json={"question": "乙的问题"}, headers=bob)
        add_book(client, bob)

        detail = client.get(f"/api/admin/users/{alice_id}", headers=admin).json()

        assert [h["question"] for h in detail["history"]] == ["甲的问题"]
        assert detail["stats"]["history"] == 1
        assert detail["books"] == []          # bob 那本是 bob 的

    def test_anonymous_history_is_not_attributed_to_anyone(self, client):
        """``user_id IS NULL`` 是匿名访客共用的一格，不是"所有用户"。

        把它算进某个人名下，管理员会看到一份凭空多出来的问答。（线上这一格
        是真实存在的：匿名访客也能求教，记录落在 ``user_id IS NULL``。）
        """
        admin = as_admin(client)
        _, alice_id = identity(client, ALICE)
        get_history_store().save("匿名的困惑", "答", user_id=None)

        detail = client.get(f"/api/admin/users/{alice_id}", headers=admin).json()

        assert detail["stats"]["history"] == 0
        assert detail["history"] == []

    def test_history_is_truncated_but_the_total_is_not(self, client):
        """列表截断，总数不截断——"这个人真用过"与"他最近在做什么"是两回事。"""
        admin = as_admin(client)
        alice, alice_id = identity(client, ALICE)
        for i in range(5):
            client.post("/api/ask", json={"question": f"第 {i} 问"}, headers=alice)

        data = client.get(
            f"/api/admin/users/{alice_id}?history_limit=2", headers=admin
        ).json()

        assert len(data["history"]) == 2
        assert data["stats"]["history"] == 5

    def test_newest_first(self, client):
        admin = as_admin(client)
        alice, alice_id = identity(client, ALICE)
        for i in range(3):
            client.post("/api/ask", json={"question": f"第 {i} 问"}, headers=alice)

        data = client.get(f"/api/admin/users/{alice_id}", headers=admin).json()
        assert [h["question"] for h in data["history"]] == ["第 2 问", "第 1 问", "第 0 问"]

    def test_unknown_user_is_404(self, client):
        """不存在的 id 要给 404，而不是一份"全零档案"。

        后者看到的是"这个人什么都没干过"，而真相是"没这个人"——前者会让人
        去翻库找数据，后者说明他给错了 id。
        """
        admin = as_admin(client)
        resp = client.get("/api/admin/users/99999", headers=admin)
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "user_not_found"

    def test_traits_sorted_by_confidence(self, client):
        """画像按把握排序：管理员想知道"这个人被看准了什么"，不是"最近抽到什么"。"""
        admin = as_admin(client)
        _, alice_id = identity(client, ALICE)
        get_profile_store().upsert(
            [
                {"category": "爱好", "content": "喜欢读史", "evidence": "问过历史", "confidence": 0.4},
                {"category": "性格", "content": "做事偏谨慎", "evidence": "总要犹豫", "confidence": 0.9},
            ],
            user_id=alice_id,
        )

        data = client.get(f"/api/admin/users/{alice_id}", headers=admin).json()
        assert [t["content"] for t in data["traits"]] == ["做事偏谨慎", "喜欢读史"]


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
        # tester（夹具预置的那个）+ 内置管理员
        assert data["total"] == 2
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
