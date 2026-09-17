"""智能问答 API 路由。

只做两件事：校验入参、把服务层的结果拼成响应模型。检索与生成的编排在
``services/qa.py``，这里不出现任何业务分支。
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import qa
from ..services.llm import EndpointOverride

router = APIRouter(prefix="/api/ask", tags=["ask"])


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


class AskRequest(BaseModel):
    """问答请求。"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    top_k: int = Field(5, ge=1, le=10, description="检索结果数")
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
def ask(request: AskRequest):
    """
    智能问答：
    1. 本地 TF-IDF 检索相关经典段落
    2. 将检索结果作为 context，调用模型生成自然语言回答
    3. 无可用模型时降级为纯检索式回答

    请求里带 ``llm`` 时改用用户自填的端点（Key 只在本进程内存中存活，
    不落盘、不回显）；不带则走 ``.env`` 里的默认模型。

    刻意写成同步函数：内部要调用阻塞的模型 HTTP 请求（最长受
    ``LLM_TOTAL_BUDGET`` 约束），若声明为 ``async def`` 会把事件循环独占几十秒，
    期间健康检查、书架、感悟等所有并发请求一并卡死。同步函数由 FastAPI
    放进线程池执行，等待期间其余接口照常响应。
    """
    result = qa.ask(
        request.question,
        top_k=request.top_k,
        override=request.llm.to_override() if request.llm else None,
    )
    return AskResponse(
        question=result.question,
        answer=result.answer,
        retrieved_count=result.retrieved,
        llm_used=result.llm_used,
        model=result.model,
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
