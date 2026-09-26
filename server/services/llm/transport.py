"""传输层：OpenAI 兼容协议的 HTTP 调用（``/models``、``/chat/completions``）。

只用标准库 ``urllib``，不引入额外依赖；网络层与应用层解耦，
上层的 ``ModelRouter`` 不需要知道 HTTP 细节，测试也可以整体替换本模块。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping, Optional, Sequence

from .. import netproxy
from .config import LLMConfig


class LLMTransportError(RuntimeError):
    """传输层错误。``status`` 为 HTTP 状态码（网络异常时为 None）。

    ``retryable`` 表示换一个模型/重试是否有意义：
    4xx（除 429）通常是请求或权限问题，换模型也没用；其余都值得换。
    """

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        if self.status is None:
            return True
        return self.status >= 500 or self.status == 429


def _request(
    config: LLMConfig,
    url: str,
    *,
    payload: Optional[Mapping[str, Any]] = None,
    timeout: float,
) -> Any:
    """发起一次请求并返回解析后的 JSON。"""
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "renshengdaoshi/1.0",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers)

    try:
        with netproxy.build_opener().open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMTransportError(_describe_http_error(exc), exc.code) from exc
    except urllib.error.URLError as exc:
        raise LLMTransportError(f"无法连接 {url}：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LLMTransportError(f"响应不是合法 JSON：{exc}") from exc
    except OSError as exc:
        raise LLMTransportError(f"网络异常：{exc}") from exc


def _describe_http_error(exc: urllib.error.HTTPError) -> str:
    """把上游的错误体提炼成一句人话。"""
    detail = ""
    try:
        body = json.loads(exc.read().decode("utf-8"))
        error = body.get("error")
        if isinstance(error, Mapping):
            detail = str(error.get("message") or "")
        elif error:
            detail = str(error)
        detail = detail or str(body.get("message") or "")
    except Exception:
        detail = ""
    suffix = f"：{detail}" if detail else ""
    return f"HTTP {exc.code}{suffix}"


def list_models(config: LLMConfig) -> tuple[str, ...]:
    """拉取端点暴露的模型 ID 列表；失败时抛 ``LLMTransportError``。"""
    data = _request(config, config.models_url(), timeout=config.models_timeout())
    items = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(items, list):
        return ()
    names = []
    for item in items:
        name = item.get("id") if isinstance(item, Mapping) else None
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(names)


def chat(
    config: LLMConfig,
    model: str,
    messages: Sequence[Mapping[str, str]],
    *,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
) -> str:
    """调用 ``/chat/completions``，返回首条回复的正文。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    else:
        payload["temperature"] = config.temperature

    request_timeout = timeout if timeout is not None else config.timeout
    try:
        data = _request(config, config.chat_url(), payload=payload, timeout=request_timeout)
    except LLMTransportError as exc:
        if not _is_max_tokens_rejection(exc):
            raise
        # 部分新模型只认 max_completion_tokens，去掉 max_tokens 重试一次
        payload.pop("max_tokens", None)
        data = _request(config, config.chat_url(), payload=payload, timeout=request_timeout)

    return _extract_content(data)


def _is_max_tokens_rejection(exc: LLMTransportError) -> bool:
    return exc.status in (400, 404, 422) and "max_tokens" in str(exc)


def _extract_content(data: Any) -> str:
    """从响应里取出正文。

    兼容推理模型：部分模型（如 glm 系列）把内容放在 ``reasoning_content``，
    ``content`` 为空。此时取 ``reasoning_content`` 作为兜底，总比空回答好。
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMTransportError(f"响应结构异常，缺少 choices[0].message：{data}") from exc

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return ""

