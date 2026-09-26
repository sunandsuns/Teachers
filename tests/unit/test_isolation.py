"""按用户隔离：求教历史与画像。

为什么单独一个文件
--------------------------------------------------------------------------
这两块数据的隔离不是"顺手加的过滤"，而是一个**隐私边界**：登录之后，A 的提问、
A 的画像不该出现在 B 的界面上。它跨两个 store、六个路由、十几个方法，散在各个
文件里各测一句，很难看出边界到底有没有立住。集中在这里，一眼能看全。

两个层次都测
--------------------------------------------------------------------------
- **store 层**：直接调 ``HistoryStore`` / ``ProfileStore``。这里能覆盖路由层
  摸不到的分支（``count_since`` 的窗口、``delete_many`` 的 AND 组合、meta 键前缀）。
- **HTTP 层**：两个身份各走一遍真实请求，确认接口确实把当前用户传了下去——
  store 层再正确，路由忘了传 ``user_id`` 也等于没隔离。
"""

from __future__ import annotations

import pytest

from server.services import profile as profile_module
from server.services.history import get_history_store
from server.services.profile import get_profile_store

PASSWORD = "goodpass123"
ALICE = "alice@example.com"
BOB = "bob@example.com"


def sign_in(client, email):
    """注册并返回该用户的 Authorization 头。

    用 header 而不是 cookie：一个 TestClient 只有一个 cookie jar，两个身份
    会互相覆盖。
    """
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    token = client.cookies.get("rsds_session")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def identity(client, email):
    """注册并返回 ``(headers, user_id)``。

    **id 不能写死**：``main.lifespan`` 启动时会先建内置管理员，它占掉 id=1，
    于是 alice 是 2、bob 是 3。直接拿 1 去查画像会查到管理员名下那份（空），
    测试就会"通过"得毫无意义。所以从 ``/api/auth/me`` 现取。
    """
    headers = sign_in(client, email)
    user_id = client.get("/api/auth/me", headers=headers).json()["user"]["id"]
    return headers, user_id


# ── store 层：历史记录 ──────────────────────────────────────────────────


