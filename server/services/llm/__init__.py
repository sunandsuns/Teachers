"""LLM 服务层对外门面。

调用方（``services/qa.py``）只需要 ``generate_answer`` / ``llm_status``，
不需要知道候选模型怎么挑、HTTP 怎么发、失败怎么降级。

模块分工
--------------------------------------------------------------------------
- ``config``    —— 配置与环境变量，含"派生一个指向别的端点的配置"
- ``transport`` —— OpenAI 兼容协议的 HTTP 细节
- ``router``    —— 模型发现、探活、缓存与失败轮换（单端点）
- ``session``   —— 默认端点与请求级自定义端点之间的选择与隔离
- ``prompt``    —— 提示词构造、对话历史编排与离线降级排版
- ``parse``     —— 从模型回复里抠出 JSON（剥围栏）
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
from .parse import extract_json_block
from .prompt import (
    DEFAULT_LANG,
    MAX_HISTORY_TURNS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EN,
    build_context,
    build_messages,
    build_user_prompt,
    clean_excerpt,
    local_fallback,
    normalize_lang,
    system_prompt,
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
    "DEFAULT_LANG",
    "EndpointOverride",
    "LLMConfig",
    "LLMSession",
    "LLMTransportError",
    "MAX_HISTORY_TURNS",
    "ModelRouter",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_EN",
    "build_context",
    "build_messages",
    "build_user_prompt",
    "chat",
    "clean_excerpt",
    "extract_json_block",
    "generate_answer",
    "generate_answer_with_model",
    "get_router",
    "has_llm",
    "list_models",
    "llm_status",
    "load_config",
    "load_env_file",
    "local_fallback",
    "normalize_lang",
    "probe_endpoint",
    "reset_endpoints",
    "reset_router",
    "resolve_session",
    "system_prompt",
]

#: 模型返回空回答时记在降级文案里的原因。两种语言各一句，
#: 与排版语言保持一致——英文界面里夹一句中文解释很突兀。
EMPTY_ANSWER_NOTE = {
    "zh": "模型返回了空回答",
    "en": "The model returned an empty answer",
}


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
    lang: str = DEFAULT_LANG,
    history: Optional[Sequence[Any]] = None,
    guidance: str = "",
) -> str:
    """生成回答；没有可用模型时降级为本地检索排版，绝不抛异常给调用方。

    ``router`` 省略时用进程级单例（即 ``.env`` 里的默认配置）；传入自定义路由
    即可改用另一套端点（见 ``session.py``），无需改动本函数。

    ``lang`` 决定作答语言，``history`` 是最近几轮问答（追问时接得上上文）。

    ``guidance`` 是这一轮的题型要求（由 ``services/intent.py`` 从问句里认出来的），
    追加在系统提示词之后。留空则不加任何额外指令。
    """
    return _generate(
        question,
        search_results,
        router=router,
        lang=lang,
        history=history,
        guidance=guidance,
    )[0]


def generate_answer_with_model(
    question: str,
    search_results: Sequence[Any],
    *,
    router: Optional[ModelRouter] = None,
    key_hint: str = "LLM_API_KEY",
    lang: str = DEFAULT_LANG,
    history: Optional[Sequence[Any]] = None,
    guidance: str = "",
) -> tuple[str, Optional[str]]:
    """:func:`generate_answer` 的变体，额外返回实际使用的模型名（未用 LLM 时为 ``None``）。

    ``key_hint`` 决定降级文案里提示用户去配哪个 Key——走自定义端点时应该是
    "检查你在设置里填的地址与 Key"，而不是让人去找一个自己没听说过的环境变量。
    """
    return _generate(
        question,
        search_results,
        router=router,
        key_hint=key_hint,
        lang=lang,
        history=history,
        guidance=guidance,
    )


def _generate(
    question: str,
    search_results: Sequence[Any],
    *,
    router: Optional[ModelRouter] = None,
    key_hint: str = "LLM_API_KEY",
    lang: str = DEFAULT_LANG,
    history: Optional[Sequence[Any]] = None,
    guidance: str = "",
) -> tuple[str, Optional[str]]:
    """两个公开入口共用的实现：返回 ``(正文, 模型名)``，降级时模型名为 None。

    合到一处之前，这两个函数各抄了一遍"检查配置 → 组消息 → 调用 → 兜底"，
    而且行为已经悄悄分叉：只有 ``generate_answer`` 会在模型返回空串时降级，
    带模型名的那个会把空回答直接交出去。这里统一为**空回答也降级**——
    对着一个空白回答，用户能做的只有再问一遍。
    """
    target = router if router is not None else get_router()
    answer_lang = normalize_lang(lang)
    if not target.config.enabled:
        return (
            local_fallback(question, search_results, key_hint=key_hint, lang=answer_lang),
            None,
        )

    messages = build_messages(
        question, search_results, lang=answer_lang, history=history, guidance=guidance
    )
    try:
        content, model = target.chat(messages)
    except LLMTransportError as exc:
        return (
            local_fallback(
                question, search_results, str(exc), key_hint=key_hint, lang=answer_lang
            ),
            None,
        )

    if not content or not content.strip():
        return (
            local_fallback(
                question,
                search_results,
                EMPTY_ANSWER_NOTE[answer_lang],
                key_hint=key_hint,
                lang=answer_lang,
            ),
            None,
        )
    return content, model
