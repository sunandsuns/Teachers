"""智能问答 API 路由。

只做两件事：校验入参、把服务层的结果拼成响应模型。检索与生成的编排在
``services/qa.py``，这里不出现任何业务分支。
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import current_user, require_user
from ..services import qa
from ..services.auth import User
from ..services.llm import EndpointOverride

# 「求教」要登录：它把问答写进「回响」，而回响是按账号隔离的——
# 匿名提问会落到谁都看不见的 `user_id IS NULL` 那一份里，等于白问。
# 理由与做法见 `deps.py`。
router = APIRouter(prefix="/api/ask", tags=["ask"], dependencies=[Depends(require_user)])

#: 请求体里最多接受几轮历史。真实上限比这严（``prompt.MAX_HISTORY_TURNS``），
#: 这里放宽只是不想因为前端多带两轮就让整次提问 422——截断是服务层的事。
MAX_REQUEST_TURNS = 20


class LLMEndpoint(BaseModel):
    """用户自填的模型端点。

    三个字段全空即"用内置的默认模型"。只填一半（有地址没 Key）视同全空——
    见 :meth:`EndpointOverride.from_payload`，拿半截配置去试探只会换来一次
    注定失败的请求。
    """

    base_url: str = Field("", max_length=500, description="接口地址，如 https://api.example.com/v1")
    api_key: str = Field("", max_length=500, description="API Key")
    model: str = Field("", max_length=200, description="模型名；留空则由应用自动挑选")

    def to_override(self) -> Optional[EndpointOverride]:
        return EndpointOverride.from_payload(self.model_dump())


class ConversationTurn(BaseModel):
    """一轮旧问答。追问时随请求带上来，模型才知道刚才聊到哪。"""

    question: str = Field("", max_length=500, description="当时的提问")
    answer: str = Field("", max_length=40000, description="当时得到的回答")


class AskRequest(BaseModel):
    """问答请求。"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    top_k: int = Field(5, ge=1, le=10, description="检索结果数")
    lang: str = Field(
        "", max_length=10, description="作答语言：zh / en；留空或无法识别时按 zh"
    )
    conversation_id: str = Field(
        "",
        max_length=64,
        description="话题 id：带上就是接着那个话题追问，留空则新开一个",
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=MAX_REQUEST_TURNS,
        description="最近几轮问答（新的在后）。追问时带上，回答才不会像失忆",
    )
    llm: Optional[LLMEndpoint] = Field(
        None, description="自定义模型端点；省略或留空则使用内置的默认模型"
    )


class AskResponse(BaseModel):
    """问答响应。"""
    question: str
    answer: str
    retrieved_count: int
    llm_used: bool
    model: Optional[str] = Field(None, description="实际使用的模型；未走 LLM 时为 null")
    history_id: Optional[int] = Field(
        None, description="这条问答在历史记录里的 id；未记上（库不可用等）为 null"
    )
    conversation_id: str = Field(..., description="这次问答所属的话题；追问时原样带回")


class AskPlanRequest(BaseModel):
    """只检索、不生成的请求。字段与 :class:`AskRequest` 保持一致，减去 ``llm``。"""

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    top_k: int = Field(5, ge=1, le=10, description="检索结果数")
    lang: str = Field("", max_length=10, description="作答语言：zh / en")
    conversation_id: str = Field("", max_length=64, description="话题 id；留空则新开一个")
    history: list[ConversationTurn] = Field(default_factory=list, max_length=MAX_REQUEST_TURNS)


class ChatMessage(BaseModel):
    """一条对话消息。后端组装好交给浏览器去生成。"""

    role: str = Field(..., description="system / user / assistant")
    content: str = Field(..., description="消息正文")


class AskPlanResponse(BaseModel):
    """检索结果与组装好的提示词。"""

    question: str
    messages: list[ChatMessage]
    lang: str
    retrieved_count: int
    conversation_id: str


class AskSaveRequest(BaseModel):
    """浏览器侧生成完，把这一问一答送回来存档。"""

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    answer: str = Field(..., min_length=1, max_length=40_000, description="模型生成的回答")
    model: str = Field("", max_length=200, description="实际使用的模型名；留空记为云端来源")
    retrieved_count: int = Field(0, ge=0, le=50, description="这次用了几条检索片段")
    conversation_id: str = Field("", max_length=64, description="话题 id；留空则新开一个")


class AskStatusResponse(BaseModel):
    """问答能力状态（描述内置默认模型，不含用户自填的端点）。"""
    enabled: bool
    base_url: str
    model: str
    available_models: int
    cooling_down: list[str]
    last_error: str


