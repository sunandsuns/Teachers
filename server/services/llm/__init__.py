"""LLM 服务层对外门面。

调用方（``routers/ask.py``）只需要 ``generate_answer`` / ``has_llm`` / ``llm_status``，
不需要知道候选模型怎么挑、HTTP 怎么发、失败怎么降级。

模块分工
--------------------------------------------------------------------------
- ``config``    —— 配置与环境变量
- ``transport`` —— OpenAI 兼容协议的 HTTP 细节
- ``router``    —— 模型发现、探活、缓存与失败轮换
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
from .transport import LLMTransportError, chat, list_models

__all__ = [
    "DEFAULT_BASE_URL",
    "LLMConfig",
    "LLMTransportError",
    "ModelRouter",
    "SYSTEM_PROMPT",
    "build_context",
    "build_user_prompt",
    "chat",
    "clean_excerpt",
    "generate_answer",
    "get_router",
    "has_llm",
    "list_models",
    "llm_status",
    "load_config",
    "load_env_file",
    "local_fallback",
    "reset_router",
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


def generate_answer(question: str, search_results: Sequence[Any]) -> str:
    """生成回答；没有可用模型时降级为本地检索排版，绝不抛异常给调用方。"""
    router = get_router()
    if not router.config.enabled:
        return local_fallback(question, search_results)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, search_results)},
    ]

    try:
        content, _model = router.chat(messages)
    except LLMTransportError as exc:
        return local_fallback(question, search_results, str(exc))

    if not content or not content.strip():
        return local_fallback(question, search_results, "模型返回了空回答")
    return content


def generate_answer_with_model(question: str, search_results: Sequence[Any]) -> tuple[str, Optional[str]]:
    """:func:`generate_answer` 的变体，额外返回实际使用的模型名（未用 LLM 时为 ``None``）。"""
    router = get_router()
    if not router.config.enabled:
        return local_fallback(question, search_results), None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, search_results)},
    ]
    try:
        return router.chat(messages)
    except LLMTransportError as exc:
        return local_fallback(question, search_results, str(exc)), None
