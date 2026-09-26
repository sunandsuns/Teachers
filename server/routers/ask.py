"""智能问答 API 路由。

只做两件事：校验入参、把服务层的结果拼成响应模型。检索与生成的编排在
``services/qa.py``，这里不出现任何业务分支。
"""

from typing import Optional

from fastapi import APIRouter, Depends

from ..deps import require_user
from ..errors import DB_BACKED
from ..schemas.ask import (
    AskPlanRequest,
    AskPlanResponse,
    AskRequest,
    AskResponse,
    AskSaveRequest,
    AskStatusResponse,
    ChatMessage,
    ConversationTurn,
    LLMEndpoint,
    ProbeResponse,
)
from ..services import qa
from ..services.auth import User
from ..services.llm import EndpointOverride

# 「求教」要登录：它把问答写进「回响」，而回响是按账号隔离的——
# 匿名提问会落到谁都看不见的 `user_id IS NULL` 那一份里，等于白问。
# 理由与做法见 `deps.py`。
router = APIRouter(
    prefix="/api/ask", tags=["ask"], dependencies=[Depends(require_user)], responses=DB_BACKED
)


def _to_override(payload: Optional[LLMEndpoint]) -> Optional[EndpointOverride]:
    """入参 → 服务层要的端点覆盖。

    转换放在 router 而不是模型上（原先挂在 ``LLMEndpoint.to_override``）：
    ``schemas/`` 是纯数据，让模型去 import 服务层的类型，等于让契约层反过来
    依赖实现层。凡是"模型 → 服务层对象"的转换都留在这一侧。

    走 ``from_payload`` 而不是直接构造：它负责"只填一半视同没填"那条规则，
    绕过去就会拿着半截配置去发一个注定失败的请求。
    """
    return EndpointOverride.from_payload(payload.model_dump() if payload else None)


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, user: User = Depends(require_user)):
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
        override=_to_override(request.llm),
        lang=request.lang,
        history=[(turn.question, turn.answer) for turn in request.history],
        conversation_id=request.conversation_id,
        user_id=user.id,
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
def plan(request: AskPlanRequest, user: User = Depends(require_user)):
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
        user_id=user.id,
    )
    return AskPlanResponse(
        question=result.question,
        messages=[ChatMessage(**message) for message in result.messages],
        lang=result.lang,
        retrieved_count=result.retrieved,
        conversation_id=result.conversation_id,
    )

@router.post("/save", response_model=AskResponse)
def save(request: AskSaveRequest, user: User = Depends(require_user)):
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
        user_id=user.id,
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
    return ProbeResponse(**qa.probe(_to_override(request)))

@router.get("/status", response_model=AskStatusResponse)
async def status():
    """查看内置默认模型是否启用、当前选中哪个、哪些在冷却。"""
    return AskStatusResponse(**qa.status())