class ProbeResponse(BaseModel):
    """自定义端点的连通性报告。"""
    ok: bool
    base_url: str
    model: str
    models: list[str]
    error: str


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, user: Optional[User] = Depends(current_user)):
    """
    智能问答：
    1. 本地 TF-IDF 检索相关经典段落
    2. 将检索结果与最近几轮对话作为 context，调用模型生成自然语言回答
    3. 无可用模型时降级为纯检索式回答

    请求里带 ``llm`` 时改用用户自填的端点（Key 只在本进程内存中存活，
    不落盘、不回显）；不带则走 ``.env`` 里的默认模型。

    ``lang`` 决定回答用什么语言写；``history`` 是最近几轮问答，**追问依赖它**；
    ``conversation_id`` 决定这次问答归到哪个话题下（不带则新开一个，响应里回传）。

    这次问答会存进历史记录（界面的「回响」页），``history_id`` 是它的编号。
    历史记录只保留最近半个月，自动清理。

    刻意写成同步函数：内部要调用阻塞的模型 HTTP 请求（最长受
    ``LLM_TOTAL_BUDGET`` 约束），若声明为 ``async def`` 会把事件循环独占几十秒，
    期间健康检查、书架、感悟等所有并发请求一并卡死。同步函数由 FastAPI
    放进线程池执行，等待期间其余接口照常响应。
    """
    result = qa.ask(
        request.question,
        top_k=request.top_k,
        override=request.llm.to_override() if request.llm else None,
        lang=request.lang,
        history=[(turn.question, turn.answer) for turn in request.history],
        conversation_id=request.conversation_id,
        user_id=user.id if user else None,
    )
    return AskResponse(
        question=result.question,
        answer=result.answer,
        retrieved_count=result.retrieved,
        llm_used=result.llm_used,
        model=result.model,
        history_id=result.history_id,
        conversation_id=result.conversation_id or "",
    )


@router.post("/plan", response_model=AskPlanResponse)
def plan(request: AskPlanRequest, user: Optional[User] = Depends(current_user)):
    """只做检索与组装提示词，把 messages 交给浏览器去调云模型。

    为什么要有这条：WorkBuddy 的免密钥模型按**浏览器 Origin** 鉴权
    （``publishableKey`` 只认发布域名），Python 后端既没有 Origin、也不该代持
    那份凭据。所以生成只能发生在页面里。但提示词、检索、题型判断必须留在
    后端——两边各写一份模板，改起来一定会走偏。

    与 ``POST /api/ask`` 共用同一段编排，只是不生成、不落库；
    生成完之后由前端调 ``POST /api/ask/save`` 补记进「回响」。
    """
    result = qa.plan(
        request.question,
        top_k=request.top_k,
        lang=request.lang,
        history=[(turn.question, turn.answer) for turn in request.history],
        conversation_id=request.conversation_id,
        user_id=user.id if user else None,
    )
    return AskPlanResponse(
        question=result.question,
        messages=[ChatMessage(**message) for message in result.messages],
        lang=result.lang,
        retrieved_count=result.retrieved,
        conversation_id=result.conversation_id,
    )


@router.post("/save", response_model=AskResponse)
def save(request: AskSaveRequest, user: Optional[User] = Depends(current_user)):
    """把浏览器侧生成好的回答补记进历史记录。

    云模型那条路的回答不经过后端，不送回来的话「回响」里会缺一整段对话。
    存不进去（库不可用）照样返回 200，只是 ``history_id`` 为 null。

    这条记录归**当前登录的人**——不带上用户身份，云模型那条路存下来的问答
    会落进"匿名那一份"，登录用户在「回响」里就看不到自己刚问过的那段。
    """
    result = qa.save_answer(
        request.question,
        request.answer,
        model=request.model or None,
        retrieved_count=request.retrieved_count,
        conversation_id=request.conversation_id,
        user_id=user.id if user else None,
    )
    return AskResponse(
        question=result.question,
        answer=result.answer,
        retrieved_count=result.retrieved,
        llm_used=result.llm_used,
        model=result.model,
        history_id=result.history_id,
        conversation_id=result.conversation_id or "",
    )


@router.post("/probe", response_model=ProbeResponse)
def probe(request: LLMEndpoint):
    """测试自填的模型端点：能否连通、暴露了哪些模型、挑得中哪一个。

    供界面上的"测试连接"按钮使用。同样写成同步函数——它内部要发真实请求，
    且会等满 ``PROBE_BUDGET``。
    """
    return ProbeResponse(**qa.probe(request.to_override()))


@router.get("/status", response_model=AskStatusResponse)
async def status():
    """查看内置默认模型是否启用、当前选中哪个、哪些在冷却。"""
    return AskStatusResponse(**qa.status())
