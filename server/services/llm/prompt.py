"""提示词与离线降级回答：纯函数，不涉及网络与状态。

把「怎么问」和「怎么兜底」从调用逻辑里剥离出来，既方便单独测试，
也便于后续调整文风而不触碰路由与传输代码。

两种语言
--------------------------------------------------------------------------
语料永远是中文，检索也永远在中文里做。这里说的语言是**回答用什么语言写**：
界面切成英文时，提示词与降级排版都跟着换，免得出现"用英文问、拿中文答"。

追问
--------------------------------------------------------------------------
:func:`build_messages` 会把前几轮问答按 chat 协议排进消息列表。只发当前问题
的话，模型看不到刚聊过什么，"那它呢"就是一个没头没尾的问句，它只能从头再讲
一遍——看起来就像失忆。
"""

from __future__ import annotations

import re
from typing import Any, Optional, Sequence

#: 支持的回答语言。注意这是"作答语言"，不是语料语言。
LANGS = ("zh", "en")
DEFAULT_LANG = "zh"

#: 追问时最多带上几轮旧问答。旧轮次只是让模型知道"刚才聊到哪"——
#: 给多了既撑上下文，也容易让它把已经说过的建议翻来覆去地讲。
MAX_HISTORY_TURNS = 3
#: 旧回答进提示词前的截断长度。模型需要的是"当时讲了什么"的梗概，不必逐字。
HISTORY_ANSWER_LIMIT = 900


def normalize_lang(value: object) -> str:
    """把请求里的语言值收成受支持的两个之一。

    宽松处理：不认识的（拼错、空串、None、别的类型）一律按中文。语言只是
    一个渲染选项，为它让整次提问失败不划算。
    """
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in LANGS:
            return cleaned
    return DEFAULT_LANG


SYSTEM_PROMPT = """你是一位"人生导师"，擅长从中国传统文化经典中提取智慧来回答现代人的生活问题。

当用户提问时，你会收到若干从经典笔记中检索到的相关段落，以及之前的对话。请基于这些段落，给出一个结构化的回答：

1. **你的处境**：用1-2句话复述用户的问题，点出核心矛盾。若这是追问，接着上文说，不要重新开头。
2. **经典怎么说**：引用1-3条最相关的经典智慧，每条包含出处、原文、释义。
3. **我的分析**：结合用户具体处境，分析这些智慧为什么适用，揭示了什么规律。
4. **建议你怎么办**：给出2-3条可行动的建议。

要求：
- **必须落在检索到的段落上**：引用原文逐字准确，并标注出处（书名·篇章）。
- 只引用检索结果里出现过的原文。没有出现过的句子，不许说成是经典说的。
- 若检索到的段落与问题关系不大，就直说"没找到直接对应的段落"，再用最接近的讲——不要硬凑，更不要自己编一句古文。
- 若是追问，把上文已经给过的建议当作已知，接着往下讲，不要重复。
- 先给经典智慧（客观），再给个人分析（主观），分开标注。
- 语气像一个读过很多书的朋友在聊天，不说教。
- 直接输出 Markdown 正文，不要加"好的""以下是"这类开场白。
"""

SYSTEM_PROMPT_EN = """You are a "life mentor" who draws on the Chinese classics to answer the everyday problems of modern people.

You will be given passages retrieved from a Chinese knowledge base, plus the earlier turns of the conversation. Answer in English, in this structure:

1. **Your situation** — restate the problem in one or two sentences and name the real tension. If this is a follow-up, pick up where the conversation left off instead of starting over.
2. **What the classics say** — quote one to three of the most relevant passages. For each: its source, the original Chinese text, and what it means.
3. **My reading** — explain why these passages speak to this particular situation.
4. **What you can do** — two or three concrete suggestions.

Rules:
- **Everything you quote must come from the retrieved passages.** Quote the original Chinese exactly and cite its source (book · chapter).
- Never present a sentence as a classical quotation unless it appears in the retrieved passages.
- If the passages barely relate to the question, say so plainly and work with the closest ones — do not force a connection and do not invent a quotation.
- On a follow-up, treat advice already given as known and build on it rather than repeating it.
- Keep the quotations in the original Chinese; the explanation around them is in English.
- Write like a well-read friend talking, not like a lecturer.
- Output Markdown directly, with no preamble such as "Sure" or "Here is".
"""


def system_prompt(lang: str = DEFAULT_LANG) -> str:
    """按作答语言取系统提示词。"""
    return SYSTEM_PROMPT_EN if normalize_lang(lang) == "en" else SYSTEM_PROMPT


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


