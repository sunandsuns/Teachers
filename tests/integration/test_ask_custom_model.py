"""集成测试：求教接口的自定义模型通道（HTTP → 会话 → 生成，全程不联网）。

单元测试覆盖了会话层本身；这里验证的是**竖切链路**——界面填的地址与 Key
真的随请求走到了传输层，且失败时给用户的提示指向他自己填的那套配置。
"""

import pytest

from server.services.llm import transport

CANNED = "## 回答\n这是模型生成的回答。"
CUSTOM = {"base_url": "https://mine/v1", "api_key": "sk-mine", "model": ""}


@pytest.fixture
def recording(monkeypatch):
    """记录每次调用用的端点，用来自证"这次到底连的是哪个地址"。

    默认配置（``.env`` 里的那套）在测试夹具里被清空了 Key，所以凡是被记录到
    带 Key 的调用，都只可能来自请求里带的 ``llm`` 字段。
    """
    seen: list[tuple[str, str]] = []

    def fake_chat(config, model, messages, **kwargs):
        seen.append((config.base_url, config.api_key))
        return CANNED

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ("model-a",))
    return seen


class TestAskWithCustomEndpoint:
    def test_custom_endpoint_is_actually_used(self, client, recording):
        body = client.post(
            "/api/ask",
            json={"question": "如何面对挫折？", "top_k": 2, "llm": CUSTOM},
        ).json()

        assert body["llm_used"] is True
        assert body["model"] == "model-a"
        assert ("https://mine/v1", "sk-mine") in recording

    def test_without_the_llm_field_nothing_changes(self, client, recording):
        """不带 llm 字段 = 用内置配置；测试环境没有 Key，应直接走本地检索。"""
        body = client.post("/api/ask", json={"question": "如何面对挫折？", "top_k": 2}).json()

        assert body["llm_used"] is False
        assert body["model"] is None
        assert recording == [], "没填自定义端点就不该有任何模型调用"

    def test_incomplete_endpoint_falls_back_to_the_default(self, client, recording):
        body = client.post(
            "/api/ask",
            json={
                "question": "如何面对挫折？",
                "top_k": 2,
                "llm": {"base_url": "https://mine/v1", "api_key": "", "model": ""},
            },
        ).json()

        assert body["llm_used"] is False
        assert recording == []

    def test_failure_hint_points_at_the_users_own_settings(self, client, monkeypatch):
        """自定义端点失败时，别让用户去找一个自己没听说过的环境变量。"""

        def broken(config, model, messages, **kwargs):
            raise transport.LLMTransportError("HTTP 401：密钥无效", 401)

        monkeypatch.setattr(transport, "chat", broken)
        monkeypatch.setattr(transport, "list_models", lambda config: ("model-a",))

        body = client.post(
            "/api/ask",
            json={"question": "如何面对挫折？", "top_k": 2, "llm": CUSTOM},
        ).json()

        assert body["llm_used"] is False
        assert "自定义模型的接口地址与 API Key" in body["answer"]


class TestProbeEndpoint:
    def test_reports_the_models_the_endpoint_exposes(self, client, recording):
        body = client.post("/api/ask/probe", json=CUSTOM).json()

        assert body["ok"] is True
        assert body["model"] == "model-a"
        assert body["models"] == ["model-a"]
        assert body["error"] == ""

    def test_requires_both_address_and_key(self, client):
        body = client.post(
            "/api/ask/probe", json={"base_url": "https://mine/v1", "api_key": "", "model": ""}
        ).json()

        assert body["ok"] is False
        assert "API Key" in body["error"]

    def test_reports_a_reason_when_unreachable(self, client, monkeypatch):
        def broken(config, model, messages, **kwargs):
            raise transport.LLMTransportError("HTTP 503：上游不可用", 503)

        monkeypatch.setattr(transport, "chat", broken)
        monkeypatch.setattr(transport, "list_models", lambda config: ())

        body = client.post("/api/ask/probe", json=CUSTOM).json()

        assert body["ok"] is False
        assert body["error"], "失败时必须给出原因，否则界面上只能显示一句'失败'"
