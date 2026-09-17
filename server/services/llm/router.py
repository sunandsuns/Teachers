"""模型路由：自动发现并挑选当前可用的上游模型。

为什么需要它
--------------------------------------------------------------------------
聚合端点的模型可用性会随时间抖动——同一时刻有的模型 403、有的 503、
有的直接消失。写死一个模型名，等于把应用绑死在某一次快照上。

本模块的策略是"**候选有序 + 逐个探活 + 结果缓存 + 失败轮换**"：

1. **候选来源**（见 ``LLMConfig.ordered_candidates``）：
   显式 ``LLM_MODEL`` → 显式 ``LLM_MODEL_CANDIDATES`` → 端点 ``/models``
   按偏好排序。前两者优先级更高，方便人工干预。
2. **探活**：用一次极短的对话验证模型真的能出字，而不是只看它出现在列表里。
   **并发进行**，理由见 :data:`PROBE_BUDGET_SHARE`。
3. **缓存**：选中的模型缓存 ``cache_ttl`` 秒，避免每个请求都重新探一遍。
4. **轮换**：调用失败的模型进冷却队列，下一次自动跳到下一个候选。
5. **时间预算**：整段"探活 + 生成"受 ``total_budget`` 约束。上游集体故障时
   宁可尽快降级到本地检索，也不让用户的请求无限期挂住。

线程安全：所有共享状态都在 ``_lock`` 内读写，探活也在锁内完成，
以换取"同一时刻只探一次"的确定性——本应用为单机小流量，这点代价可以接受。
探活线程本身只做一次 HTTP 调用、不碰任何共享状态，结果经队列回传。
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Mapping, Optional, Sequence

from . import transport
from .config import LLMConfig, load_config

#: 一次挑选最多探活几个候选，避免上游整体故障时长时间阻塞
DEFAULT_PROBE_LIMIT = 4

#: 探活阶段最多占用总预算的比例，其余留给真正生成回答。
#:
#: 为什么探活要并发
#: ------------------------------------------------------------------
#: 聚合端点上的模型有两种坏法：**快速报错**（4xx/5xx，不费时间）和
#: **连得上但不回应**（挂到读超时才放手，费满 probe_timeout）。
#: 早先探活是串行的，于是后一种坏法是致命的：4 个候选里有 3 个在挂，
#: 光探活就要烧掉 3 × probe_timeout = 36s，加上 ``/models`` 的开销，
#: 45s 的总预算在探活阶段就见底了——**明明有可用模型，生成一步却没有余量，
#: 用户等满 45 秒拿到的仍是本地降级答案**。
#:
#: 并发探活把这个上限从"候选数 × 超时"压回"单次超时"，同时取最先返回的那个，
#: 响应快的模型优先。本比例是第二道保险：即使有人把 probe_timeout 配得很大，
#: 探活也不可能吃掉整个预算。
PROBE_BUDGET_SHARE = 0.34

#: 探活用的最小请求。16 而非 1：推理模型会先花 token 思考，
#: 预算太小会导致 content 为空、被误判为不可用。
_PROBE_MESSAGES: tuple[Mapping[str, str], ...] = (
    {"role": "user", "content": "hi"},
)
_PROBE_MAX_TOKENS = 16


class ModelRouter:
    """在给定配置下，维护"当前可用模型"的状态机。"""

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        *,
        probe_limit: int = DEFAULT_PROBE_LIMIT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config if config is not None else load_config()
        self._probe_limit = max(1, probe_limit)
        self._clock = clock
        self._lock = threading.RLock()

        self._current: str = ""
        self._current_expires: float = 0.0
        self._cooldown: dict[str, float] = {}
        self._available: tuple[str, ...] = ()
        self._available_expires: float = 0.0
        self._last_error: str = ""

    # ── 配置与状态 ──────────────────────────────────────────────────

    @property
    def config(self) -> LLMConfig:
        return self._config

    def now(self) -> float:
        """内部时钟的当前读数。

        对外暴露是为了让调用方能构造 ``pick(deadline=...)`` ——超时预算用的是
        本路由器自己的时钟轴（测试里可能被换成假时钟），用 ``time.monotonic()``
        去拼 deadline 会在测试中直接失效。
        """
        return self._clock()

    def reload(self, config: Optional[LLMConfig] = None) -> None:
        """重新读取配置并清空所有缓存状态（``.env`` 改动后调用）。"""
        with self._lock:
            self._config = config if config is not None else load_config()
            self._current = ""
            self._current_expires = 0.0
            self._cooldown.clear()
            self._available = ()
            self._available_expires = 0.0
            self._last_error = ""

    def status(self) -> dict:
        """给接口层用的状态快照。"""
        with self._lock:
            return {
                "enabled": self._config.enabled,
                "base_url": self._config.base_url,
                "model": self._current,
                "available_models": len(self._available),
                "cooling_down": sorted(self._cooldown),
                "last_error": self._last_error,
            }

    # ── 模型发现 ────────────────────────────────────────────────────

    def available_models(self, *, force: bool = False) -> tuple[str, ...]:
        """端点暴露的模型列表（带缓存）。

        ``/models`` 不可用时返回空元组——不抛异常，因为候选还有
        ``LLM_MODEL`` 与 ``LLM_MODEL_CANDIDATES`` 两条人工兜底路径。
        """
        with self._lock:
            now = self._clock()
            if not force and self._available and now < self._available_expires:
                return self._available
            try:
                found = transport.list_models(self._config)
            except transport.LLMTransportError as exc:
                self._last_error = f"拉取模型列表失败：{exc}"
                found = ()
            self._available = found
            # 失败也照样进缓存：省得每个请求都去撞一次已经挂掉的 /models
            self._available_expires = now + self._config.cache_ttl
            return found

    def candidates(self, *, force: bool = False) -> tuple[str, ...]:
        """当前有序候选列表（已剔除冷却中的模型）。"""
        with self._lock:
            ordered = self._config.ordered_candidates(self.available_models(force=force))
            now = self._clock()
            return tuple(name for name in ordered if self._cooldown.get(name, 0.0) <= now)

    # ── 挑选与轮换 ──────────────────────────────────────────────────

    def pick(self, *, force: bool = False, deadline: Optional[float] = None) -> str:
        """返回当前可用的模型名；全部不可用时返回空串。

        ``force=True`` 时忽略缓存，重新探活。
        ``deadline`` 是 ``self._clock()`` 时间轴上的绝对时刻，超过即停止探活，
        避免上游整体故障时把用户的时间耗在无谓的重试上。

        流程分四步，各自成方法：**复用缓存 → 圈定候选并能算出余量 →
        并发探活 → 据结果落状态**。原先这些揉在一个六十行的方法里，
        四处重复的"清空当前模型"要逐个比对才能确认没有分叉。
        """
        with self._lock:
            if not self._config.enabled:
                return ""

            if deadline is None:
                deadline = self._clock() + self._config.total_budget

            cached = self._cached_current(force=force)
            if cached:
                return cached

            # 先取候选（可能触发一次 ``/models`` 请求），再算剩余预算——
            # 否则那几秒不计入预算，deadline 就成了纸面上的约束。
            batch = self.candidates(force=force)[: self._probe_limit]
            remaining = deadline - self._clock()

            if not batch or remaining <= 0:
                self._discard_current()
                self._note_no_candidate(remaining)
                return ""

            timeout = min(
                self._config.probe_timeout,
                max(1.0, remaining * PROBE_BUDGET_SHARE),
            )
            winner, outcomes = self._probe_batch(batch, timeout)
            self._record_outcomes(outcomes)

            if winner is not None:
                self._accept(winner)
                return winner

            self._discard_current()
            self._summarize_all_failed(outcomes)
            return ""

    # ── pick 的四个步骤 ─────────────────────────────────────────────

    def _cached_current(self, *, force: bool) -> str:
        """上次选中的模型若还在缓存期且没被拉黑，直接沿用。"""
        if force or not self._current:
            return ""
        now = self._clock()
        if now < self._current_expires and self._cooldown.get(self._current, 0.0) <= now:
            return self._current
        return ""

    def _discard_current(self) -> None:
        """撤销"当前模型"：探活失败、或调用方已明确放弃它。"""
        self._current = ""
        self._current_expires = 0.0

    def _note_no_candidate(self, remaining: float) -> None:
        """连候选都没有时，把原因写清楚——是超预算，还是压根挑不出模型。"""
        if remaining <= 0:
            self._last_error = "探活超出时间预算，提前降级到本地检索"
        elif not self._last_error:
            self._last_error = "所有候选模型均不可用"

    def _record_outcomes(
        self, outcomes: Mapping[str, Optional[transport.LLMTransportError]]
    ) -> None:
        """把这一批的探活结果落进冷却表与错误状态。"""
        for name, failure in outcomes.items():
            if failure is None:
                continue
            # 带上 status 判断硬软冷却：403/404 这类换模型也修不好，
            # 只给软冷却的话每两分钟就会再撞一次同一堵墙。
            self._mark_failed_locked(name, hard=not failure.retryable)
            self._last_error = f"{name} 探活失败：{failure}"

    def _accept(self, model: str) -> None:
        """选中一个模型并开始计时。"""
        self._current = model
        self._current_expires = self._clock() + self._config.cache_ttl
        self._last_error = ""

    def _summarize_all_failed(
        self, outcomes: Mapping[str, Optional[transport.LLMTransportError]]
    ) -> None:
        """一个都没探出来时，把"探了哪些"写进状态。

        出问题时能一眼看出是候选太少还是候选全挂，省得靠猜。
        """
        failed = [name for name, failure in outcomes.items() if failure is not None]
        if failed:
            self._last_error = "所有候选模型均不可用（已探活：%s）" % ", ".join(sorted(failed))
        elif not self._last_error:
            self._last_error = "所有候选模型均不可用"

    def mark_failed(self, model: str, *, hard: bool = False) -> None:
        """外部调用失败后主动上报，使其进入冷却。

        ``hard=True`` 表示明确不可重试的失败（权限、模型不存在等），
        冷却时间更长，省得每个请求都去撞同一堵墙。
        """
        with self._lock:
            self._mark_failed_locked(model, hard=hard)

    def _mark_failed_locked(self, model: str, *, hard: bool = False) -> None:
        seconds = (
            self._config.hard_failure_cooldown if hard else self._config.failure_cooldown
        )
        self._cooldown[model] = self._clock() + seconds
        if self._current == model:
            self._current = ""
            self._current_expires = 0.0

    def _probe_batch(
        self, candidates: Sequence[str], timeout: float
    ) -> tuple[Optional[str], dict[str, Optional[transport.LLMTransportError]]]:
        """并发探活一批候选。

        Returns:
            ``(最快可用的模型名或 None, {模型名: 失败原因或 None})``。
            已经拿到可用模型就立即返回，剩下的探活留在后台自行结束——
            那些卡住的候选没必要等它们熬满超时。

        调用方必须已持有 ``_lock``：本方法只读配置、只写局部结果，
        不碰任何共享状态。
        """
        sink: "queue.Queue[tuple[str, Optional[transport.LLMTransportError]]]" = queue.Queue()
        threads = [
            threading.Thread(
                target=_probe_worker,
                args=(self._config, name, timeout, sink),
                name=f"llm-probe-{name}",
                daemon=True,
            )
            for name in candidates
        ]
        for thread in threads:
            thread.start()

        outcomes: dict[str, Optional[transport.LLMTransportError]] = {}
        winner: Optional[str] = None
        for _ in range(len(threads)):
            name, failure = sink.get()
            outcomes[name] = failure
            if failure is None:
                winner = name
                break
        return winner, outcomes

    # ── 带轮换的对话 ────────────────────────────────────────────────

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        budget: Optional[float] = None,
    ) -> tuple[str, str]:
        """发起对话，失败时自动换下一个候选模型。

        整段流程受 ``budget`` 秒（默认 ``config.total_budget``）约束——上游
        集体故障时宁可快速降级，也不让请求无限期挂住。

        Returns:
            ``(回答正文, 实际使用的模型名)``；均无可用模型时抛
            ``LLMTransportError``。
        """
        tried: list[str] = []
        last_error: Optional[Exception] = None
        span = budget if budget is not None else self._config.total_budget
        deadline = self._clock() + max(1.0, span)

        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                if last_error is None:
                    last_error = transport.LLMTransportError("调用超出时间预算")
                break

            model = self.pick(deadline=deadline)
            if not model:
                break
            if model in tried:
                # 该模型是本轮唯一的候选且刚失败过，避免死循环
                break
            tried.append(model)
            try:
                content = transport.chat(
                    self._config, model, messages,
                    max_tokens=max_tokens, temperature=temperature,
                    timeout=min(self._config.timeout, max(1.0, deadline - self._clock())),
                )
            except transport.LLMTransportError as exc:
                last_error = exc
                self.mark_failed(model, hard=not exc.retryable)
                if not exc.retryable:
                    break
                continue
            return content, model

        detail = f"（已尝试：{', '.join(tried)}）" if tried else ""
        reason = str(last_error) if last_error else "没有可用模型"
        raise transport.LLMTransportError(f"{reason}{detail}")


def _probe_worker(
    config: LLMConfig,
    model: str,
    timeout: float,
    sink: "queue.Queue[tuple[str, Optional[transport.LLMTransportError]]]",
) -> None:
    """探活线程体：用一次极小请求确认模型真能出字，结果塞进队列。

    刻意放在类外、只做一次 HTTP 调用、不读写路由器状态，因此不需要持锁——
    ``pick()`` 正握着 ``_lock`` 等结果，探活线程若回头取锁就会自锁。
    """
    try:
        content = transport.chat(
            config,
            model,
            _PROBE_MESSAGES,
            max_tokens=_PROBE_MAX_TOKENS,
            temperature=0.0,
            timeout=timeout,
        )
    except transport.LLMTransportError as exc:
        sink.put((model, exc))
        return
    except Exception as exc:  # noqa: BLE001 — 线程里逃逸的异常会变成静默丢结果
        sink.put((model, transport.LLMTransportError(f"{type(exc).__name__}: {exc}")))
        return

    if content and content.strip():
        sink.put((model, None))
    else:
        # 推理模型可能只回了思考过程、或干脆空串，同样视为不可用
        sink.put((model, transport.LLMTransportError("模型返回空回答")))


# ── 全局单例 ────────────────────────────────────────────────────────────

_router: Optional[ModelRouter] = None
_router_lock = threading.Lock()


def get_router() -> ModelRouter:
    """获取全局路由单例。"""
    global _router
    with _router_lock:
        if _router is None:
            _router = ModelRouter()
        return _router


def reset_router() -> None:
    """丢弃全局单例（测试与热重载用）。"""
    global _router
    with _router_lock:
        _router = None