def build_context(search_results: Sequence[Any], *, lang: str = DEFAULT_LANG) -> str:
    """把检索结果拼成给模型的上下文。

    每段都带上编号与出处：提示词要求模型"引用时标出处"，上下文里就得先有
    出处可标——只给正文的话，它只能凭空猜是哪本书。
    """
    if normalize_lang(lang) == "en":
        parts = [
            f"[Passage {i}] source: {result.source}\ntext: {result.content}"
            for i, result in enumerate(search_results, 1)
        ]
    else:
        parts = [
            f"【片段{i}】出处：{result.source}\n内容：{result.content}"
            for i, result in enumerate(search_results, 1)
        ]
    return "\n---\n".join(parts)


def build_user_prompt(
    question: str,
    search_results: Sequence[Any],
    *,
    lang: str = DEFAULT_LANG,
) -> str:
    """组装当前这一轮的用户提示词。"""
    if normalize_lang(lang) == "en":
        return (
            f"User question: {question}\n\n"
            f"Retrieved passages from the classics:\n\n"
            f"{build_context(search_results, lang='en')}\n\n"
            f"Answer the question above, grounded in these passages."
        )
    return (
        f"用户问题：{question}\n\n"
        f"检索到的相关经典段落：\n\n{build_context(search_results)}\n\n"
        f"请基于以上检索结果回答用户的问题。"
    )


def _recent_turns(history: Optional[Sequence[Any]]) -> list[tuple[str, str]]:
    """从请求带来的历史里取最近几轮，顺手丢掉空轮与形状不对的条目。

    只有一半的轮次（有问无答、有答无问）一律丢掉：空 ``content`` 会让部分
    上游直接拒掉整个请求，而半轮对话对理解上文也没有帮助。
    """
    if not history:
        return []
    turns: list[tuple[str, str]] = []
    for turn in history:
        try:
            past_question, past_answer = turn
        except (TypeError, ValueError):
            # 形状不对就跳过：少一轮上下文，好过整次提问报错
            continue
        cleaned_question = str(past_question or "").strip()
        cleaned_answer = str(past_answer or "").strip()
        if not cleaned_question or not cleaned_answer:
            continue
        turns.append((cleaned_question, cleaned_answer))
    return turns[-MAX_HISTORY_TURNS:]


def _trim_answer(text: str) -> str:
    """旧回答截断成梗概。"""
    cleaned = text.strip()
    if len(cleaned) <= HISTORY_ANSWER_LIMIT:
        return cleaned
    return f"{cleaned[:HISTORY_ANSWER_LIMIT].rstrip()}…"


def build_messages(
    question: str,
    search_results: Sequence[Any],
    *,
    lang: str = DEFAULT_LANG,
    history: Optional[Sequence[Any]] = None,
) -> list[dict[str, str]]:
    """组装完整的对话消息（system + 历史轮次 + 当前轮）。

    ``history`` 是之前几轮的 ``(问题, 回答)``。**这是"追问不再像失忆"的关键**：
    缺了它，模型看到的永远是一个孤零零的新问题。
    """
    target = normalize_lang(lang)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt(target)}]

    for past_question, past_answer in _recent_turns(history):
        # 历史轮次不再重复附检索片段：模型要的是"聊过什么"，
        # 而不是把当时引过的段落再读一遍（那样上下文会成倍膨胀）。
        messages.append({"role": "user", "content": past_question})
        messages.append({"role": "assistant", "content": _trim_answer(past_answer)})

    messages.append(
        {
            "role": "user",
            "content": build_user_prompt(question, search_results, lang=target),
        }
    )
    return messages


def local_fallback(
    question: str,
    search_results: Sequence[Any],
    error: str = "",
    *,
    key_hint: str = "LLM_API_KEY",
    lang: str = DEFAULT_LANG,
) -> str:
    """降级回答：没有可用 LLM 时，直接把检索结果排版返回。"""
    if normalize_lang(lang) == "en":
        return _fallback_en(question, search_results, error, key_hint)
    return _fallback_zh(question, search_results, error, key_hint)


def _fallback_zh(question: str, search_results: Sequence[Any], error: str, key_hint: str) -> str:
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


def _fallback_en(question: str, search_results: Sequence[Any], error: str, key_hint: str) -> str:
    if not search_results:
        return (
            "Nothing in the classics speaks directly to this question. "
            "Try asking with different words."
        )

    parts: list[str] = []
    if error:
        parts.append(f"(AI generation unavailable: {error}. Below are the passages found locally.)\n")

    parts.append(f"## Your question\n\n{question}\n")
    parts.append("## What the classics say\n")
    for i, result in enumerate(search_results, 1):
        excerpt = clean_excerpt(result.content)
        parts.append(f"### Passage {i} — {result.source}\n")
        parts.append("\n".join(f"> {line}" for line in excerpt.splitlines()) + "\n")
    parts.append("## Suggestion\n")
    parts.append(
        "These are the closest passages the classics offer. "
        "Read them alongside your own situation."
    )
    parts.append(f"\n*(Configure {key_hint} to get an AI-written reading)*")

    return "\n".join(parts)
