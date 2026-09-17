"""端点会话单元测试：默认端点与请求级自定义端点的选择与隔离（全程不联网）。

这一层的价值全在**隔离**上：用户填的端点有自己的探活与冷却，不能让它在默认
端点上留下任何痕迹，反过来也一样。下面用假的 transport 精确构造两种端点的
可用性组合来验证这件事。
"""

import pytest

from server.services.llm import transport
from server.services.llm.config import LLMConfig
from server.services.llm.router import ModelRouter, get_router
from server.services.llm.session import (
    EndpointOverride,
    EndpointRegistry,
    probe_endpoint,
    resolve_session,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport:
    """按模型名决定行为；``working`` 之外的模型一律 503。"""

    def __init__(self, *, working=(), models=()):
        self.working = set(working)
        self.models = tuple(models)
        self.chat_calls: list[str] = []

    def chat(self, config, model, messages, **kwargs):
        self.chat_calls.append(model)
        if model in self.working:
            return f"来自 {model} 的回答"
        raise transport.LLMTransportError(f"HTTP 503：{model} 上游不可用", 503)

    def list_models(self, config):
        return self.models


@pytest.fixture
def patched(monkeypatch):
    def install(fake: FakeTransport) -> FakeTransport:
        monkeypatch.setattr(transport, "chat", fake.chat)
        monkeypatch.setattr(transport, "list_models", fake.list_models)
        return fake

    return install


# ── 覆盖值的解析 ────────────────────────────────────────────────────────


class TestEndpointOverride:
    def test_parses_complete_payload(self):
        override = EndpointOverride.from_payload(
            {"base_url": "https://mine/v1", "api_key": "sk-mine", "model": "m"}
        )
        assert override is not None
        assert override.usable
        assert override.model == "m"

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            {},
            {"base_url": "https://mine/v1"},
            {"api_key": "sk-mine"},
            {"base_url": "   ", "api_key": "sk-mine"},
            {"base_url": "https://mine/v1", "api_key": ""},
        ],
    )
    def test_incomplete_payload_means_no_override(self, payload):
        """只填一半视同没填——拿半截配置去试探必然失败，不如按默认走。"""
        assert EndpointOverride.from_payload(payload) is None

    def test_ignores_non_string_fields(self):
        assert EndpointOverride.from_payload({"base_url": 123, "api_key": None}) is None

    def test_fingerprint_does_not_leak_the_key(self):
        override = EndpointOverride(base_url="https://mine/v1", api_key="sk-super-secret")
        fingerprint = override.fingerprint()
        assert "sk-super-secret" not in fingerprint
        assert "https://mine/v1" in fingerprint

    def test_fingerprint_is_stable_and_distinguishes_keys(self):
        a = EndpointOverride(base_url="https://mine/v1", api_key="sk-1")
        b = EndpointOverride(base_url="https://mine/v1", api_key="sk-1")
        c = EndpointOverride(base_url="https://mine/v1", api_key="sk-2")
        assert a.fingerprint() == b.fingerprint()
        assert a.fingerprint() != c.fingerprint()


# ── 配置派生 ────────────────────────────────────────────────────────────


class TestWithEndpoint:
    def test_replaces_connection_but_keeps_runtime_parameters(self):
        base = LLMConfig(
            base_url="https://default/v1",
            api_key="sk-default",
            model="m0",
            candidates=("m1", "m2"),
            timeout=33.0,
            total_budget=44.0,
            max_tokens=1234,
        )
        derived = base.with_endpoint("https://mine/v1", "sk-mine", "mx")

        assert derived.base_url == "https://mine/v1"
        assert derived.api_key == "sk-mine"
        assert derived.model == "mx"
        # 运行参数描述的是"这个应用愿意等多久"，与端点无关，必须原样带过去
        assert derived.timeout == 33.0
        assert derived.total_budget == 44.0
        assert derived.max_tokens == 1234

    def test_clears_candidates_from_the_old_endpoint(self):
        """候选是默认端点上的模型名，换端点后留着只会白费探活预算。"""
        base = LLMConfig(candidates=("m1", "m2"))
        derived = base.with_endpoint("https://mine/v1", "sk-mine")
        assert derived.candidates == ()

    def test_blank_url_keeps_the_original(self):
        base = LLMConfig(base_url="https://default/v1")
        assert base.with_endpoint("  ", "sk-mine").base_url == "https://default/v1"


