"""LLM 配置层：从环境变量与项目根目录的 ``.env`` 读取，零第三方依赖。

配置优先级（高 → 低）
--------------------------------------------------------------------------
1. 真实环境变量（``os.environ``）
2. 项目根目录 ``.env`` 文件
3. 本模块内置默认值

这样既能在开发机上放一份 ``.env`` 图省事，也能在部署时用环境变量覆盖它。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping, Optional

from ...paths import resolve_env_file

#: 默认的 OpenAI 兼容端点
DEFAULT_BASE_URL = "https://api.sllying.bond/v1"

#: 智谱（历史兼容）：未显式配置 LLM_* 时回落到它
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_KEY_VARS = ("ZHIPUAI_API_KEY", "GLM_API_KEY")

#: 自动挑选模型时的偏好顺序（越靠前越优先）。仅用于排序，不做硬性过滤。
MODEL_PREFERENCE: tuple[str, ...] = (
    "deepseek-v4-pro",
    "deepseek",
    "glm-5",
    "glm-4",
    "qwen",
    "kimi",
    "grok",
    "gemini-3",
    "gemini",
    "gpt-oss",
    "claude",
    "hy3",
)

#: 明确不参与探活的模型（多智能体编排、随机路由等，不适合做单轮问答）
MODEL_DENYLIST: frozenset[str] = frozenset({"openrouter-random", "kilo-auto"})


def load_env_file(
    path: Optional[Path] = None,
    *,
    target: Optional[MutableMapping[str, str]] = None,
) -> dict[str, str]:
    """解析 ``.env``（``KEY=VALUE``，支持 ``#`` 注释与成对引号）。

    只把**目标中尚不存在**的键写进去，保证真实环境变量始终优先。
    ``target`` 默认是 ``os.environ``；测试可传入普通 dict 以避免污染进程环境。
    返回本次实际生效的键值，便于测试与排查。

    ``path`` 省略时按 :func:`server.paths.resolve_env_file` 的规则查找，
    以便源码态与打包态共用同一套定位逻辑。
    """
    env_path = path if path is not None else resolve_env_file()
    if env_path is None or not env_path.is_file():
        return {}

    sink = os.environ if target is None else target
    applied: dict[str, str] = {}
    try:
        raw = env_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key not in sink:
            sink[key] = value
            applied[key] = value

    return applied


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _as_float(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value else default
    except (TypeError, ValueError):
        return default


def _as_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


def _split_models(value: Optional[str]) -> tuple[str, ...]:
    """解析逗号/分号/换行分隔的模型名列表，去空去重且保序。"""
    if not value:
        return ()
    parts = value.replace(";", ",").replace("\n", ",").split(",")
    seen: dict[str, None] = {}
    for part in parts:
        name = part.strip()
        if name:
            seen.setdefault(name, None)
    return tuple(seen)


@dataclass(frozen=True)
class LLMConfig:
    """一次调用所需的全部 LLM 参数。"""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = ""
    candidates: tuple[str, ...] = ()
    auto_select: bool = True
    timeout: float = 60.0
    probe_timeout: float = 12.0
    #: 一次「探活 + 生成」的总时间预算（秒）。
    #: 上游整体故障时必须尽快降级到本地检索，而不是让用户干等两分钟。
    total_budget: float = 45.0
    max_tokens: int = 2000
    temperature: float = 0.7
    #: 探活结果缓存秒数：避免每次请求都重新试一遍所有模型
    cache_ttl: float = 300.0
    #: 某个模型失败后的冷却秒数
    failure_cooldown: float = 120.0
    #: 明确不可重试的失败（401/403/404 等）冷却更久，省得反复撞墙
    hard_failure_cooldown: float = 600.0

    @property
    def enabled(self) -> bool:
        """是否具备调用外部 LLM 的条件（有 Key 即视为可用）。"""
        return bool(self.api_key)

    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def models_url(self) -> str:
        return self.base_url.rstrip("/") + "/models"

    def models_timeout(self) -> float:
        """拉模型列表的单独超时：它只是"锦上添花"，不该吃掉生成预算。"""
        return min(self.probe_timeout, 8.0)

    def ordered_candidates(self, available: tuple[str, ...] = ()) -> tuple[str, ...]:
        """给出有序候选模型列表。

        顺序：显式 ``model`` → 显式 ``candidates`` → 端点暴露的 ``available``
        （按 ``MODEL_PREFERENCE`` 排序，未命中的排在后面）。
        """
        result: dict[str, None] = {}
        if self.model:
            result.setdefault(self.model, None)
        for name in self.candidates:
            result.setdefault(name, None)
        for name in _rank_by_preference(available):
            result.setdefault(name, None)
        return tuple(n for n in result if n not in MODEL_DENYLIST)


def _rank_by_preference(models: tuple[str, ...]) -> tuple[str, ...]:
    """按 ``MODEL_PREFERENCE`` 把模型名排序：命中的靠前，未命中的保持原序殿后。"""

    def score(name: str) -> tuple[int, int]:
        lowered = name.lower()
        for index, keyword in enumerate(MODEL_PREFERENCE):
            if keyword in lowered:
                return (0, index)
        return (1, 0)

    return tuple(sorted(models, key=score))


def load_config(env: Optional[Mapping[str, str]] = None) -> LLMConfig:
    """装配配置。``env`` 传入时只读它，便于测试；默认为 ``os.environ``。"""
    if env is None:
        load_env_file()
        source: Mapping[str, str] = os.environ
    else:
        source = env

    api_key = source.get("LLM_API_KEY", "").strip()
    base_url = source.get("LLM_BASE_URL", "").strip()

    # 历史兼容：没配 LLM_API_KEY 时回落到智谱的 OpenAI 兼容端点
    if not api_key:
        for var in GLM_KEY_VARS:
            fallback_key = source.get(var, "").strip()
            if fallback_key:
                api_key = fallback_key
                base_url = base_url or GLM_BASE_URL
                break

    return LLMConfig(
        base_url=base_url or DEFAULT_BASE_URL,
        api_key=api_key,
        model=source.get("LLM_MODEL", "").strip(),
        candidates=_split_models(source.get("LLM_MODEL_CANDIDATES")),
        auto_select=_as_bool(source.get("LLM_AUTO_MODEL"), True),
        timeout=_as_float(source.get("LLM_TIMEOUT"), 60.0),
        probe_timeout=_as_float(source.get("LLM_PROBE_TIMEOUT"), 12.0),
        total_budget=_as_float(source.get("LLM_TOTAL_BUDGET"), 45.0),
        max_tokens=_as_int(source.get("LLM_MAX_TOKENS"), 2000),
        temperature=_as_float(source.get("LLM_TEMPERATURE"), 0.7),
    )
