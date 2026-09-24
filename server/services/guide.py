"""书籍导读生成：拿元信息让模型写一份可检索的导读。

为什么需要它
--------------------------------------------------------------------------
OpenLibrary 只给元信息，而且经常连简介都没有（实测《活着》的 work 记录里
``description`` 字段是空的，只有主题标签）。用户加了一本书，书架里若只有
"书名 / 作者 / 2008"，那和收藏夹没区别，也搜不出任何东西。所以补一份导读，
它既是阅读入口，也是这本书在检索里唯一有分量的正文。

降级
--------------------------------------------------------------------------
上游不可用时返回空串——加书这个动作**不该因为模型挂了而失败**。书架里
照样有元信息，只是没有导读，前端会如实标出来。
"""

from __future__ import annotations

from .book_search import BookCandidate
from .llm import LLMTransportError, get_router

#: 导读的 token 上限。目标篇幅 500-700 字，1200 留足余量。
MAX_TOKENS = 1200

SYSTEM_PROMPT = """你是一位博学的读书向导。用户想读一本书，你为它写一份导读。

要求：
1. 直接输出导读正文，不要开场白（不要"好的""以下是"这类话）。
2. 用 Markdown，包含三节：
   ## 这本书在讲什么
   ## 为什么值得读
   ## 读的时候留意什么
3. 总长 500-700 字，中文。
4. **只写你确实知道的内容。** 如果你并不了解这本书，就依据书名、作者、主题
   做合理推测，并在开头明确说明"以下依据书名与主题推断"。编造情节比承认
   不知道更糟——用户会拿着你编的内容去读真书。
5. 不要剧透关键结局。"""


def _user_prompt(candidate: BookCandidate) -> str:
    """把元信息排成一段给模型看的事实清单。

    明确写出"来源方没有提供简介"，模型才会去用书名与主题推断，而不是
    凭空编一段"本书讲述了……"。
    """
    lines = [f"书名：{candidate.title}"]
    if candidate.author:
        lines.append(f"作者：{candidate.author}")
    if candidate.year:
        lines.append(f"首版年份：{candidate.year}")
    if candidate.subjects:
        lines.append(f"主题标签：{'、'.join(candidate.subjects)}")
    if candidate.summary:
        lines.append(f"来源方提供的简介：{candidate.summary}")
    else:
        lines.append("来源方没有提供简介——请主要依据书名、作者与主题来写。")
    return "\n".join(lines)


def generate_guide(candidate: BookCandidate) -> tuple[str, str]:
    """生成导读。

    Returns:
        ``(导读正文, 实际使用的模型名)``。不可用时返回 ``("", "")``——
        调用方据此判断"这本书只有元信息"。
    """
    router = get_router()
    if not router.config.enabled:
        return "", ""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(candidate)},
    ]
    try:
        content, model = router.chat(messages, max_tokens=MAX_TOKENS)
    except LLMTransportError:
        # 上游故障（或预算耗尽）。不抛——加书照常完成，只是没有导读。
        return "", ""

    text = (content or "").strip()
    if not text:
        return "", ""
    return text, model
