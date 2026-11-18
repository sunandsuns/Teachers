"""书籍导读生成：拿元信息让模型写一份可检索的导读。

为什么需要它
--------------------------------------------------------------------------
OpenLibrary 只给元信息，而且经常连简介都没有（实测《活着》的 work 记录里
``description`` 字段是空的，只有主题标签）。用户加了一本书，书架里若只有
"书名 / 作者 / 2008"，那和收藏夹没区别，也搜不出任何东西。所以补一份导读，
它既是阅读入口，也是这本书在检索里唯一有分量的正文。

降级
--------------------------------------------------------------------------
上游不可用时**不抛异常**——加书这个动作不该因为模型挂了而失败。书架里照样
有元信息，只是没有导读。

但"不抛"不等于"不说"：失败的原因放在 :attr:`GuideOutcome.error` 里。这一点是
后补的——原先失败一律返回 ``("", "")``，"服务端根本没配模型"与"上游这次挂了"
长得一模一样，调用方除了沉默什么都做不了。而用户那边看到的是一张除了状态药丸
什么都没有的卡片：书架上的书没有正文，导读就是唯一能读的东西，它空了就等于
整本书没法读。
"""

from __future__ import annotations

from dataclasses import dataclass

from .book_search import BookCandidate
from .llm import LLMTransportError, get_router

#: 导读的 token 上限。目标篇幅 500-700 字，1200 留足余量。
MAX_TOKENS = 1200

#: 失败原因会落库、并原样显示在书架卡片上。上游的报错有时很长（"已尝试：
#: a, b, c"那一串），截一段够定位就行——它要回答的是"为什么没成"，
#: 不是"完整堆栈"。
MAX_ERROR_CHARS = 200

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


@dataclass(frozen=True)
class GuideOutcome:
    """一次导读生成的结果。

    三者只会出现两种组合：``ok`` 为真（``text`` 有内容），或者 ``text`` 为空
    而 ``error`` 有话说。**不会有"两个都空"**——那种状态正是这个类型要消灭的。
    """

    text: str = ""
    model: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())


def _failed(reason: str) -> GuideOutcome:
    """把一段失败原因收拾成一条能给用户看的短句。"""
    # 换行与连续空白压平：这句话要放进卡片的一行里，带换行会撑出奇怪的空白
    text = " ".join((reason or "").split())
    if len(text) > MAX_ERROR_CHARS:
        text = text[: MAX_ERROR_CHARS - 1] + "…"
    return GuideOutcome(error=text or "导读生成失败")


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


def generate_guide(candidate: BookCandidate) -> GuideOutcome:
    """生成导读。**任何失败都不抛**，原因放在结果的 ``error`` 里。

    调用方据此判断"这本书只有元信息"以及"为什么只有元信息"。
    """
    router = get_router()
    if not router.config.enabled:
        return _failed("服务端没有配置可用的模型")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(candidate)},
    ]
    try:
        content, model = router.chat(messages, max_tokens=MAX_TOKENS)
    except LLMTransportError as exc:
        # 上游故障（或预算耗尽）。不抛——加书照常完成，只是没有导读。
        #
        # 用括号而不是第二个冒号：这几句话会被塞进 ``导读生成失败：{reason}``
        # 里，再带一个冒号就成了「导读生成失败：模型调用失败：没有可用模型」。
        return _failed(f"模型没有答复（{exc}）")

    text = (content or "").strip()
    if not text:
        # 实测有这一支：同一个模型一次给出整段好答案，另一次只回几十个字符
        # 甚至空串。当成成功会让书架里多出一份空导读。
        return _failed(f"模型（{model}）这一次没有返回内容")
    return GuideOutcome(text=text, model=model)
