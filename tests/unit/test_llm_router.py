"""模型路由单元测试：探活、缓存、冷却与失败轮换（全程不联网）。

路由的关键价值在于"端点上有的模型能跑、有的跑不了"这个现实。
这里用假的 transport 精确构造出各种可用性组合来验证策略。

关于并发探活
--------------------------------------------------------------------------
``pick()`` 是**并发**探活整个候选批次的（原因见 ``router.PROBE_BUDGET_SHARE``），
因此"批内哪个模型先被探到"没有确定顺序。断言里凡涉及探活调用**顺序**的地方
都必须换成集合或计数；需要"当前模型是谁"确定的用例，用 ``probe_limit=1``
或只给一个候选把批次收窄到单个。
"""

import time

import pytest

from server.services.llm import transport
from server.services.llm.config import LLMConfig
from server.services.llm.router import ModelRouter
from server.services.retriever import SearchResult


class FakeClock:
    """可手动推进的时钟，用来测 TTL 与冷却。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport:
    """按模型名决定行为：返回内容、抛可重试错误、抛不可重试错误。"""

    def __init__(self, *, working=(), retryable_fail=(), fatal_fail=(), models=()):
        self.working = set(working)
        self.retryable_fail = set(retryable_fail)
        self.fatal_fail = set(fatal_fail)
        self.models = tuple(models)
        self.chat_calls: list[str] = []
        self.model_list_calls = 0

    def chat(self, config, model, messages, **kwargs):
        self.chat_calls.append(model)
        if model in self.fatal_fail:
            raise transport.LLMTransportError(f"HTTP 404：模型 {model} 不存在", 404)
        if model in self.retryable_fail:
            raise transport.LLMTransportError(f"HTTP 503：{model} 上游不可用", 503)
        if model in self.working:
            return f"来自 {model} 的回答"
        raise transport.LLMTransportError(f"HTTP 500：{model} 未知故障", 500)

    def list_models(self, config):
        self.model_list_calls += 1
        return self.models


@pytest.fixture
def patched(monkeypatch):
    """把 router 依赖的 transport 换成假实现。"""

    def install(fake: FakeTransport) -> FakeTransport:
        monkeypatch.setattr(transport, "chat", fake.chat)
        monkeypatch.setattr(transport, "list_models", fake.list_models)
        return fake

    return install


def make_config(**overrides) -> LLMConfig:
    base = dict(
        base_url="https://fake/v1",
        api_key="sk-test",
        candidates=("m1", "m2", "m3"),
        probe_timeout=5.0,
        cache_ttl=300.0,
        failure_cooldown=120.0,
    )
    base.update(overrides)
    return LLMConfig(**base)


# ── 挑选 ────────────────────────────────────────────────────────────────


class TestPick:
    def test_returns_empty_when_not_configured(self, patched):
        router = ModelRouter(LLMConfig(api_key=""), clock=FakeClock())
        assert router.pick() == ""

    def test_picks_working_model_from_batch(self, patched):
        """一批候选里只有 m2 能用时应选中 m2；坏掉的候选不阻碍挑选。"""
        fake = patched(FakeTransport(working={"m2"}, retryable_fail={"m1"}))
        router = ModelRouter(make_config(), clock=FakeClock())

        assert router.pick() == "m2"
        assert "m1" in fake.chat_calls and "m2" in fake.chat_calls

    def test_returns_empty_when_all_fail(self, patched):
        patched(FakeTransport(retryable_fail={"m1", "m2", "m3"}))
        router = ModelRouter(make_config(), clock=FakeClock())

        assert router.pick() == ""
        assert "不可用" in router.status()["last_error"]

    def test_caches_winner_within_ttl(self, patched):
        fake = patched(FakeTransport(working={"m1"}))
        clock = FakeClock()
        router = ModelRouter(make_config(), clock=clock)

        assert router.pick() == "m1"
        first_round = len(fake.chat_calls)
        assert router.pick() == "m1"
        assert len(fake.chat_calls) == first_round, "TTL 内命中缓存，不该再探活"

        clock.advance(301)
        assert router.pick() == "m1"
        assert len(fake.chat_calls) > first_round, "TTL 过后应重新探活"

    def test_force_reprobes(self, patched):
        fake = patched(FakeTransport(working={"m1"}))
        router = ModelRouter(make_config(), probe_limit=1, clock=FakeClock())

        router.pick()
        router.pick(force=True)
        assert fake.chat_calls == ["m1", "m1"]

    def test_failed_model_enters_cooldown(self, patched):
        fake = patched(FakeTransport(working={"m2"}, retryable_fail={"m1"}))
        router = ModelRouter(make_config(), clock=FakeClock())

        assert router.pick() == "m2"
        assert "m1" not in router.candidates(), "探活失败的模型应进冷却"

        fake.chat_calls.clear()
        router.pick(force=True)
        assert "m1" not in fake.chat_calls, "冷却期内的 m1 不该被反复探活"
        assert "m2" in fake.chat_calls

    def test_cooldown_expires(self, patched):
        fake = patched(FakeTransport(working={"m1", "m2"}))
        clock = FakeClock()
        router = ModelRouter(make_config(), clock=clock)

        router.pick()
        router.mark_failed("m2")
        clock.advance(121)
        assert "m2" in router.candidates(), "冷却结束后 m2 应重回候选"

    def test_probe_limit_caps_attempts(self, patched):
        """上游整体故障时不能把每个候选都试一遍，否则请求会长时间挂住。"""
        fake = patched(FakeTransport(retryable_fail={"m1", "m2", "m3"}))
        router = ModelRouter(make_config(), probe_limit=2, clock=FakeClock())

        router.pick()
        assert len(fake.chat_calls) == 2


# ── 并发探活 ────────────────────────────────────────────────────────────


class TestConcurrentProbe:
    """探活必须并发，否则卡住的候选会把时间预算吃光。

    这是修掉的一处真实故障：聚合端点上 4 个候选里有 3 个"连得上但不回应"，
    串行探活先耗 3 × probe_timeout，45s 总预算在探活阶段就见底，
    于是**明明有可用模型，生成一步却没有余量，用户等满 45 秒拿到的仍是降级答案**。

    并发把探活阶段的耗时上限从"候选数 × 超时"压回"单次超时"。
    这里用真实时钟 + 真实 sleep：假时钟在并发下无法反映真实耗时。
    """

    @staticmethod
    def _install(monkeypatch, handler):
        monkeypatch.setattr(transport, "chat", handler.chat)
        monkeypatch.setattr(transport, "list_models", handler.list_models)
        return handler

    def test_hanging_candidates_do_not_multiply_wait(self, monkeypatch):
        class Hanging:
            def __init__(self):
                self.calls: list[str] = []

            def chat(self, config, model, messages, **kwargs):
                self.calls.append(model)
                time.sleep(float(kwargs.get("timeout") or 1.0))
                raise transport.LLMTransportError("网络异常：读取超时")

            def list_models(self, config):
                return ()

        handler = self._install(monkeypatch, Hanging())
        candidates = ("h1", "h2", "h3", "h4")
        router = ModelRouter(
            make_config(candidates=candidates, probe_timeout=0.5),
            clock=time.monotonic,
        )

        started = time.monotonic()
        assert router.pick() == ""
        elapsed = time.monotonic() - started

        assert sorted(handler.calls) == sorted(candidates), "四个候选都该探到"
        # 串行需 4 × 0.5 = 2.0s；并发应接近单次 0.5s
        assert elapsed < 1.6, "探活耗时随候选数线性增长，实测 %.2fs" % elapsed

    def test_returns_first_success_without_waiting_for_hanging_siblings(self, monkeypatch):
        """已经拿到可用模型就立即返回，不必等卡住的候选熬满超时。"""

        class Mixed:
            def __init__(self):
                self.calls: list[str] = []

            def chat(self, config, model, messages, **kwargs):
                self.calls.append(model)
                if model == "fast":
                    return "ok"
                time.sleep(float(kwargs.get("timeout") or 1.0))
                raise transport.LLMTransportError("网络异常：读取超时")

            def list_models(self, config):
                return ()

        handler = self._install(monkeypatch, Mixed())
        router = ModelRouter(
            make_config(candidates=("slow1", "slow2", "slow3", "fast"), probe_timeout=1.0),
            clock=time.monotonic,
        )

        started = time.monotonic()
        assert router.pick() == "fast"
        elapsed = time.monotonic() - started
        assert elapsed < 0.6, "拿到可用模型后应立即返回，实测 %.2fs" % elapsed


# ── 时间预算 ────────────────────────────────────────────────────────────


class TestTimeBudget:
    """上游集体故障时，整段流程必须被时间预算截断，及时降级。

    没有预算的话：探活超时 + 一次生成超时可能拖到几分钟，
    用户会在页面上干等到浏览器超时。

    注意预算约束的是**整段流程**（探活 + 生成），不只是生成。
    早先探活串行且不受比例限制，45s 预算会在探活阶段就被吃干净，
    生成一步没有余量——这个坑由 ``TestConcurrentProbe`` 守着。
    """

    @staticmethod
    def _slow_transport(clock: FakeClock, cost: float, **kwargs) -> FakeTransport:
        """每次调用都推进时钟 ``cost`` 秒，模拟上游卡住。"""
        fake = FakeTransport(**kwargs)
        original = fake.chat

        def slow(config, model, messages, **kw):
            clock.advance(cost)
            return original(config, model, messages, **kw)

        fake.chat = slow
        return fake

    def test_pick_returns_empty_when_budget_already_exhausted(self, patched):
        """deadline 已过时一次探活都不该发起——预算是硬约束，不是建议。"""
        clock = FakeClock()
        fake = patched(FakeTransport(working={"m1"}))
        router = ModelRouter(make_config(), clock=clock)

        assert router.pick(deadline=clock() - 1) == ""
        assert fake.chat_calls == [], "预算已耗尽时不该再打上游"
        assert "预算" in router.status()["last_error"]

    def test_pick_within_budget_tries_whole_batch(self, patched):
        clock = FakeClock()
        fake = patched(
            self._slow_transport(clock, 1.0, retryable_fail={"m1", "m2", "m3"})
        )
        router = ModelRouter(make_config(total_budget=50.0), clock=clock)

        assert router.pick() == ""
        assert len(fake.chat_calls) == 3, "预算充裕时整个批次都该探到"

    def test_chat_gives_up_within_budget(self, monkeypatch):
        """上游集体卡住时必须在预算内抛错，而不是挂到用户浏览器超时。"""

        class Hanging:
            def __init__(self):
                self.calls: list[str] = []

            def chat(self, config, model, messages, **kwargs):
                self.calls.append(model)
                time.sleep(float(kwargs.get("timeout") or 1.0))
                raise transport.LLMTransportError("网络异常：读取超时")

            def list_models(self, config):
                return ()

        handler = Hanging()
        monkeypatch.setattr(transport, "chat", handler.chat)
        monkeypatch.setattr(transport, "list_models", handler.list_models)
        router = ModelRouter(
            make_config(
                candidates=("h1", "h2", "h3"), probe_timeout=0.5, total_budget=1.0
            ),
            clock=time.monotonic,
        )

        started = time.monotonic()
        with pytest.raises(transport.LLMTransportError):
            router.chat([{"role": "user", "content": "问"}])
        elapsed = time.monotonic() - started

        assert handler.calls, "至少应该探过一次"
        assert elapsed < 2.0, "应在预算内放弃，实测 %.2fs" % elapsed

    def test_budget_does_not_block_a_healthy_call(self, patched):
        fake = patched(FakeTransport(working={"m1"}))
        router = ModelRouter(make_config(total_budget=45.0), clock=FakeClock())

        content, model = router.chat([{"role": "user", "content": "问"}])
        assert model == "m1"
        assert "m1" in content


class TestHardCooldown:
    """权限/模型不存在这类错误换模型也修不好，冷却要更久。"""

    def test_hard_failure_cools_longer_than_soft(self, patched):
        clock = FakeClock()
        patched(FakeTransport(working={"m1"}))
        router = ModelRouter(make_config(), clock=clock)

        router.mark_failed("m1")            # 软冷却 120s
        router.mark_failed("m2", hard=True)  # 硬冷却 600s

        clock.advance(200)  # 已超过软冷却，但不到硬冷却
        assert "m1" in router.candidates()
        assert "m2" not in router.candidates()

        clock.advance(401)  # 累计 601s
        assert "m2" in router.candidates()

    def test_probe_hard_failure_cools_longer(self, patched):
        """探活阶段撞到 404 同样该按硬冷却处理。

        探活失败原先丢弃了 HTTP 状态，403/404 这类"换模型也修不好"的错误
        被当成软失败，120s 后就再去撞同一堵墙，白耗预算。
        """
        clock = FakeClock()
        patched(FakeTransport(working={"m2"}, fatal_fail={"m1"}))
        router = ModelRouter(make_config(), clock=clock)

        assert router.pick() == "m2", "m1 探活 404，应退到 m2"
        clock.advance(200)  # 已过软冷却（120s），未到硬冷却（600s）
        assert "m1" not in router.candidates(), "探活阶段的 404 应触发硬冷却"

    def test_non_retryable_failure_marks_hard_cooldown(self, patched, monkeypatch):
        clock = FakeClock()
        fake = patched(FakeTransport(working={"m1"}))
        # 只留一个候选：并发探活下"选中谁"才是确定的
        router = ModelRouter(make_config(candidates=("m1",)), clock=clock)
        assert router.pick() == "m1"

        def fatal(config, model, messages, **kwargs):
            fake.chat_calls.append(model)
            raise transport.LLMTransportError("HTTP 403：无权访问", 403)

        monkeypatch.setattr(transport, "chat", fatal)
        with pytest.raises(transport.LLMTransportError):
            router.chat([{"role": "user", "content": "问"}])

        clock.advance(200)
        assert "m1" not in router.candidates(), "403 之后 200s 内不该再撞 m1"


# ── 候选发现 ────────────────────────────────────────────────────────────


class TestCandidates:
    def test_explicit_candidates_come_first_then_endpoint(self, patched):
        """人工候选优先，其后仍追加端点发现的模型——前几个都挂了还有后备。"""
        patched(FakeTransport(models=("x1", "x2")))
        router = ModelRouter(make_config(), clock=FakeClock())
        assert router.candidates() == ("m1", "m2", "m3", "x1", "x2")

    def test_falls_back_to_endpoint_models(self, patched):
        patched(FakeTransport(models=("llama3.1-8b", "deepseek-v4-pro-0813")))
        router = ModelRouter(make_config(candidates=()), clock=FakeClock())
        assert router.candidates() == ("deepseek-v4-pro-0813", "llama3.1-8b")

    def test_model_list_is_cached(self, patched):
        fake = patched(FakeTransport(models=("m9",)))
        router = ModelRouter(make_config(candidates=()), clock=FakeClock())

        router.candidates()
        router.candidates()
        assert fake.model_list_calls == 1

    def test_endpoint_failure_degrades_to_explicit_candidates(self, patched, monkeypatch):
        """`/models` 挂了不该让整个问答瘫掉，人工候选仍应可用。"""
        monkeypatch.setattr(
            transport, "chat", FakeTransport(working={"m1"}).chat
        )

        def broken(_config):
            raise transport.LLMTransportError("无法连接 /models")

        monkeypatch.setattr(transport, "list_models", broken)
        router = ModelRouter(make_config(candidates=("m1",)), clock=FakeClock())

        assert router.candidates() == ("m1",)
        assert "拉取模型列表失败" in router.status()["last_error"]


# ── 带轮换的对话 ────────────────────────────────────────────────────────


class TestChatFailover:
    def test_returns_answer_and_model(self, patched):
        patched(FakeTransport(working={"m1"}))
        router = ModelRouter(make_config(), clock=FakeClock())

        content, model = router.chat([{"role": "user", "content": "问"}])
        assert content == "来自 m1 的回答"
        assert model == "m1"

    def test_switches_model_when_call_fails(self, patched, monkeypatch):
        """探活通过但真正调用失败时，必须换下一个候选，而不是把错误抛给用户。"""
        fake = patched(FakeTransport(working={"m1", "m2"}))
        # probe_limit=1：并发探活下若一次探三个，锁定的可能是 m2，轮换就无从观察
        router = ModelRouter(make_config(), probe_limit=1, clock=FakeClock())
        assert router.pick() == "m1"

        original = fake.chat

        def flaky(config, model, messages, **kwargs):
            if model == "m1":
                fake.chat_calls.append(model)
                raise transport.LLMTransportError("HTTP 503：m1 突然挂了", 503)
            return original(config, model, messages, **kwargs)

        monkeypatch.setattr(transport, "chat", flaky)
        content, model = router.chat([{"role": "user", "content": "问"}])

        assert model == "m2"
        assert "m2" in content

    def test_raises_when_nothing_available(self, patched):
        patched(FakeTransport(retryable_fail={"m1", "m2", "m3"}))
        router = ModelRouter(make_config(), clock=FakeClock())

        with pytest.raises(transport.LLMTransportError):
            router.chat([{"role": "user", "content": "问"}])

    def test_fatal_error_stops_failover(self, patched, monkeypatch):
        """不可重试的错误（如 404）换模型也没意义，应立即放弃而不是继续试。"""
        fake = patched(FakeTransport(working={"m1", "m2", "m3"}))
        router = ModelRouter(make_config(), probe_limit=1, clock=FakeClock())
        assert router.pick() == "m1"
        before = len(fake.chat_calls)

        def fatal(config, model, messages, **kwargs):
            fake.chat_calls.append(model)
            raise transport.LLMTransportError("HTTP 404：模型已下线", 404)

        monkeypatch.setattr(transport, "chat", fatal)
        with pytest.raises(transport.LLMTransportError):
            router.chat([{"role": "user", "content": "问"}])

        assert fake.chat_calls[before:] == ["m1"], "不该继续尝试 m2/m3"


# ── 门面编排 ────────────────────────────────────────────────────────────


def make_result(source: str = "《易经》· 乾卦", content: str = "天行健") -> SearchResult:
    return SearchResult(
        book_id="01", book_title="易经", chapter_id="01", chapter_title="乾卦",
        content=content, score=0.9, source=source,
    )


class TestGenerateAnswer:
    def test_uses_llm_when_available(self, patched, monkeypatch):
        patched(FakeTransport(working={"m1"}))
        monkeypatch.setattr(
            "server.services.llm.get_router", lambda: ModelRouter(make_config(), clock=FakeClock())
        )
        from server.services.llm import generate_answer

        assert "来自 m1 的回答" in generate_answer("问题", [make_result()])

    def test_falls_back_when_all_models_fail(self, patched, monkeypatch):
        patched(FakeTransport(retryable_fail={"m1", "m2", "m3"}))
        monkeypatch.setattr(
            "server.services.llm.get_router", lambda: ModelRouter(make_config(), clock=FakeClock())
        )
        from server.services.llm import generate_answer

        answer = generate_answer("问题", [make_result()])
        assert "天行健" in answer
        assert "本地检索结果" in answer

    def test_falls_back_without_api_key(self, patched, monkeypatch):
        patched(FakeTransport(working={"m1"}))
        monkeypatch.setattr(
            "server.services.llm.get_router",
            lambda: ModelRouter(LLMConfig(api_key=""), clock=FakeClock()),
        )
        from server.services.llm import generate_answer

        assert "天行健" in generate_answer("问题", [make_result()])

    def test_with_model_reports_none_on_fallback(self, patched, monkeypatch):
        patched(FakeTransport(retryable_fail={"m1", "m2", "m3"}))
        monkeypatch.setattr(
            "server.services.llm.get_router", lambda: ModelRouter(make_config(), clock=FakeClock())
        )
        from server.services.llm import generate_answer_with_model

        answer, model = generate_answer_with_model("问题", [make_result()])
        assert model is None
        assert "天行健" in answer
