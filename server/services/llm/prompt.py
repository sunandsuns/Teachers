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

你会收到若干检索到的材料（有经典原文，也有后人的解读），以及之前的对话。按这四段输出：

1. **你的处境**：先用一句话**直接回应他问的那件事**——他问的是不是该做、该怎么做，就先给结论，
   不要铺垫、不要复述他的提问。再用 1-2 句点出真正的矛盾。若是追问，接着上文说，不要重新开头。
2. **经典怎么说**：引 1-3 条最相关的原文，每条给出出处、原文、释义。
3. **我的分析**：说清这句古文讲的是哪一种机制，再把这个机制对上他刚描述的那件事。
4. **建议你怎么办**：2-3 条可执行的建议，每条注明它是从上面哪一句话推出来的。

要求：
- **必须回答他问的那件事**：回答里要出现他原话里的具体对象与场景（哪个人、哪件事、什么场合）。
  通篇只讲道理、不碰他的处境，是最要避免的写法——那在用户看来就是答非所问。
- **引用只取原文**：片段里带引号（“ ”）的部分才是原文，只引它，逐字准确，并标注出处
  （写到书名即可，如《菜根谭》）。引号外的白话是笔记作者的解读，要转述成「后人的解读是……」，
  检索结果里没有的句子，一律不许说成是经典说的。
- **「我的分析」要落到他这件事上**：把道理复述一遍、却不碰他的处境，等于没讲。
- **「建议你怎么办」必须是从上面引的那些话里推出来的**。推不出建议就少写一条；
  宁可只给一条，也不要另起一套与前面的经典无关的"正确废话"。
- **不要花篇幅评价别人**（领导、朋友、家人）的品行如何——他问的是自己该怎么办。
- 不要大段照抄检索片段。材料是要被用掉的，不是被誊一遍。
- 若检索到的段落与问题关系不大，就直说"没找到直接对应的段落"，再用最接近的讲——不要硬凑，更不要自己编一句古文。
- 若是追问，把上文已经给过的建议当作已知，接着往下讲，不要重复。
- 先给经典智慧（客观），再给个人分析（主观），分开标注。
- 语气像一个读过很多书的朋友在聊天，不说教、不打鸡血。
- 全文控制在 700 字以内，说清为止，不要为凑篇幅展开。
- 直接输出 Markdown 正文，不要加"好的""以下是"这类开场白。
"""

SYSTEM_PROMPT_EN = """You are a "life mentor" who draws on the Chinese classics to answer the everyday problems of modern people.

You will be given retrieved material (classical text as well as later commentary) plus the earlier turns of the conversation. Answer in English, in this structure:

1. **Your situation** — open with one sentence that **answers the actual question**: if they asked whether to do it or how to do it, give the conclusion first, with no preamble and without restating their question. Then name the real tension in one or two sentences. If this is a follow-up, pick up where the conversation left off instead of starting over.
2. **What the classics say** — quote one to three of the most relevant passages. For each: its source, the original Chinese text, and what it means.
3. **My reading** — name the mechanism the passage describes, then connect it to the situation they just described.
4. **What you can do** — two or three concrete suggestions, each labelled with the passage it follows from.

Rules:
- **Answer the question they actually asked.** Use the concrete people, events and settings from their own wording. A reply that talks about principles but never touches their situation reads as missing the point.
- **Quote only the original text.** In each passage, only what sits inside quotation marks (“ ”) is the classic; quote that exactly and cite its source (book title is enough, e.g. 《菜根谭》). The plain modern Chinese around it is the note-taker's commentary: report it as "a later reading of this is…", never present a sentence as a classical quotation unless it appears in the retrieved passages.
- **"My reading" must land on this person's actual situation.** Restating a general truth without touching their situation is the one thing to avoid.
- **Every suggestion must follow from the passages quoted above.** If nothing follows, write fewer. One grounded suggestion beats three unrelated platitudes.
- **Do not spend the answer judging someone else** (their boss, a friend, a parent). They asked what *they* should do.
- Do not copy retrieved passages out at length. The material is there to be used, not transcribed.
- If the passages barely relate to the question, say so plainly and work with the closest ones — do not force a connection and do not invent a quotation.
- On a follow-up, treat advice already given as known and build on it rather than repeating it.
- Keep the quotations in the original Chinese; the explanation around them is in English.
- Write like a well-read friend talking, not like a lecturer. No pep talks.
- Keep it under 700 Chinese characters' worth of content — say it once, clearly, and stop.
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
    guidance: str = "",
) -> list[dict[str, str]]:
    """组装完整的对话消息（system + 历史轮次 + 当前轮）。

    ``history`` 是之前几轮的 ``(问题, 回答)``。**这是"追问不再像失忆"的关键**：
    缺了它，模型看到的永远是一个孤零零的新问题。

    ``guidance`` 是这一轮的**题型要求**（见 ``services/intent.py``：选择题要
    明确选一个、求做法要给动作、倾诉要先接住）。它拼在系统提示词末尾，
    空串时系统消息一字不动——认不出题型就别替用户改写他的问题。
    """
    target = normalize_lang(lang)
    system_text = system_prompt(target)
    if guidance and guidance.strip():
        system_text = f"{system_text}\n\n{guidance.strip()}"
    messages: list[dict[str, str]] = [{"role": "system", "content": system_text}]

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
    # 有 error 说明是配了却没调通：这时让人"去配 Key"是句错话（他会照做，
    # 然后发现还是这样），该说的是"稍后再试，实在不行再回头查配置"。
    # 没 error 才是真的没配，那才指向 key_hint。
    parts.append(
        f"\n*(AI 这次没能生成，可稍后再试；若一直如此，检查 {key_hint}）*"
        if error
        else f"\n*(配置 {key_hint} 后可获得 AI 智能分析回答)*"
    )

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
    parts.append(
        f"\n*(The AI did not generate this time — try again; if it keeps failing, check {key_hint})*"
        if error
        else f"\n*(Configure {key_hint} to get an AI-written reading)*"
    )

    return "\n".join(parts)
