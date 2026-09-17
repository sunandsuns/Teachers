"""LLM 服务层对外门面。

调用方（``services/qa.py``）只需要 ``generate_answer`` / ``llm_status``，
不需要知道候选模型怎么挑、HTTP 怎么发、失败怎么降级。

模块分工
--------------------------------------------------------------------------
- ``config``    —— 配置与环境变量，含"派生一个指向别的端点的配置"
- ``transport`` —— OpenAI 兼容协议的 HTTP 细节
- ``router``    —— 模型发现、探活、缓存与失败轮换（单端点）
- ``session``   —— 默认端点与请求级自定义端点之间的选择与隔离
- ``prompt``    —— 提示词构造与离线降级排版
- 本模块        —— 把上面几层组装成"问一个问题，拿到一个回答"
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from . import transport
from .config import (
    DEFAULT_BASE_URL,
    LLMConfig,
    load_config,
    load_env_file,
)
from .prompt import (
    SYSTEM_PROMPT,
    build_context,
    build_user_prompt,
    clean_excerpt,
    local_fallback,
)
from .router import ModelRouter, get_router, reset_router
from .session import (
    EndpointOverride,
    LLMSession,
    probe_endpoint,
    reset_endpoints,
    resolve_session,
)
from .transport import LLMTransportError, chat, list_models

__all__ = [
    "DEFAULT_BASE_URL",
    "EndpointOverride",
    "LLMConfig",
    "LLMSession",
    "LLMTransportError",
    "ModelRouter",
    "SYSTEM_PROMPT",
    "build_context",
    "build_user_prompt",
    "chat",
    "clean_excerpt",
    "generate_answer",
    "generate_answer_with_model",
    "get_router",
    "has_llm",
    "list_models",
    "llm_status",
    "load_config",
    "load_env_file",
    "local_fallback",
    "probe_endpoint",
    "reset_endpoints",
    "reset_router",
    "resolve_session",
]


def has_llm() -> bool:
    """是否已配置可用的 LLM（只看配置，不发网络请求）。

    想知道"此刻真的有模型能用"，用 :func:`llm_status` 或 ``get_router().pick()``。
    """
    return get_router().config.enabled


def llm_status(refresh: bool = False) -> dict:
    """当前 LLM 状态：是否启用、正在用哪个模型、有多少候选、最近一次错误。"""
    router = get_router()
    status = router.status()
    status["model"] = router.pick(force=refresh) if refresh else status["model"]
    return status


def generate_answer(
    question: str,
    search_results: Sequence[Any],
    *,
    router: Optional[ModelRouter] = None,
) -> str:
    """生成回答；没有可用模型时降级为本地检索排版，绝不抛异常给调用方。

    ``router`` 省略时用进程级单例（即 ``.env`` 里的默认配置）；传入自定义路由
    即可改用另一套端点（见 ``session.py``），无需改动本函数。
    """
    return _generate(question, search_results, router=router)[0]


def generate_answer_with_model(
    question: str,
    search_results: Sequence[Any],
    *,
    router: Optional[ModelRouter] = None,
    key_hint: str = "LLM_API_KEY",
) -> tuple[str, Optional[str]]:
    """:func:`generate_answer` 的变体，额外返回实际使用的模型名（未用 LLM 时为 ``None``）。

    ``key_hint`` 决定降级文案里提示用户去配哪个 Key——走自定义端点时应该是
    "检查你在设置里填的地址与 Key"，而不是让人去找一个自己没听说过的环境变量。
    """
    return _generate(question, search_results, router=router, key_hint=key_hint)


def _generate(
    question: str,
    search_results: Sequence[Any],
    *,
    router: Optional[ModelRouter] = None,
    key_hint: str = "LLM_API_KEY",
) -> tuple[str, Optional[str]]:
    """两个公开入口共用的实现：返回 ``(正文, 模型名)``，降级时模型名为 None。

    合到一处之前，这两个函数各抄了一遍"检查配置 → 组消息 → 调用 → 兜底"，
    而且行为已经悄悄分叉：只有 ``generate_answer`` 会在模型返回空串时降级，
    带模型名的那个会把空回答直接交出去。这里统一为**空回答也降级**——
    对着一个空白回答，用户能做的只有再问一遍。
    """
    target = router if router is not None else get_router()
    if not target.config.enabled:
        return local_fallback(question, search_results, key_hint=key_hint), None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, search_results)},
    ]
    try:
        content, model = target.chat(messages)
    except LLMTransportError as exc:
        return local_fallback(question, search_results, str(exc), key_hint=key_hint), None

    if not content or not content.strip():
        return local_fallback(question, search_results, "模型返回了空回答", key_hint=key_hint), None
    return content, model