class TestHistoryStoreScope:
    def test_each_user_sees_only_their_own(self):
        store = get_history_store()
        store.save("甲的问题", "甲的答案", user_id=1)
        store.save("乙的问题", "乙的答案", user_id=2)

        total_a, records_a = store.list(user_id=1)
        assert total_a == 1
        assert [r.question for r in records_a] == ["甲的问题"]

    def test_anonymous_does_not_see_logged_in_records(self):
        """未登录看到的是"无归属那一份"，不是"全部"。"""
        store = get_history_store()
        store.save("登录者的问题", "答案", user_id=1)
        store.save("匿名的问题", "答案")

        total, records = store.list(user_id=None)
        assert total == 1
        assert [r.question for r in records] == ["匿名的问题"]

    def test_logged_in_does_not_see_anonymous_records(self):
        store = get_history_store()
        store.save("匿名的问题", "答案")
        assert store.list(user_id=1)[0] == 0

    def test_topics_are_scoped(self):
        """聚合要在 GROUP BY 之前过滤，否则 COUNT(*) 会把别人的记录也算进去。"""
        store = get_history_store()
        store.save("甲", "答", user_id=1, conversation_id="t1")
        store.save("乙", "答", user_id=2, conversation_id="t1")

        total_a, topics_a = store.list_topics(user_id=1)
        assert total_a == 1
        assert topics_a[0].question_count == 1

        total_b, topics_b = store.list_topics(user_id=2)
        assert total_b == 1
        assert topics_b[0].question_count == 1

    def test_list_by_topic_does_not_leak_across_users(self):
        store = get_history_store()
        store.save("甲的追问", "答", user_id=1, conversation_id="shared")
        store.save("乙的追问", "答", user_id=2, conversation_id="shared")

        total, records = store.list_by_topic("shared", user_id=1)
        assert total == 1
        assert records[0].question == "甲的追问"

    def test_delete_only_touches_own_record(self):
        store = get_history_store()
        mine = store.save("我的", "答", user_id=1)
        theirs = store.save("别人的", "答", user_id=2)

        assert store.delete(theirs, user_id=1) is False
        assert store.delete(mine, user_id=1) is True
        # 别人的那条还在
        assert store.get(theirs, user_id=2) is not None

    def test_delete_topic_only_touches_own(self):
        store = get_history_store()
        store.save("甲", "答", user_id=1, conversation_id="t9")
        store.save("乙", "答", user_id=2, conversation_id="t9")

        assert store.delete_topic("t9", user_id=1) == 1
        assert store.list_by_topic("t9", user_id=2)[0] == 1

    def test_delete_many_cannot_reach_another_users_ids(self):
        """勾选清单里的 id 是可以随手编的，归属必须绑在同一条 SQL 里。"""
        store = get_history_store()
        store.save("我的", "答", user_id=1)
        theirs = store.save("别人的", "答", user_id=2)

        assert store.delete_many(ids=[theirs], user_id=1) == 0
        assert store.get(theirs, user_id=2) is not None

    def test_clear_only_clears_own(self):
        store = get_history_store()
        store.save("我的", "答", user_id=1)
        store.save("别人的", "答", user_id=2)
        store.save("匿名的", "答")

        assert store.clear(user_id=1) == 1
        assert store.list(user_id=2)[0] == 1
        assert store.list(user_id=None)[0] == 1

    def test_count_since_window_is_per_user(self):
        """窗口是"这个人自己的最近 N 条"——否则别人的提问会把窗口占满，
        这个人自己的新记录被挤出窗口，画像永远不刷新。"""
        store = get_history_store()
        # 别人先塞满窗口
        for i in range(5):
            store.save(f"别人的 {i}", "答", user_id=2, now=1000 + i)
        # 我再提一条更新的
        store.save("我的新问题", "答", user_id=1, now=2000)

        assert store.count_since(0, user_id=1, window=3) == 1
        assert store.count_since(0, user_id=2, window=3) == 3

    def test_status_total_matches_visible_list(self):
        store = get_history_store()
        store.save("我的", "答", user_id=1)
        store.save("别人的", "答", user_id=2)
        store.save("别人的", "答", user_id=2)

        assert store.status(user_id=1)["total"] == 1
        assert store.status(user_id=2)["total"] == 2
        assert store.status(user_id=None)["total"] == 0


# ── store 层：画像 ──────────────────────────────────────────────────────


TRAIT = {"category": "性格", "content": "做事偏谨慎", "evidence": "我说我总要犹豫很久", "confidence": 0.7}
OTHER_TRAIT = {"category": "爱好", "content": "喜欢读史", "evidence": "我问过很多历史问题", "confidence": 0.6}


