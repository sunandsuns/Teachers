"""ask 接口的出入参。

从 ``routers/ask.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

#: 请求体里最多接受几轮历史。真实上限比这严（``prompt.MAX_HISTORY_TURNS``），
#: 这里放宽只是不想因为前端多带两轮就让整次提问 422——截断是服务层的事。
#:
#: 它是**契约的一部分**（决定什么时候 422），所以跟着模型一起住在这里，
#: 而不是留在 router 里让 schemas 反过来去 import。
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


class ConversationTurn(BaseModel):
    """一轮旧问答。追问时随请求带上来，模型才知道刚才聊到哪。"""

    model_config = ConfigDict(title="ChatTurn")

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

    model_config = ConfigDict(title="AskPlan")

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

    model_config = ConfigDict(title="AskStatus")

    enabled: bool
    base_url: str
    model: str
    available_models: int
    cooling_down: list[str]
    last_error: str


class ProbeResponse(BaseModel):
    """自定义端点的连通性报告。"""

    model_config = ConfigDict(title="ProbeResult")

    ok: bool
    base_url: str
    model: str
    models: list[str]
    error: str
