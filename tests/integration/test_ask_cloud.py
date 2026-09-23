"""集成测试：给浏览器侧云模型用的两条接口（``/api/ask/plan`` 与 ``/ask/save``）。

云模型那条路的生成发生在页面里（凭据按浏览器 Origin 鉴权，后端代不了），
于是后端必须拆成"备料"与"记账"两步。这里守住三件事：

1. **备料与内置模型那条路完全一致**——同样的检索、同样的题型指令。
   两边各写一份模板，改起来一定会走偏，而这个偏很难从界面上看出来。
2. **不生成、不落库**：``plan`` 是只读的，调用它不该在「回响」里留下痕迹。
3. **生成完能补记回来**：``save`` 要能把页面产出的回答存进去，
   且存不进去（库不可用）时照样返回 200。

全程用假的 transport，不发起真实网络请求。
"""

import pytest

from server.services.llm import router as router_module
from server.services.llm import transport

MODEL = "test-model"


@pytest.fixture
def patched(monkeypatch):
    """让默认端点"配了但用不上"——plan 本来就不该调模型。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://fake/v1")
    monkeypatch.setenv("LLM_MODEL", MODEL)
    monkeypatch.setenv("LLM_MODEL_CANDIDATES", MODEL)

    calls: list[list[dict[str, str]]] = []

    def fake_chat(config, model, messages, **kwargs):
        calls.append(messages)
        return "不该被调用"

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ())
    router_module.reset_router()
    yield calls
    router_module.reset_router()


class TestPlan:
    def test_returns_system_and_user_messages(self, client, patched):
        resp = client.post("/api/ask/plan", json={"question": "如何坚持长期目标？", "top_k": 3})
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert [m["role"] for m in messages][0] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"].strip() != ""

    def test_does_not_call_the_model(self, client, patched):
        """plan 只备料。它若偷偷生成一次，用户会为一次没用到的回答付钱。"""
        client.post("/api/ask/plan", json={"question": "如何坚持长期目标？", "top_k": 2})
        assert patched == []

    def test_current_turn_carries_the_retrieved_passages(self, client, patched):
        """与内置模型那条路同一套上下文：片段编号 + 出处，否则模型无处可引。"""
        resp = client.post("/api/ask/plan", json={"question": "上善若水怎么理解？", "top_k": 3})
        assert "片段" in resp.json()["messages"][-1]["content"]

    def test_history_is_replayed(self, client, patched):
        resp = client.post(
            "/api/ask/plan",
            json={
                "question": "那具体怎么做？",
                "top_k": 2,
                "history": [{"question": "我总是半途而废", "answer": "先从小事做起"}],
            },
        )
        roles = [m["role"] for m in resp.json()["messages"]]
        assert roles == ["system", "user", "assistant", "user"]

    def test_intent_guidance_is_applied(self, client, patched):
        """选择题要拿到"必须明确选一个"的指令——两套路必须一样。"""
        resp = client.post(
            "/api/ask/plan", json={"question": "我该忍还是该说？", "top_k": 2}
        )
        assert "该" in resp.json()["messages"][0]["content"]

    def test_returns_a_conversation_id(self, client, patched):
        resp = client.post("/api/ask/plan", json={"question": "如何坚持？", "top_k": 2})
        assert resp.json()["conversation_id"]

    def test_rejects_empty_question(self, client, patched):
        assert client.post("/api/ask/plan", json={"question": ""}).status_code == 422


class TestSave:
    def test_stores_the_browser_generated_answer(self, client, patched):
        resp = client.post(
            "/api/ask/save",
            json={
                "question": "如何坚持长期目标？",
                "answer": "先从一件小事做起。",
                "model": "cloud-model-x",
                "retrieved_count": 4,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "先从一件小事做起。"
        assert body["model"] == "cloud-model-x"
        assert body["llm_used"] is True
        assert body["conversation_id"]

        # 真的进了「回响」：云模型那条路本来不经过后端，漏了这一步就整段丢失
        history = client.get("/api/history?limit=50").json()
        questions = [item["question"] for item in history["items"]]
        assert "如何坚持长期目标？" in questions

    def test_reuses_the_given_conversation_id(self, client, patched):
        resp = client.post(
            "/api/ask/save",
            json={"question": "追问一句", "answer": "接着说", "conversation_id": "topic-9"},
        )
        assert resp.json()["conversation_id"] == "topic-9"

    def test_model_defaults_to_the_cloud_tag(self, client, patched):
        """没给模型名时记来源标记，而不是把 null 当"本地检索降级"显示。"""
        resp = client.post("/api/ask/save", json={"question": "问一句", "answer": "答一句"})
        assert resp.json()["model"]

    def test_rejects_empty_answer(self, client, patched):
        assert (
            client.post("/api/ask/save", json={"question": "问一句", "answer": ""}).status_code
            == 422
        )
