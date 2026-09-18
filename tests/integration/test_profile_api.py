"""集成测试：画像接口在 HTTP 上跑通。

包括"模型可用时真的写进库"这条完整链路——用假 transport，不联网。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from server.services.llm import router as router_module
from server.services.llm import transport

MODEL = "test-model"

TRAITS = [
    {
        "category": "性格",
        "content": "做事偏谨慎，习惯想清楚再动手",
        "evidence": "我说我总是犹豫很久才决定",
        "confidence": 0.8,
    }
]


@pytest.fixture
def fake_model(monkeypatch):
    """配置成"有密钥"，并把 transport 换成固定返回一段 JSON 的假实现。

    返回一个记录器：``.messages`` 是历次送出的消息，用来断言提问被真的送进了
    模型（以及用的是哪种语言）。
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://fake/v1")
    monkeypatch.setenv("LLM_MODEL", MODEL)
    monkeypatch.setenv("LLM_MODEL_CANDIDATES", MODEL)

    sent: list[list[dict]] = []

    def fake_chat(config, model, messages, **kwargs):
        sent.append(messages)
        return json.dumps(TRAITS, ensure_ascii=False)

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ())
    router_module.reset_router()

    recorder = SimpleNamespace(messages=sent)
    yield recorder
    router_module.reset_router()


class TestProfileBasics:
    def test_empty_profile(self, client):
        body = client.get("/api/profile").json()
        assert body["available"] is True
        assert body["traits"] == []
        assert body["avatar"] == "male"
        # 分类清单给界面排引线用，必须是完整的封闭集合
        assert "性格" in body["categories"]
        assert "规划" in body["categories"]

    def test_nothing_pending_on_a_fresh_install(self, client):
        """没问过问题就没有待归纳的东西，画像页不该自动去调模型。"""
        assert client.get("/api/profile").json()["pending"] == 0

    def test_pending_counts_questions_asked_after_the_last_extraction(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        assert client.get("/api/profile").json()["pending"] == 1

        client.post("/api/profile/extract")
        # 归纳过了，这批提问就不再算"新"
        assert client.get("/api/profile").json()["pending"] == 0

        client.post("/api/ask", json={"question": "那我该怎么办", "top_k": 1})
        assert client.get("/api/profile").json()["pending"] == 1

    def test_extract_without_model_reports_why(self, client):
        """没有模型不是 500——画像本来就是附加功能。"""
        body = client.post("/api/profile/extract").json()
        assert body["ok"] is False
        assert body["llm_used"] is False
        assert body["error"] == "llm_disabled"

    def test_extract_with_no_history_says_so(self, client, fake_model):
        body = client.post("/api/profile/extract").json()
        assert body["ok"] is False
        assert body["error"] == "no_records"


class TestLanguage:
    """归纳提示词的语言。

    ``/api/ask`` 也会走同一个假 transport，所以要看的是**最后一次**调用——
    归纳排在求教之后。
    """

    def test_english_asks_the_model_in_english(self, client, fake_model):
        client.post("/api/ask", json={"question": "How do I choose?", "top_k": 1})
        client.post("/api/profile/extract", json={"lang": "en"})

        system, user = fake_model.messages[-1]
        assert "questions this user asked" in user["content"]
        # 分类仍然是中文封闭集合，否则界面上的引线没有落脚点
        assert "性格" in system["content"]

    def test_missing_language_defaults_to_chinese(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract", json={})

        assert "以下是这位用户问过的问题" in fake_model.messages[-1][-1]["content"]


class TestAvatar:
    def test_can_be_switched_and_read_back(self, client):
        body = client.put("/api/profile/avatar", json={"gender": "female"}).json()
        assert body["avatar"] == "female"
        assert client.get("/api/profile").json()["avatar"] == "female"

    def test_unknown_value_falls_back(self, client):
        body = client.put("/api/profile/avatar", json={"gender": "别的"}).json()
        assert body["avatar"] == "male"


class TestExtractWithModel:
    def test_traits_are_stored_and_listed(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})

        body = client.post("/api/profile/extract").json()
        assert body["ok"] is True
        assert body["extracted"] == 1

        profile = client.get("/api/profile").json()
        assert profile["total"] == 1
        assert profile["traits"][0]["category"] == "性格"
        assert profile["traits"][0]["evidence"]

    def test_extract_twice_does_not_duplicate(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})

        client.post("/api/profile/extract")
        client.post("/api/profile/extract")

        assert client.get("/api/profile").json()["total"] == 1

    def test_delete_one_trait(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")
        trait_id = client.get("/api/profile").json()["traits"][0]["id"]

        assert client.delete(f"/api/profile/traits/{trait_id}").json()["deleted"] == 1
        assert client.get("/api/profile").json()["total"] == 0

    def test_delete_missing_trait_is_a_404(self, client):
        assert client.delete("/api/profile/traits/9999").status_code == 404

    def test_clear_the_whole_profile(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")

        assert client.delete("/api/profile").json()["deleted"] == 1
        assert client.get("/api/profile").json()["total"] == 0

    def test_clearing_the_profile_keeps_the_history(self, client, fake_model):
        """画像和问答记录是两份数据，清空一个不该动另一个。"""
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")

        client.delete("/api/profile")

        assert client.get("/api/history").json()["total"] == 1
