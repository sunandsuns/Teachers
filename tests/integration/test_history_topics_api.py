"""集成测试：话题分组在 HTTP 上跑通。

其中一条专门守住**路由顺序**：``/api/history/topics`` 若排在
``/api/history/{record_id}`` 之后，会被 ``int`` 校验拦下直接 422——
这种写法在浏览器里表现为"话题列表莫名打不开"，而单元测试完全看不到。
"""

from __future__ import annotations


def ask(client, question: str, **extra) -> dict:
    return client.post("/api/ask", json={"question": question, "top_k": 1, **extra}).json()


class TestConversationId:
    def test_every_ask_gets_a_topic(self, client):
        assert ask(client, "如何坚持？")["conversation_id"]

    def test_follow_up_reuses_the_given_topic(self, client):
        topic = ask(client, "如何坚持？")["conversation_id"]
        assert ask(client, "那具体呢？", conversation_id=topic)["conversation_id"] == topic

    def test_asks_without_a_topic_do_not_share_one(self, client):
        first = ask(client, "问题一")["conversation_id"]
        second = ask(client, "问题二")["conversation_id"]
        assert first != second


class TestTopicEndpoints:
    def test_topics_route_is_not_swallowed_by_the_record_route(self, client):
        """路由顺序的回归：``/topics`` 必须排在 ``/{record_id}`` 前面。"""
        assert client.get("/api/history/topics").status_code == 200

    def test_follow_ups_are_grouped_into_one_card(self, client):
        topic = ask(client, "如何坚持？")["conversation_id"]
        ask(client, "那具体呢？", conversation_id=topic)

        body = client.get("/api/history/topics").json()
        assert body["total"] == 1
        card = body["items"][0]
        assert card["id"] == topic
        assert card["question_count"] == 2
        assert card["title"] == "如何坚持？"
        assert card["latest_question"] == "那具体呢？"

    def test_topic_records_are_chronological(self, client):
        topic = ask(client, "第一问")["conversation_id"]
        ask(client, "第二问", conversation_id=topic)
        ask(client, "第三问", conversation_id=topic)

        body = client.get(f"/api/history/topics/{topic}").json()
        assert body["total"] == 3
        assert [item["question"] for item in body["items"]] == ["第一问", "第二问", "第三问"]

    def test_flat_listing_still_works(self, client):
        """平铺接口是旧路径，别为了分组把它弄坏。"""
        ask(client, "如何坚持？")
        body = client.get("/api/history").json()
        assert body["total"] == 1
        assert body["items"][0]["conversation_id"]

    def test_delete_topic_removes_all_records(self, client):
        topic = ask(client, "第一问")["conversation_id"]
        ask(client, "第二问", conversation_id=topic)

        assert client.delete(f"/api/history/topics/{topic}").json()["deleted"] == 2
        assert client.get("/api/history/topics").json()["total"] == 0
        assert client.get("/api/history").json()["total"] == 0

    def test_deleting_an_unknown_topic_is_a_404(self, client):
        assert client.delete("/api/history/topics/nope").status_code == 404

    def test_single_record_deletion_is_still_available(self, client):
        """话题里删单条（而不是整个话题）也要能删掉。"""
        topic = ask(client, "第一问")["conversation_id"]
        ask(client, "第二问", conversation_id=topic)
        record_id = client.get(f"/api/history/topics/{topic}").json()["items"][0]["id"]

        assert client.delete(f"/api/history/{record_id}").json()["deleted"] == 1
        assert client.get(f"/api/history/topics/{topic}").json()["total"] == 1

    def test_unavailable_database_still_answers_200(self, client, monkeypatch, tmp_path):
        """库建不出来时，话题列表也走 200 + available:false，而不是 500。"""
        from server.services import history as history_module
        from server.services.history import HistoryStore

        blocked = tmp_path / "blocked"
        blocked.write_text("我不是目录", encoding="utf-8")
        blocked_store = HistoryStore()
        blocked_store._db._path = blocked / "history.db"  # noqa: SLF001 — 测试要造出"建不出来"
        monkeypatch.setattr(history_module, "_store", blocked_store)

        body = client.get("/api/history/topics").json()
        assert body["available"] is False
        assert body["error"]
        assert body["items"] == []
