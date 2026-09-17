"""集成测试：求教接口在配置了 LLM 时的完整链路。

单元测试覆盖了路由策略本身；这里验证的是 **HTTP → 路由 → 换模型 → 生成回答**
这条竖切链路真的接通了——包括"首选模型挂掉时自动换到下一个"这个关键行为。

全程用假的 transport，不发起真实网络请求。
"""

import pytest

from server.services.llm import router as router_module
from server.services.llm import transport

WORKING_MODEL = "backup-model"
BROKEN_MODEL = "primary-model"
CANNED = "## 你的处境\n这是模型生成的回答。"


@pytest.fixture
def llm_env(monkeypatch):
    """配置成"有密钥 + 候选模型已知"，并把 transport 换成假实现。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://fake/v1")
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_MODEL_CANDIDATES", f"{BROKEN_MODEL},{WORKING_MODEL}")

    def fake_chat(config, model, messages, **kwargs):
        if model == BROKEN_MODEL:
            raise transport.LLMTransportError("HTTP 503：上游暂时不可用", 503)
        return CANNED

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ())
    router_module.reset_router()
    yield
    router_module.reset_router()


class TestAskWithLlm:
    def test_answer_comes_from_model(self, client, llm_env):
        body = client.post("/api/ask", json={"question": "工作中遇到小人怎么办？", "top_k": 3}).json()
        assert body["answer"] == CANNED
        assert body["llm_used"] is True
        assert body["model"] == WORKING_MODEL

    def test_failover_skips_broken_primary(self, client, llm_env):
        """首选模型 503 时应自动换到备用模型，而不是降级成本地检索。"""
        body = client.post("/api/ask", json={"question": "如何保持专注？", "top_k": 2}).json()
        assert body["model"] == WORKING_MODEL
        assert body["llm_used"] is True

    def test_status_reports_selected_model(self, client, llm_env):
        client.post("/api/ask", json={"question": "问点什么", "top_k": 1})
        body = client.get("/api/ask/status").json()
        assert body["enabled"] is True
        assert body["model"] == WORKING_MODEL
        assert BROKEN_MODEL in body["cooling_down"]

    def test_degrades_when_every_model_fails(self, client, monkeypatch):
        """全部模型不可用时，接口仍须返回可用内容（本地检索排版）。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL_CANDIDATES", f"{BROKEN_MODEL},{WORKING_MODEL}")

        def all_broken(config, model, messages, **kwargs):
            raise transport.LLMTransportError("HTTP 503：全挂了", 503)

        monkeypatch.setattr(transport, "chat", all_broken)
        monkeypatch.setattr(transport, "list_models", lambda config: ())
        router_module.reset_router()

        body = client.post("/api/ask", json={"question": "如何面对挫折？", "top_k": 3}).json()
        assert body["llm_used"] is False
        assert body["model"] is None
        assert body["retrieved_count"] == 3
        assert "本地检索结果" in body["answer"]
