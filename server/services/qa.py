"""问答编排：检索经典 → 组装提示词 → 生成回答。

为什么单独成层
--------------------------------------------------------------------------
路由（``routers/ask.py``）原先自己干这件事，于是它同时承担了参数校验、检索器
惰性初始化、调模型、拼响应四件事。按项目的三层约定，路由该只有第一件和最后
一件。

除此之外还有两个直接收益：

- **可单测**：本模块不依赖 FastAPI，测试可以直接调用 :func:`ask`，不必起客户端、
  也不必小心翼翼地绕开真实的模型调用；
- **可复用**：以后新增"换个入口提问"（比如命令行、定时任务）不必重写一遍编排。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .advice import DEFAULT_TOP_K, search_for_advice
from .history import get_history_store, new_topic_id
from .intent import guidance as intent_guidance
from .intent import parse_intent
from .llm import EndpointOverride, generate_answer_with_model, llm_status, probe_endpoint
from .llm import build_messages, normalize_lang, resolve_session
from .retriever import SearchResult, ensure_retriever
from .unified_search import CANDIDATE_FACTOR, rrf_fuse, shelf_index

#: 走自定义端点时，降级文案要指向用户真正能改的地方——
#: 让他去配一个自己没听说过的环境变量，等于没说。
CUSTOM_KEY_HINT = "自定义模型的接口地址与 API Key"
CUSTOM_KEY_HINT_EN = "the endpoint and API key filled in model settings"

#: 走内置端点时的提示。这是个环境变量名，让它保持原样，两种语言都去 .env 里找。
DEFAULT_KEY_HINT = "LLM_API_KEY"

#: 浏览器侧调用 WorkBuddy 云模型时记在历史里的名字。
#:
#: 它不是某个具体模型 id——云端模型目录会变，前端每次挑的是目录里的某一个。
#: 记一个稳定的来源标记，比记一串会过期的 id 更有用。
CLOUD_MODEL_TAG = "workbuddy-cloud"

_MAX_SAVED_ANSWER = 40_000


@dataclass(frozen=True)
class Answer:
    """一次求教的完整结果。"""

    question: str
    answer: str
    retrieved: int
    model: Optional[str]
    #: 落库后的记录 id；没记上（库不可用等）为 None
    history_id: Optional[int] = None
    #: 这次问答所属的话题。追问时把它带回来，才归得到同一个话题下。
    conversation_id: Optional[str] = None

    @property
    def llm_used(self) -> bool:
        """回答是否真由模型产出。

        以"有没有拿到模型名"为准，而不是"配没配 Key"——后者会把一次失败的调用
        报成成功。
        """
        return self.model is not None


def _retrieve(
    question: str,
    *,
    top_k: int,
    history: Optional[Sequence[tuple[str, str]]],
    user_id: Optional[int],
) -> list[SearchResult]:
    """求教用的检索：公共语料 + 登录用户自己的书架。

    公共那一路走 :func:`advice.search_for_advice` 而不是直接 ``retriever.search``：
    全库平权时回来的是《毛泽东选集》和《易经》卦爻辞（两者占索引 67%），
    模型拿不到对口材料，只能硬凑或架空。详见 ``services/advice.py``。

    私人书架那一路独立检索，两路再用 RRF 融合。为什么不把用户的书直接并进
    公共检索：两边 IDF 基准差着一个数量级，分数不可直接比较——理由写在
    ``services/unified_search.py`` 的模块注释里。

    追问时把上一轮的问句一起送进检索：光靠"那我具体该说什么"这种句子，
    检索召回的是一堆与正在聊的事无关的段落，回答看着就是答非所问。
    """
    past_questions = _past_questions(history)
    hits = search_for_advice(
        ensure_retriever(),
        question,
        top_k=top_k,
        context=past_questions[-1] if past_questions else "",
    )
    results = list(hits.results)

    if user_id is None:
        return results
    index = shelf_index(user_id)
    if index is None:
        return results
    shelf_hits = index.search(question, top_k=top_k * CANDIDATE_FACTOR)
    if not shelf_hits:
        return results
    return rrf_fuse([results, shelf_hits], top_k=top_k)


def ask(
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    override: Optional[EndpointOverride] = None,
    lang: str = "",
    history: Optional[Sequence[tuple[str, str]]] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Answer:
    """回答一个问题。

    检索走 :func:`advice.search_for_advice` 而不是直接 ``retriever.search``：
    全库平权时回来的是《毛泽东选集》和《易经》卦爻辞（两者占索引 67%），
    模型拿不到对口材料，只能硬凑或架空。详见 ``services/advice.py``。

    ``override`` 非空时改用请求方填的端点；该端点的可用性不影响默认配置，
    反之亦然（各自的路由器与冷却表相互独立）。

    ``lang`` 决定**回答用什么语言写**（``zh`` / ``en``；不认识的值按中文）。
    检索与语料始终是中文，这里管的是作答语言。

    ``history`` 是最近几轮 ``(问题, 回答)``。**追问能不能接上上文全看它**——
    不带的话，模型收到的永远是一个孤零零的新问题。它还被用来喂检索：
    最近那一轮的问句会一起送进去，否则"那我第一句话该怎么说"这种没有主语、
    没有对象的追句召回不到任何对得上的材料。

    回答生成前还会从问句里认出**题型**（``services/intent.py``：选择题 /
    求做法 / 求原因 / 倾诉…），把对应的要求追加进提示词。同一套四段式模板
    对所有问题一视同仁，正是"答非所问"的来源——问"该忍还是该说"的人要的是
    一个明确的选择，不是两段各有道理的分析。

    ``conversation_id`` 是话题归属：带上就是接着那个话题追问，不带则新开一个。
    **无论库是否可用都会给出一个话题 id**——它在前端只是个分组凭据，不该
    因为"这次没记上账"就丢掉。

    回答会顺手存进历史记录。**存不进去不影响返回**：由 ``HistoryStore`` 内部
    吞掉失败，这里只如实带上 ``history_id``（没存上就是 None）。
    一次已经成功的求教，不该因为"附带的记账动作"失败而变成失败。
    """
    # 追问时把上一轮的问句一起送进检索：光靠"那我具体该说什么"这种句子，
    # 检索召回的是一堆与正在聊的事无关的段落，回答看着就是答非所问。
    results = _retrieve(question, top_k=top_k, history=history, user_id=user_id)
    session = resolve_session(override)
    answer_lang = normalize_lang(lang)
    topic_id = (conversation_id or "").strip() or new_topic_id()

    if not session.custom:
        key_hint = DEFAULT_KEY_HINT
    else:
        key_hint = CUSTOM_KEY_HINT_EN if answer_lang == "en" else CUSTOM_KEY_HINT

    answer, model = generate_answer_with_model(
        question,
        results,
        router=session.router,
        key_hint=key_hint,
        lang=answer_lang,
        history=history,
        guidance=intent_guidance(parse_intent(question), lang=answer_lang),
    )
    record_id = get_history_store().save(
        question,
        answer,
        model=model,
        retrieved_count=len(results),
        conversation_id=topic_id,
        user_id=user_id,
    )
    return Answer(
        question=question,
        answer=answer,
        retrieved=len(results),
        model=model,
        history_id=record_id,
        conversation_id=topic_id,
    )


@dataclass(frozen=True)
class AskPlan:
    """一次求教的"待生成"包：检索到的段落 + 组装好的提示词。

    给**浏览器侧**的云模型用。WorkBuddy 的免密钥模型按浏览器 Origin 鉴权，
    Python 后端既没有 Origin 也不被允许代持凭据，所以只能由页面去调。
    提示词仍然在这里组装——两边各写一份模板，改起来一定会走偏。
    """

    question: str
    messages: list[dict[str, str]]
    lang: str
    retrieved: int
    conversation_id: str


def plan(
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    lang: str = "",
    history: Optional[Sequence[tuple[str, str]]] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> AskPlan:
    """只做检索与组装提示词，不调模型——生成交给浏览器。

    与 :func:`ask` 共用同一段检索与题型判断，保证"内置模型"和"云模型"
    两条路拿到的材料与要求完全一致；差别只在谁去生成。
    """
    results = _retrieve(question, top_k=top_k, history=history, user_id=user_id)
    answer_lang = normalize_lang(lang)
    topic_id = (conversation_id or "").strip() or new_topic_id()
    messages = build_messages(
        question,
        results,
        lang=answer_lang,
        history=history,
        guidance=intent_guidance(parse_intent(question), lang=answer_lang),
    )
    return AskPlan(
        question=question,
        messages=messages,
        lang=answer_lang,
        retrieved=len(results),
        conversation_id=topic_id,
    )


def save_answer(
    question: str,
    answer: str,
    *,
    model: Optional[str] = None,
    retrieved_count: int = 0,
    conversation_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Answer:
    """把浏览器侧生成好的回答补记进历史。

    云模型那条路的回答是在页面里产出的，后端没见过，所以要由前端送回来存档，
    否则「回响」里会缺一整段对话。存不进去照样不影响返回。
    """
    topic_id = (conversation_id or "").strip() or new_topic_id()
    text = (answer or "")[:_MAX_SAVED_ANSWER]
    record_id = get_history_store().save(
        question,
        text,
        model=model or CLOUD_MODEL_TAG,
        retrieved_count=retrieved_count,
        conversation_id=topic_id,
        user_id=user_id,
    )
    return Answer(
        question=question,
        answer=text,
        retrieved=retrieved_count,
        model=model or CLOUD_MODEL_TAG,
        history_id=record_id,
        conversation_id=topic_id,
    )


def _past_questions(history: Optional[Sequence[tuple[str, str]]]) -> list[str]:
    """从历史轮次里取出问句文本。

    形状不对的轮次跳过——少一点上下文，好过整次提问报错。
    """
    past: list[str] = []
    for turn in history or ():
        if not isinstance(turn, (tuple, list)) or not turn:
            continue
        text = str(turn[0] or "").strip()
        if text:
            past.append(text)
    return past


def probe(override: Optional[EndpointOverride]) -> dict[str, Any]:
    """测试一个自定义端点是否可用（界面上"测试连接"按钮的后端）。"""
    return probe_endpoint(override)


def status() -> dict:
    """默认端点此刻的状态（自定义端点的状态由 :func:`probe` 单独反馈）。"""
    return llm_status()
