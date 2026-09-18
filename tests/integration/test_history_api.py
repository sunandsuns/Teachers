"""历史记录（「回响」）的接口集成测试。

覆盖从 HTTP 边界看过去的那条完整链路：

    求教一次 → 记录入库 → 列表里能查到 → 可以单条删除 / 整体清空

以及**数据库不可用时的优雅降级**——程序目录只读、磁盘满这些情况在真实机器上
是会发生的，那时求教本身必须照常可用，只是不再记账。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from server.services import history as history_module
from server.services.db import Database


def ask(client, question: str, top_k: int = 2):
    response = client.post("/api/ask", json={"question": question, "top_k": top_k})
    assert response.status_code == 200, response.text
    return response.json()


class TestHistoryFlow:
    def test_ask_is_recorded_and_listed(self, client):
        answer = ask(client, "工作中遇到小人怎么办？")

        assert answer["history_id"] is not None
        listing = client.get("/api/history").json()

        assert listing["available"] is True
        assert listing["total"] == 1
        item = listing["items"][0]
        assert item["id"] == answer["history_id"]
        assert item["question"] == "工作中遇到小人怎么办？"
        assert item["answer"] == answer["answer"]
        assert item["model"] == answer["model"]
        assert item["llm_used"] == answer["llm_used"]
        assert item["retrieved_count"] == answer["retrieved_count"]
        # 时间要能给前端直接 new Date(...)
        assert datetime.fromisoformat(item["created_at"]).year == datetime.now().year

    def test_newest_first_and_pagination(self, client):
        for index in range(3):
            ask(client, "第 %d 个问题" % index)

        first = client.get("/api/history?limit=2").json()
        second = client.get("/api/history?limit=2&offset=2").json()

        assert first["total"] == second["total"] == 3
        assert [i["question"] for i in first["items"]] == ["第 2 个问题", "第 1 个问题"]
        assert [i["question"] for i in second["items"]] == ["第 0 个问题"]

    def test_limit_is_validated(self, client):
        assert client.get("/api/history?limit=0").status_code == 422
        assert client.get("/api/history?limit=99999").status_code == 422
        assert client.get("/api/history?offset=-1").status_code == 422

    def test_delete_one(self, client):
        answer = ask(client, "如何面对挫折？")

        response = client.delete("/api/history/%d" % answer["history_id"])

        assert response.status_code == 200 and response.json() == {"deleted": 1}
        assert client.get("/api/history").json()["total"] == 0
        # 再删一次就是 404，而不是"成功删除了 0 条"
        assert client.delete("/api/history/%d" % answer["history_id"]).status_code == 404

    def test_clear_all(self, client):
        for index in range(3):
            ask(client, "问题 %d" % index)

        assert client.delete("/api/history").json() == {"deleted": 3}
        listing = client.get("/api/history").json()
        assert listing["total"] == 0 and listing["items"] == []


class TestHistoryStatus:
    def test_reports_store_location_and_retention(self, client):
        ask(client, "问题")
        status = client.get("/api/history/status").json()

        assert status["available"] is True
        assert status["error"] == ""
        assert status["total"] == 1
        # 半个月
        assert status["retention_days"] == 15.0
        assert status["db_path"].endswith("history.db")
        # 库是自己建出来的，不需要用户做任何初始化
        assert status["size_bytes"] > 0
        assert status["next_purge_at"] is not None

    def test_retention_window_is_configurable(self, client, monkeypatch):
        monkeypatch.setenv("RSDS_HISTORY_RETENTION_DAYS", "7")
        history_module.reset_history_store()

        assert client.get("/api/history/status").json()["retention_days"] == 7.0


class TestGracefulDegradation:
    """数据库坏掉时：求教照常，历史记录如实报告不可用。"""

    @pytest.fixture
    def broken_db(self, monkeypatch):
        def explode(self, **kwargs):
            raise OSError("磁盘满了")

        monkeypatch.setattr(Database, "connect", explode)
        # 换成"连不上"的那一份：单例在 lifespan 里已经建过，得让它重建
        history_module.reset_history_store()
        yield

    def test_ask_still_answers(self, client, broken_db):
        answer = ask(client, "如何面对挫折？")

        assert answer["answer"]  # 检索降级也该给出内容
        assert answer["history_id"] is None  # 只是没记上

    def test_list_reports_unavailable_instead_of_failing(self, client, broken_db):
        response = client.get("/api/history")

        assert response.status_code == 200
        body = response.json()
        assert body["available"] is False
        assert "磁盘满了" in body["error"]
        assert body["items"] == [] and body["total"] == 0

    def test_status_explains_the_failure(self, client, broken_db):
        status = client.get("/api/history/status").json()

        assert status["available"] is False
        assert "磁盘满了" in status["error"]
        # 即便不可用也要说清"打算写在哪"，否则用户没法排查
        assert status["db_path"].endswith("history.db")

    def test_delete_and_clear_do_not_blow_up(self, client, broken_db):
        # 什么都没有，删不到就是 404，而不是 500
        assert client.delete("/api/history/1").status_code == 404
        assert client.delete("/api/history").json() == {"deleted": 0}
