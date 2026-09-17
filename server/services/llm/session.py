"""端点会话：决定「这一次调用用哪套模型配置」。

为什么单独成一层
--------------------------------------------------------------------------
默认配置来自 ``.env``，进程内只需要一份，用全局单例即可。但用户还能在界面上
填自己的接口地址与 Key——那一套**只对当前这次请求有效**，绝不能写回全局，
否则等于把一个人的 Key 摊给了所有人。

本层就是在这两者之间做选择，并解决随之而来的两个问题：

1. **状态隔离**。自定义端点的探活结果与失败冷却必须自成一格。若与默认端点
   共用路由器的冷却表，用户在自定义端点上的失败会把默认端点上的模型一并
   拉黑——切回默认还得白等一轮冷却。
2. **探活成本**。探活一次要几秒。若每个请求都新建路由器，用户会觉得
   "自定义比默认慢很多"。故按端点缓存路由器实例，让同一个端点只探一次。

缓存里会留下列人填过的 API Key（``LLMConfig`` 持有），所以设了容量上限与
存活时间。它纯粹是加速器：被淘汰后下次重建即可，不影响正确性。
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .config import LLMConfig
from .router import ModelRouter, get_router

#: 同时缓存多少个自定义端点
ENDPOINT_CACHE_LIMIT = 8
#: 一个自定义端点的路由器最长留多久（秒）
ENDPOINT_TTL = 900.0

#: 「测试连接」的时间上限。刻意远小于正常问答的总预算：
#: 那是用户盯着一个按钮等结果的场景，让人干等 45 秒等于告诉对方"按钮坏了"。
PROBE_BUDGET = 20.0


def _clean(value: Any) -> str:
    """把用户输入规整成字符串：非字符串按空处理，顺带去空白。"""
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class EndpointOverride:
    """请求级的自定义端点，字段全部来自用户输入。"""

    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_payload(cls, payload: Optional[Mapping[str, Any]]) -> Optional["EndpointOverride"]:
        """从请求体里解析；字段缺失或不完整时返回 ``None``（表示"用默认配置"）。

        只填了 URL 或只填了 Key 都算没填：拿着半截配置去试探，只会换来一个
        必然失败的请求，不如干脆按默认走，让用户拿到一个能用的回答。
        """
        if not payload:
            return None
        override = cls(
            base_url=_clean(payload.get("base_url")),
            api_key=_clean(payload.get("api_key")),
            model=_clean(payload.get("model")),
        )
        return override if override.usable else None

    @property
    def usable(self) -> bool:
        """接口地址与 Key 都填了才算数。"""
        return bool(self.base_url and self.api_key)

    def fingerprint(self) -> str:
        """缓存键。Key 只以摘要形式参与，避免明文散落在状态快照与日志里。"""
        digest = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:16]
        return "%s|%s|%s" % (self.base_url.rstrip("/"), self.model, digest)


@dataclass(frozen=True)
class LLMSession:
    """一次调用所用的模型环境。

    ``custom`` 为真表示这套配置来自本次请求而非 ``.env``；调用方据此决定
    降级文案——自定义端点连不上时说"你填的地址不可用"，比说"没配 Key"有用。
    """

    router: ModelRouter
    config: LLMConfig
    custom: bool


class EndpointRegistry:
    """按端点缓存路由器实例。"""

    def __init__(
        self,
        *,
        limit: int = ENDPOINT_CACHE_LIMIT,
        ttl: float = ENDPOINT_TTL,
        clock=time.monotonic,
    ) -> None:
        self._limit = max(1, limit)
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, ModelRouter]] = {}

    def session(self, override: Optional[EndpointOverride] = None) -> LLMSession:
        """给出本次调用该用的路由器。

        没有覆盖（或覆盖不完整）时返回进程级单例，行为与加这个功能之前完全一致。
        """
        if override is None or not override.usable:
            router = get_router()
            return LLMSession(router=router, config=router.config, custom=False)

        # 运行参数（超时、预算、token 上限）沿用默认配置：它们描述的是
        # "这个应用愿意等多久"，与用户填的地址无关。
        config = get_router().config.with_endpoint(
            override.base_url, override.api_key, override.model
        )
        key = override.fingerprint()
        now = self._clock()

        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and now - entry[0] <= self._ttl:
                return LLMSession(router=entry[1], config=entry[1].config, custom=True)

            router = ModelRouter(config)
            self._entries[key] = (now, router)
            self._prune_locked(now)

        return LLMSession(router=router, config=config, custom=True)

    def clear(self) -> None:
        """丢弃全部缓存（测试与 ``.env`` 热更新后调用）。"""
        with self._lock:
            self._entries.clear()

    def _prune_locked(self, now: float) -> None:
        """淘汰过期项；仍然超出上限时，按创建时间从最旧的开始丢。"""
        for key in [k for k, (created, _) in self._entries.items() if now - created > self._ttl]:
            self._entries.pop(key, None)
        while len(self._entries) > self._limit:
            oldest = min(self._entries, key=lambda k: self._entries[k][0])
            self._entries.pop(oldest, None)


# ── 全局单例 ────────────────────────────────────────────────────────────

_registry: Optional[EndpointRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> EndpointRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = EndpointRegistry()
        return _registry


def reset_endpoints() -> None:
    """丢弃端点缓存（测试与热更新用）。"""
    global _registry
    with _registry_lock:
        _registry = None


def resolve_session(override: Optional[EndpointOverride] = None) -> LLMSession:
    """便捷入口：取本次调用该用的会话。"""
    return get_registry().session(override)


def probe_endpoint(override: Optional[EndpointOverride]) -> dict[str, Any]:
    """测试用户填的端点：能不能连、有哪些模型、挑得中哪一个。

    Returns:
        ``{ok, base_url, model, models, error}``。无论成功失败都不抛异常——
        它是给界面上的"测试连接"按钮用的，失败信息本身就是它要交付的结果。
    """
    if override is None or not override.usable:
        return {
            "ok": False,
            "base_url": "",
            "model": "",
            "models": [],
            "error": "请先填写接口地址与 API Key",
        }

    session = resolve_session(override)
    router = session.router

    # 先列模型：即使一个都挑不出来，把端点暴露的清单还给用户也有诊断价值。
    models = router.available_models(force=True)
    model = router.pick(force=True, deadline=router.now() + PROBE_BUDGET)

    return {
        "ok": bool(model),
        "base_url": session.config.base_url,
        "model": model,
        "models": list(models),
        "error": "" if model else (router.status()["last_error"] or "没有可用的模型"),
    }
