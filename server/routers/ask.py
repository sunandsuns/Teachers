"""智能问答 API 路由。"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.content_loader import get_loader
from ..services.llm import generate_answer_with_model, llm_status
from ..services.retriever import build_retriever_from_loader, get_retriever

router = APIRouter(prefix="/api/ask", tags=["ask"])


class AskRequest(BaseModel):
    """问答请求。"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    top_k: int = Field(5, ge=1, le=10, description="检索结果数")


class AskResponse(BaseModel):
    """问答响应。"""
    question: str
    answer: str
    retrieved_count: int
    llm_used: bool
    model: Optional[str] = Field(None, description="实际使用的模型；未走 LLM 时为 null")


class AskStatusResponse(BaseModel):
    """问答能力状态。"""
    enabled: bool
    base_url: str
    model: str
    available_models: int
    cooling_down: list[str]
    last_error: str


@router.post("", response_model=AskResponse)
def ask(request: AskRequest):
    """
    智能问答：
    1. 本地 TF-IDF 检索相关经典段落
    2. 将检索结果作为 context，调用 LLM 生成自然语言回答
    3. 无可用模型时降级为纯检索式回答

    刻意写成同步函数：内部要调用阻塞的模型 HTTP 请求（最长受
    ``LLM_TOTAL_BUDGET`` 约束），若声明为 ``async def`` 会把事件循环独占几十秒，
    期间健康检查、书架、感悟等所有并发请求一并卡死。同步函数由 FastAPI
    放进线程池执行，等待期间其余接口照常响应。
    """
    # 确保检索器已初始化
    retriever = get_retriever()
    if not retriever.documents:
        loader = get_loader()
        retriever = build_retriever_from_loader(loader)

    # 检索相关段落
    results = retriever.search(request.question, top_k=request.top_k)

    # 生成回答：llm_used 以"回答是否真由模型产出"为准，而不是"是否配了密钥"
    answer, model = generate_answer_with_model(request.question, results)

    return AskResponse(
        question=request.question,
        answer=answer,
        retrieved_count=len(results),
        llm_used=model is not None,
        model=model,
    )


@router.get("/status", response_model=AskStatusResponse)
async def status():
    """查看 LLM 是否启用、当前选中哪个模型、哪些模型在冷却。"""
    return AskStatusResponse(**llm_status())