class TestProfileStoreScope:
    def test_traits_are_scoped(self):
        store = get_profile_store()
        store.upsert([TRAIT], user_id=1)
        store.upsert([OTHER_TRAIT], user_id=2)

        assert [t.content for t in store.list(user_id=1)] == ["做事偏谨慎"]
        assert store.count(user_id=1) == 1
        assert store.count(user_id=2) == 1
        assert store.count(user_id=None) == 0

    def test_same_content_from_two_users_stays_two_rows(self):
        """两个人都说自己"偏内向"是两件事，合并成一条会让画像串味。"""
        store = get_profile_store()
        store.upsert([TRAIT], user_id=1)
        store.upsert([TRAIT], user_id=2)
        assert store.count(user_id=1) == 1
        assert store.count(user_id=2) == 1

    def test_delete_trait_only_touches_own(self):
        store = get_profile_store()
        store.upsert([TRAIT], user_id=1)
        store.upsert([TRAIT], user_id=2)
        theirs = store.list(user_id=2)[0]

        assert store.delete(theirs.id, user_id=1) is False
        assert store.count(user_id=2) == 1

    def test_clear_only_clears_own(self):
        store = get_profile_store()
        store.upsert([TRAIT], user_id=1)
        store.upsert([TRAIT], user_id=2)
        assert store.clear(user_id=1) == 1
        assert store.count(user_id=2) == 1

    def test_avatar_is_per_user(self):
        """形象存在 meta 表里，而那张表的键是全局的——不带归属，
        A 换了形象 B 打开画像看到的就是 A 的选择。"""
        store = get_profile_store()
        store.set_avatar("female", user_id=1)
        assert store.avatar(user_id=1) == "female"
        assert store.avatar(user_id=2) == "male"  # 默认值

    def test_avatar_of_anonymous_keeps_the_legacy_key(self):
        """匿名读的必须是**不加前缀**的那个键——登录功能上线前的数据就存在那儿。"""
        store = get_profile_store()
        store.set_avatar("female", user_id=None)
        assert store.avatar(user_id=None) == "female"
        # 而且它不会串给任何登录用户
        assert store.avatar(user_id=1) == "male"

    def test_last_extract_is_per_user(self):
        store = get_profile_store()
        store.mark_extracted(user_id=1, now=12345.0)
        assert store.last_extract_ts(user_id=1) == pytest.approx(12345.0)
        assert store.last_extract_ts(user_id=2) == 0.0

    def test_figure_is_per_user(self):
        store = get_profile_store()
        store.set_figure("male", {"id": "wangyangming", "week": "2026-W38"}, user_id=1)
        assert store.get_figure("male", user_id=1)["id"] == "wangyangming"
        assert store.get_figure("male", user_id=2) == {}

    def test_clear_figures_only_clears_own(self):
        store = get_profile_store()
        store.set_figure("male", {"id": "a"}, user_id=1)
        store.set_figure("male", {"id": "b"}, user_id=2)
        store.clear_figures(user_id=1)
        assert store.get_figure("male", user_id=1) == {}
        assert store.get_figure("male", user_id=2)["id"] == "b"

    def test_status_counts_only_own_traits(self):
        store = get_profile_store()
        store.upsert([TRAIT], user_id=1)
        store.upsert([TRAIT, OTHER_TRAIT], user_id=2)
        assert store.status(user_id=1)["total"] == 1
        assert store.status(user_id=2)["total"] == 2

    def test_meta_key_prefix_does_not_collide_with_a_real_key(self):
        """``u1:avatar_gender`` 与 ``avatar_gender`` 是两个键，不能互相覆盖。"""
        store = get_profile_store()
        store.set_avatar("female", user_id=None)
        store.set_avatar("male", user_id=1)
        assert store.avatar(user_id=None) == "female"
        assert store.avatar(user_id=1) == "male"


# ── HTTP 层：路由有没有把当前用户传下去 ────────────────────────────────


class TestHistoryRoutesScope:
    def test_two_users_do_not_see_each_others_questions(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)

        client.post("/api/ask", json={"question": "甲问的问题"}, headers=alice)

        assert [i["question"] for i in client.get("/api/history", headers=alice).json()["items"]] == [
            "甲问的问题"
        ]
        assert client.get("/api/history", headers=bob).json()["items"] == []

    def test_anonymous_cannot_read_anyones_questions(self, anon_client):
        """匿名连这一层都进不去——不是"看到空列表"，是压根不给看。

        这条原先断言的是"匿名读到空列表"（那时匿名是个合法身份，只是看不到
        别人的东西）。现在登录之前一个接口也不放行，所以它变成 401；
        "两个人互相看不见"由上面那条覆盖。
        """
        assert anon_client.get("/api/history").status_code == 401

    def test_topics_endpoint_is_scoped(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)

        assert client.get("/api/history/topics", headers=alice).json()["total"] == 1
        assert client.get("/api/history/topics", headers=bob).json()["total"] == 0

    def test_status_endpoint_is_scoped(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)

        assert client.get("/api/history/status", headers=alice).json()["total"] == 1
        assert client.get("/api/history/status", headers=bob).json()["total"] == 0

    def test_cannot_delete_another_users_record(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)
        record_id = client.get("/api/history", headers=alice).json()["items"][0]["id"]

        assert client.delete(f"/api/history/{record_id}", headers=bob).status_code == 404
        assert len(client.get("/api/history", headers=alice).json()["items"]) == 1

    def test_cannot_read_another_users_topic(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)
        topic_id = client.get("/api/history/topics", headers=alice).json()["items"][0]["id"]

        assert client.get(f"/api/history/topics/{topic_id}", headers=bob).json()["items"] == []

    def test_clear_history_is_scoped(self, client):
        alice = sign_in(client, ALICE)
        bob = sign_in(client, BOB)
        client.post("/api/ask", json={"question": "甲的问题"}, headers=alice)
        client.post("/api/ask", json={"question": "乙的问题"}, headers=bob)

        client.delete("/api/history", headers=alice)
        assert client.get("/api/history", headers=alice).json()["items"] == []
        assert len(client.get("/api/history", headers=bob).json()["items"]) == 1


