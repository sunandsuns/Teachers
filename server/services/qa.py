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
from typing import Any, Optional

from .llm import EndpointOverride, generate_answer_with_model, llm_status, probe_endpoint
from .llm import resolve_session
from .retriever import ensure_retriever

#: 走自定义端点时，降级文案要指向用户真正能改的地方——
#: 让他去配一个自己没听说过的环境变量，等于没说。
CUSTOM_KEY_HINT = "自定义模型的接口地址与 API Key"


@dataclass(frozen=True)
class Answer:
    """一次求教的完整结果。"""

    question: str
    answer: str
    retrieved: int
    model: Optional[str]

    @property
    def llm_used(self) -> bool:
        """回答是否真由模型产出。

        以"有没有拿到模型名"为准，而不是"配没配 Key"——后者会把一次失败的调用
        报成成功。
        """
        return self.model is not None


def ask(question: str, *, top_k: int = 5, override: Optional[EndpointOverride] = None) -> Answer:
    """回答一个问题。

    ``override`` 非空时改用请求方填的端点；该端点的可用性不影响默认配置，
    反之亦然（各自的路由器与冷却表相互独立）。
    """
    results = ensure_retriever().search(question, top_k=top_k)
    session = resolve_session(override)

    answer, model = generate_answer_with_model(
        question,
        results,
        router=session.router,
        key_hint=CUSTOM_KEY_HINT if session.custom else "LLM_API_KEY",
    )
    return Answer(
        question=question,
        answer=answer,
        retrieved=len(results),
        model=model,
    )


def probe(override: Optional[EndpointOverride]) -> dict[str, Any]:
    """测试一个自定义端点是否可用（界面上"测试连接"按钮的后端）。"""
    return probe_endpoint(override)


def status() -> dict:
    """默认端点此刻的状态（自定义端点的状态由 :func:`probe` 单独反馈）。"""
    return llm_status()
