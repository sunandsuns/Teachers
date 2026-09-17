"""提示词与离线降级回答：纯函数，不涉及网络与状态。

把「怎么问」和「怎么兜底」从调用逻辑里剥离出来，既方便单独测试，
也便于后续调整文风而不触碰路由与传输代码。
"""

from __future__ import annotations

import re
from typing import Any, Sequence

SYSTEM_PROMPT = """你是一位"人生导师"，擅长从中国传统文化经典中提取智慧来回答现代人的生活问题。

当用户提问时，你会收到若干从经典笔记中检索到的相关段落。请基于这些段落，给出一个结构化的回答：

1. **你的处境**：用1-2句话复述用户的问题，点出核心矛盾。
2. **经典怎么说**：引用1-3条最相关的经典智慧，每条包含出处、原文、释义。
3. **我的分析**：结合用户具体处境，分析这些智慧为什么适用，揭示了什么规律。
4. **建议你怎么办**：给出2-3条可行动的建议。

要求：
- 引用原文时逐字准确，标注出处。
- 先给经典智慧（客观），再给个人分析（主观），分开标注。
- 不编造原文，只引用检索到的内容。
- 语气像一个读过很多书的朋友在聊天，不说教。
- 直接输出 Markdown 正文，不要加"好的""以下是"这类开场白。
"""

#: 摘录需要剔除的整行噪声：Markdown 标题、表格行、分隔线
_HEADING_OR_TABLE = re.compile(r"^(#{1,6}\s|\|)")
_SEPARATOR = re.compile(r"^(?:-{3,}|\*{3,}|_{3,}|(?:\|\s*:?-+:?\s*)+\|)$")
_BLOCKQUOTE_PREFIX = re.compile(r"^>+\s*")
_BULLET_PREFIX = re.compile(r"^[-*+]\s+")
_INLINE_MARKS = re.compile(r"[*`]")
_WHITESPACE = re.compile(r"\s+")


def clean_excerpt(text: str, limit: int = 220) -> str:
    """把检索到的段落整理成适合直接引用的单段文本。

    检索单元本身是原始 Markdown 片段，可能以标题行、表格行或引用符开头；
    直接塞进 `> ` 引用块会产生错乱的嵌套层级（例如出现 `> ### 小标题`）。
    这里统一清洗为纯段落：剥掉引用符与列表符号、丢弃标题/表格/分隔线、
    去掉强调标记、压缩空白，并按上限截断。
    """
    lines: list[str] = []
    for raw in text.splitlines():
        line = _BLOCKQUOTE_PREFIX.sub("", raw.strip())
        if not line or _HEADING_OR_TABLE.match(line) or _SEPARATOR.match(line):
            continue
        lines.append(_BULLET_PREFIX.sub("", line))

    merged = _WHITESPACE.sub(" ", _INLINE_MARKS.sub("", " ".join(lines))).strip()
    return f"{merged[:limit].rstrip()}…" if len(merged) > limit else merged


def build_context(search_results: Sequence[Any]) -> str:
    """把检索结果拼成给模型的上下文。"""
    parts = [
        f"【片段{i}】出处：{result.source}\n内容：{result.content}"
        for i, result in enumerate(search_results, 1)
    ]
    return "\n---\n".join(parts)


def build_user_prompt(question: str, search_results: Sequence[Any]) -> str:
    """组装用户侧提示词。"""
    return (
        f"用户问题：{question}\n\n"
        f"检索到的相关经典段落：\n\n{build_context(search_results)}\n\n"
        f"请基于以上检索结果回答用户的问题。"
    )


def local_fallback(
    question: str,
    search_results: Sequence[Any],
    error: str = "",
    *,
    key_hint: str = "LLM_API_KEY",
) -> str:
    """降级回答：没有可用 LLM 时，直接把检索结果排版返回。"""
    if not search_results:
        return "抱歉，在经典笔记中没有找到与您问题直接相关的内容。请尝试换个关键词提问。"

    parts: list[str] = []
    if error:
        parts.append(f"(LLM 生成不可用：{error}，以下为本地检索结果)\n")

    parts.append(f"## 你的问题\n\n{question}\n")
    parts.append("## 经典怎么说\n")
    for i, result in enumerate(search_results, 1):
        excerpt = clean_excerpt(result.content)
        parts.append(f"### 片段{i} —— {result.source}\n")
        parts.append("\n".join(f"> {line}" for line in excerpt.splitlines()) + "\n")
    parts.append("## 建议\n")
    parts.append("以上是从经典笔记中检索到的最相关段落。请参考原文出处的智慧来思考您的问题。")
    parts.append(f"\n*(配置 {key_hint} 后可获得 AI 智能分析回答)*")

    return "\n".join(parts)