class TestProfileRoutesScope:
    def test_two_users_do_not_share_avatar(self, client):
        alice, _ = identity(client, ALICE)
        bob, _ = identity(client, BOB)

        assert client.put("/api/profile/avatar", json={"gender": "female"}, headers=alice).json() == {
            "avatar": "female"
        }
        assert client.get("/api/profile", headers=alice).json()["avatar"] == "female"
        assert client.get("/api/profile", headers=bob).json()["avatar"] == "male"

    def test_trait_delete_is_scoped(self, client):
        alice, alice_id = identity(client, ALICE)
        bob, _ = identity(client, BOB)

        # 直接落库：画像的归纳要走模型，这里只关心归属
        store = get_profile_store()
        store.upsert([TRAIT], user_id=alice_id)
        trait_id = store.list(user_id=alice_id)[0].id

        assert client.delete(f"/api/profile/traits/{trait_id}", headers=bob).status_code == 404
        assert store.count(user_id=alice_id) == 1

    def test_profile_counts_only_own_traits(self, client):
        alice, alice_id = identity(client, ALICE)
        bob, _ = identity(client, BOB)

        store = get_profile_store()
        store.upsert([TRAIT, OTHER_TRAIT], user_id=alice_id)

        assert client.get("/api/profile", headers=alice).json()["total"] == 2
        assert client.get("/api/profile", headers=bob).json()["total"] == 0

    def test_extract_uses_only_own_records(self, client, monkeypatch):
        """素材与归属必须配对：读的是这个人的记录，写进的是同一份画像。"""
        alice, alice_id = identity(client, ALICE)
        bob, bob_id = identity(client, BOB)
        client.post("/api/ask", json={"question": "甲问的问题"}, headers=alice)

        seen: dict[str, object] = {}

        def fake_extract(profile, records, *, router=None, lang="zh", user_id=None):
            seen["questions"] = [r.question for r in records]
            seen["user_id"] = user_id
            return profile_module.ExtractionResult(0, 0, False, error="stub")

        # 路由里是从模块取的函数名，得打在路由模块的命名空间上
        from server.routers import profile as profile_router

        monkeypatch.setattr(profile_router, "extract", fake_extract)

        client.post("/api/profile/extract", json={"lang": "zh"}, headers=bob)
        assert seen["questions"] == []
        assert seen["user_id"] == bob_id

        client.post("/api/profile/extract", json={"lang": "zh"}, headers=alice)
        assert seen["questions"] == ["甲问的问题"]
        assert seen["user_id"] == alice_id

    def test_clear_profile_is_scoped(self, client):
        alice, alice_id = identity(client, ALICE)
        bob, bob_id = identity(client, BOB)

        store = get_profile_store()
        store.upsert([TRAIT], user_id=alice_id)
        store.upsert([TRAIT, OTHER_TRAIT], user_id=bob_id)

        client.delete("/api/profile", headers=alice)
        assert store.count(user_id=alice_id) == 0
        assert store.count(user_id=bob_id) == 2
        # 顺手确认 bob 的画像还在
        assert client.get("/api/profile", headers=bob).json()["total"] == 2