# ── 会话选择 ────────────────────────────────────────────────────────────


class TestResolveSession:
    def test_without_override_uses_the_process_wide_router(self):
        session = resolve_session(None)
        assert session.custom is False
        assert session.router is get_router()

    def test_incomplete_override_also_uses_the_default(self):
        session = resolve_session(EndpointOverride(base_url="https://mine/v1"))
        assert session.custom is False
        assert session.router is get_router()

    def test_complete_override_gets_its_own_router(self):
        override = EndpointOverride(base_url="https://mine/v1", api_key="sk-mine")
        session = resolve_session(override)

        assert session.custom is True
        assert session.router is not get_router()
        assert session.config.base_url == "https://mine/v1"
        assert session.config.api_key == "sk-mine"
        # 默认端点的候选模型不该被带过来
        assert session.config.candidates == ()

    def test_custom_endpoint_reuses_router_for_the_same_key(self):
        override = EndpointOverride(base_url="https://mine/v1", api_key="sk-mine")
        first = resolve_session(override)
        second = resolve_session(override)
        assert first.router is second.router, "同一端点应复用路由器，否则每次提问都要重新探活"


class TestRegistryCache:
    def make(self, override_key: str, **kwargs):
        return EndpointOverride(base_url="https://mine/v1", api_key=override_key, **kwargs)

    def test_expired_entry_is_rebuilt(self):
        clock = FakeClock()
        registry = EndpointRegistry(ttl=60.0, clock=clock)
        override = self.make("sk-mine")

        first = registry.session(override).router
        clock.advance(61)
        assert registry.session(override).router is not first

    def test_evicts_oldest_when_over_limit(self):
        clock = FakeClock()
        registry = EndpointRegistry(limit=2, clock=clock)

        a = registry.session(self.make("sk-a")).router
        clock.advance(1)
        b = registry.session(self.make("sk-b")).router
        clock.advance(1)
        c = registry.session(self.make("sk-c")).router  # 挤掉最早的 a

        # 先验证幸存的，再验证被淘汰的——顺序反过来的话，
        # 重新取 a 又会把别人挤出去，把用例自己搅乱。
        assert registry.session(self.make("sk-c")).router is c
        assert registry.session(self.make("sk-b")).router is b
        assert registry.session(self.make("sk-a")).router is not a

    def test_clear_drops_everything(self):
        registry = EndpointRegistry(clock=FakeClock())
        first = registry.session(self.make("sk-mine")).router
        registry.clear()
        assert registry.session(self.make("sk-mine")).router is not first

    def test_custom_router_state_does_not_reach_the_default_router(self, patched):
        """自定义端点上的失败冷却不能落在默认端点上。"""
        patched(FakeTransport(working=set()))  # 谁都不通
        default = get_router()
        before = default.status()["last_error"]

        override = EndpointOverride(base_url="https://mine/v1", api_key="sk-mine")
        session = resolve_session(override)
        session.router.pick(force=True)

        assert default.status()["last_error"] == before
        assert default.status()["model"] == ""


# ── 测试连接 ────────────────────────────────────────────────────────────


class TestProbeEndpoint:
    def test_incomplete_input_is_rejected_with_a_hint(self):
        result = probe_endpoint(EndpointOverride(base_url="https://mine/v1"))
        assert result["ok"] is False
        assert "接口地址与 API Key" in result["error"]

    def test_reports_the_selected_model_and_available_list(self, patched):
        patched(FakeTransport(working={"good"}, models=("good", "bad")))
        result = probe_endpoint(
            EndpointOverride(base_url="https://mine/v1", api_key="sk-mine")
        )

        assert result["ok"] is True
        assert result["model"] == "good"
        assert "good" in result["models"]
        assert result["error"] == ""

    def test_reports_a_reason_when_nothing_works(self, patched):
        patched(FakeTransport(working=set(), models=("bad",)))
        result = probe_endpoint(
            EndpointOverride(base_url="https://mine/v1", api_key="sk-mine")
        )

        assert result["ok"] is False
        assert result["model"] == ""
        assert result["error"], "失败时必须给出原因，否则按钮上只能显示一句'失败'"
