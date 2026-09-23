"""读懂一句话"到底在问什么"。

为什么需要这一层
--------------------------------------------------------------------------
原来的回答只有一套固定的四段式模板：你的处境 / 经典怎么说 / 我的分析 /
建议你怎么办。模板本身没错，错在它**对所有问题一视同仁**——于是：

- 问"我该忍还是该说"（一道选择题），回答把两个选项各分析一遍，最后落
  到"要看情况""各有道理"。用户要的是**你帮我选一个**；
- 问"我该怎么开口要"（要动作），回答给了三段道理，最后一条建议还是
  "调整心态"。用户要的是**我明天具体说什么**；
- 问"我最近很焦虑"（在倾诉），回答立刻列出一二三条行动清单，像在布置
  作业。用户此刻要的是**有人先把这句话接住**。

这三种"答非所问"都不是模型不会写，而是**没被告知该写哪一种**。本模块
就是补上这一步：先判断这一句属于哪类问题，再把对应的要求塞进提示词。

刻意做成纯函数 + 正则
--------------------------------------------------------------------------
判错类型的代价不小（把倾诉判成行动清单，比不给建议更让人难受），所以
这里**只认字面信号**：出现"还是""该不该"才是选择题，出现"怎么办"才是
求动作。宁可判成通用型（只是少一条额外指令），也不猜——猜错会把回答
引到一条更窄的路上去。

同样地，它不调用模型：意图识别要在检索之后、生成之前完成，再排一次
模型调用等于把 ``LLM_TOTAL_BUDGET`` 翻一倍。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

#: 问题类型。
ASK_DECISION = "decision"    # 二选一：该忍还是该说、要不要辞职
ASK_HOWTO = "howto"          # 求做法：怎么办、怎么开口、如何坚持
ASK_WHY = "why"              # 求原因：为什么会这样、凭什么
ASK_MEANING = "meaning"      # 求解义：这句话什么意思、怎么理解
ASK_KNOWLEDGE = "knowledge"  # 求知：某部经典在这件事上怎么说
ASK_VENT = "vent"            # 倾诉：只有处境，没有提问
ASK_GENERAL = "general"      # 认不出，走通用四段式

ASK_KINDS = (
    ASK_DECISION,
    ASK_HOWTO,
    ASK_WHY,
    ASK_MEANING,
    ASK_KNOWLEDGE,
    ASK_VENT,
    ASK_GENERAL,
)

#: 选择题的信号。出现即算——"还是"两侧的那两个词由 :func:`_split_options` 再剥。
_DECISION_RE = re.compile(r"还是|该不该|要不要|值不值得|选哪个|好不好|划不划算")

#: 求做法。"怎么/如何"必须与动作搭配才算（"怎么会这样"是问原因，归 WHY）。
_HOWTO_RE = re.compile(r"怎么办|咋办|如何做|怎么做|怎么才能|怎样才能|怎么开口|该怎么|有什么办法|如何开口|如何坚持|如何面对|如何是好")

#: 求原因。
_WHY_RE = re.compile(r"为什么|为何|怎么会|咋会|凭什么|怎么这样|为什么会")

#: 求解义。
_MEANING_RE = re.compile(r"是什么意思|什么意思|什么含义|怎么理解|如何理解|何谓|怎么讲|怎么解")

#: 求知：点了某部经典或某个人物，多半是问"它在这件事上怎么说"。
_KNOWLEDGE_RE = re.compile(r"《[^》]{1,24}》|孔子|老子|孟子|庄子|荀子|王阳明|曾国藩|孙子|鬼谷子|菜根谭|论语|道德经")

#: 倾诉的信号：说了情绪，但没提任何要求。
_VENT_RE = re.compile(
    r"焦虑|难受|委屈|崩溃|压力大|心累|很累|沮丧|低落|失眠|睡不着|想哭|"
    r"撑不住|迷茫|孤独|害怕|恐惧|后悔|不甘|疲惫|内耗|烦躁"
)

#: 选项两侧要剥掉的成分。
#: "我该忍还是该说"里，"忍"前面挂着"我该"，"说"前面挂着"该"——
#: 不剥的话指令里写的是"在『我该忍』与『该说』之间"，读起来很怪。
#: 刻意不含"不"：选项里的"不该忍"是个真正的立场，剥掉就成了"忍"，
#: 于是"忍还是不该忍"被读成"忍 / 忍"，指令也就跟着废了。
_PARTICLE_RE = re.compile(r"^[我你他她它我们咱们的该应要不是能可以会就还再吗呢吧啊呀么嘛]+")
#: 选项右侧的终止符。
_OPTION_STOP_RE = re.compile(r"[，。？?！!、；;：:\s]")


@dataclass(frozen=True)
class QuestionIntent:
    """一句话的问法。

    ``kind`` 决定提示词里追加哪一条要求；``options`` 只在选择题里非空，
    用来把"在忍与说之间"写进指令——**带上具体选项**才压得住"各有道理"
    式的骑墙回答。
    """

    kind: str
    options: tuple[str, ...] = ()

    @property
    def is_decision(self) -> bool:
        return self.kind == ASK_DECISION


def _strip(option: str) -> str:
    """剥掉选项前后的虚词；剥完就没了的话宁可不剥。

    "我该忍"只剩"忍"才算一个选项；可"不要"被剥成""就什么都不是了——
    这时候原样留着比消失好。
    """
    stripped = _PARTICLE_RE.sub("", option.strip())
    return stripped or option.strip()


def _split_options(text: str) -> tuple[str, ...]:
    """从"我该忍还是该说"里剥出 ("忍", "说")。

    剥不出来就返回空元组——指令里少一句"在 X 与 Y 之间"，比写错选项好。
    """
    pivot = text.find("还是")
    if pivot <= 0:
        return ()
    # 先切再剥：左边常常挂着更前面的话（"领导抢我功劳，我该忍"），
    # 得先按标点取最后那一截，才轮得到剥"我该"——顺序反了就剥不动。
    left = re.split(r"[，。？?！!、；;：:\s]", text[:pivot].strip())[-1]
    right = _OPTION_STOP_RE.split(text[pivot + 2 :].strip())[0]
    left = _strip(left)
    right = _strip(right)
    # 选项太长说明"还是"两侧根本不是选项（"我在想这件事还是那件事"之类）
    if not left or not right or len(left) > 8 or len(right) > 8:
        return ()
    # 两侧一样（"辞职还是不辞职"被剥成了同一句）就当没剥出来：
    # 那其实是一道是非题，交给"该不该"那条指令更准。
    if left == right:
        return ()
    return (left, right)


def parse_intent(question: str) -> QuestionIntent:
    """判断一句话属于哪类问题。

    顺序即优先级：先认选择题（它常常也带"怎么办"，但用户真正要的是
    选一个），再认原因/释义（这两类的句式很固定），最后才轮到求做法。
    """
    text = (question or "").strip()
    if not text:
        return QuestionIntent(kind=ASK_GENERAL)

    if _DECISION_RE.search(text):
        return QuestionIntent(kind=ASK_DECISION, options=_split_options(text))
    if _WHY_RE.search(text) and not _HOWTO_RE.search(text):
        return QuestionIntent(kind=ASK_WHY)
    if _MEANING_RE.search(text):
        return QuestionIntent(kind=ASK_MEANING)
    if _KNOWLEDGE_RE.search(text):
        return QuestionIntent(kind=ASK_KNOWLEDGE)
    if _HOWTO_RE.search(text):
        return QuestionIntent(kind=ASK_HOWTO)
    if _VENT_RE.search(text):
        return QuestionIntent(kind=ASK_VENT)
    return QuestionIntent(kind=ASK_GENERAL)


#: 各类问题的作答要求（中文）。
#:
#: 写法上有两条共识：
#: - **先说"用户要的是什么"**，再说"因此你必须怎么做"。只写后半句，模型
#:   会把它当成又一条通用准则，照样骑墙；
#: - **把最典型的失败写法点名**（"各有道理""调整心态""列清单"）。不点名，
#:   它就不知道自己正要犯的错是哪一个。
GUIDANCE_ZH: Mapping[str, str] = {
    ASK_DECISION: (
        "这是一道选择题，用户要在「{options}」之间定一个。"
        "你必须在「建议你怎么办」里明确选一个，并在同一处说清另一个为什么不选；"
        "「我的分析」也要围着这个选择写。"
        "禁止用「要看情况」「各有道理」「你自己权衡」收尾——那是没回答。"
        "若两个选项其实都不对（例如还有第三条路），就直说，并给出那条路。"
    ),
    ASK_HOWTO: (
        "用户在问**具体怎么做**，不是问道理。"
        "「建议你怎么办」要给 2-3 个能立刻上手的动作：说清先做什么、话怎么开口、"
        "什么时候做。每条一句话说到位，不写「调整心态」「提升自己」这类空话。"
    ),
    ASK_WHY: (
        "用户在问**为什么会这样**。先把成因讲透（它往往是一条机制，不是一句评判），"
        "再给一条针对这个成因的应对；不要在还没解释清楚时就转去给建议。"
    ),
    ASK_MEANING: (
        "用户在问**一句话或一个说法是什么意思**。先给直白的释义，再引原文，"
        "最后说它落在他这件事上是什么意思。不要通篇只做翻译。"
    ),
    ASK_KNOWLEDGE: (
        "用户在**求知**：某部经典或某个人在这个问题上到底怎么说。"
        "以原文为主，少做发挥；引用务必逐字准确。若检索到的材料不是他问的那一家，"
        "就直说「这段里没有」，不要拿别的书顶上。"
    ),
    ASK_VENT: (
        "用户主要是在**说自己的处境**，并没有提问。"
        "先用一两句话接住他描述的那个具体情形（点出他说的那件事），"
        "再给一条最贴切的话；不要一上来就列一二三条行动清单，"
        "那样读起来像在布置作业。建议最多一条，且要轻。"
    ),
    ASK_GENERAL: "",
}

#: 认出是选择题、却剥不出具体选项时的兜底指令（"该不该辞职""要不要去"）。
#:
#: 这种情况更常见，也更难答：用户连选项都没摆出来，模型最容易滑向
#: "要看你自己的情况"。所以这里的指令换成"把该不该翻译成该或不该"——
#: 直接点名那个最可能的失败写法。
_DECISION_FALLBACK_ZH = (
    "用户在犹豫**该不该**做一件事，没有把选项摆出来。"
    "你必须给出明确的「该」或「不该」，并说清你判断时所依据的那一条；"
    "禁止用「看你自己」「因人而异」「没有标准答案」收尾——那是没回答。"
    "确实取决于某个前提时，就把前提说清楚：满足什么条件就该，不满足就不该。"
)
_DECISION_FALLBACK_EN = (
    "They are hesitating over whether to do something, without naming the options. "
    "Give a clear yes or no and name the one thing your judgement rests on. "
    "Never end with \"it depends\" or \"there is no right answer\" — that is not an answer. "
    "If it really does hinge on a condition, state the condition: if X, do it; if not, don't."
)

#: 各类问题的作答要求（英文）。与中文版逐条对应，别只改一半。
GUIDANCE_EN: Mapping[str, str] = {
    ASK_DECISION: (
        "This is a choice between {options}. You must pick one explicitly in "
        "\"What you can do\" and say in the same place why the other is worse. "
        "Never end with \"it depends\" or \"both have merit\" — that is not an answer. "
        "If neither option is right (say, there is a third way), say so and give that way."
    ),
    ASK_HOWTO: (
        "They are asking how to do it, not asking for a principle. Give two or three "
        "actions they can take today: what to do first, what to say, when to do it. "
        "No filler like \"adjust your mindset\" or \"improve yourself\"."
    ),
    ASK_WHY: (
        "They are asking why this is happening. Explain the mechanism first — it is "
        "usually a mechanism, not a verdict — and only then give one response that "
        "follows from it. Do not jump to advice before the cause is clear."
    ),
    ASK_MEANING: (
        "They are asking what a phrase means. Give a plain explanation first, then "
        "the original text, then what it means for their situation. Do not translate "
        "and stop there."
    ),
    ASK_KNOWLEDGE: (
        "They want to know what a given classic or thinker actually says about this. "
        "Lead with the source text and keep interpretation short. If the passages are "
        "not from the one they asked about, say so plainly instead of substituting "
        "another book."
    ),
    ASK_VENT: (
        "They are mostly telling you where they are, not asking anything. Start by "
        "acknowledging the specific situation they described in a sentence or two, "
        "then offer one passage that fits. Do not open with a numbered action list — "
        "it reads like homework. One suggestion at most, and keep it light."
    ),
    ASK_GENERAL: "",
}


def guidance(intent: QuestionIntent, *, lang: str = "zh") -> str:
    """把意图翻成一句可直接拼进提示词的要求。

    认不出类型（``ASK_GENERAL``）时返回空串：**不追加任何额外指令**，
    让通用模板自己走。给一个认不出的问题硬套要求，等于替用户改写了他的问题。
    """
    table = GUIDANCE_EN if lang == "en" else GUIDANCE_ZH
    text = table.get(intent.kind, "")
    if not text:
        return ""
    if "{options}" in text:
        # 剥不出选项（"该不该辞职"这种）时换成兜底指令，而不是退回通用写法：
        # 认出了是选择题却不说选哪个，等于什么都没说——而这类问题恰恰最
        # 容易滑向"看你自己"。
        if not intent.options:
            return _DECISION_FALLBACK_EN if lang == "en" else _DECISION_FALLBACK_ZH
        text = text.replace("{options}", " / ".join(intent.options))
    return text


__all__ = [
    "ASK_DECISION",
    "ASK_GENERAL",
    "ASK_HOWTO",
    "ASK_KNOWLEDGE",
    "ASK_KINDS",
    "ASK_MEANING",
    "ASK_VENT",
    "ASK_WHY",
    "GUIDANCE_EN",
    "GUIDANCE_ZH",
    "QuestionIntent",
    "guidance",
    "parse_intent",
]
