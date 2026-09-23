"""集成测试：追问的上下文与作答语言真的走到了模型那一步。

单元测试验的是"提示词拼得对"；这里验的是 **HTTP → 路由 → qa → LLM 门面**
这条链上，``history`` 与 ``lang`` 没有被哪一层悄悄丢掉——这类问题不会报错，
只会让追问继续像失忆，靠肉眼极难发现。

全程用假的 transport，不发起真实网络请求。
"""

import pytest

from server.services.llm import router as router_module
from server.services.llm import transport
from server.services.llm.prompt import SYSTEM_PROMPT

MODEL = "test-model"
CANNED = "## 你的处境\n你正卡在半途。"


@pytest.fixture
def capture(monkeypatch):
    """把 transport 换成假的，并把每次调用收到的 messages 记下来。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://fake/v1")
    monkeypatch.setenv("LLM_MODEL", MODEL)
    monkeypatch.setenv("LLM_MODEL_CANDIDATES", MODEL)

    calls: list[list[dict[str, str]]] = []

    def fake_chat(config, model, messages, **kwargs):
        calls.append(messages)
        return CANNED

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ())
    router_module.reset_router()
    yield calls
    router_module.reset_router()


class TestFollowUpContext:
    def test_history_reaches_the_model(self, client, capture):
        client.post(
            "/api/ask",
            json={
                "question": "那具体该怎么做？",
                "top_k": 2,
                "history": [{"question": "我总是半途而废", "answer": "先从小事做起"}],
            },
        )
        messages = capture[-1]
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert messages[1]["content"] == "我总是半途而废"
        assert messages[2]["content"] == "先从小事做起"

    def test_without_history_the_model_sees_a_single_question(self, client, capture):
        client.post("/api/ask", json={"question": "如何坚持？", "top_k": 2})
        assert [m["role"] for m in capture[-1]] == ["system", "user"]

    def test_current_turn_carries_the_retrieved_passages(self, client, capture):
        """当前轮必须带检索片段与出处，否则模型无处可引。"""
        client.post("/api/ask", json={"question": "上善若水怎么理解？", "top_k": 3})
        assert "片段" in capture[-1][-1]["content"]

    def test_several_turns_are_replayed_in_order(self, client, capture):
        body = {
            "question": "第三个问题",
            "top_k": 2,
            "history": [
                {"question": "第一个问题", "answer": "第一个回答"},
                {"question": "第二个问题", "answer": "第二个回答"},
            ],
        }
        client.post("/api/ask", json=body)
        contents = [m["content"] for m in capture[-1][:-1]]
        assert contents[1:3] == ["第一个问题", "第一个回答"]
        assert contents[3:5] == ["第二个问题", "第二个回答"]


class TestQuestionTypeGuidance:
    """题型要求是"回答不再答非所问"的关键，得确认它真的到了模型那一层。"""

    def test_a_choice_question_tells_the_model_to_pick_one(self, client, capture):
        client.post("/api/ask", json={"question": "我该忍还是该说？", "top_k": 2})
        system = capture[-1][0]["content"]
        assert "明确选一个" in system
        # 选项要写进指令里，光说"选一个"等于没说
        assert "忍" in system and "说" in system

    def test_a_howto_question_asks_for_actions(self, client, capture):
        client.post("/api/ask", json={"question": "我该怎么开口要？", "top_k": 2})
        assert "具体怎么做" in capture[-1][0]["content"]

    def test_english_gets_the_english_guidance(self, client, capture):
        client.post("/api/ask", json={"question": "我该忍还是该说？", "lang": "en", "top_k": 2})
        system = capture[-1][0]["content"]
        assert "pick one" in system
        assert "明确选一个" not in system

    def test_unrecognized_question_leaves_the_prompt_untouched(self, client, capture):
        """认不出题型就不追加指令——替用户改写他的问题比不给指令更糟。"""
        client.post("/api/ask", json={"question": "今天天气不错", "top_k": 2})
        assert capture[-1][0]["content"] == SYSTEM_PROMPT


class TestAnswerLanguage:
    def test_english_request_gets_english_system_prompt(self, client, capture):
        client.post("/api/ask", json={"question": "How do I stay calm?", "lang": "en", "top_k": 2})
        assert "life mentor" in capture[-1][0]["content"]

    def test_chinese_is_the_default(self, client, capture):
        client.post("/api/ask", json={"question": "如何保持平静？", "top_k": 2})
        assert "人生导师" in capture[-1][0]["content"]

    def test_unknown_language_falls_back_to_chinese(self, client, capture):
        """拼错的语言名不该让整次提问失败。"""
        response = client.post(
            "/api/ask", json={"question": "如何保持平静？", "lang": "klingon", "top_k": 2}
        )
        assert response.status_code == 200
        assert "人生导师" in capture[-1][0]["content"]

    def test_degraded_answer_follows_the_language(self, client, monkeypatch):
        """上游全挂时，英文界面不该收到中文的降级排版。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL_CANDIDATES", MODEL)

        def broken(config, model, messages, **kwargs):
            raise transport.LLMTransportError("HTTP 503：全挂了", 503)

        monkeypatch.setattr(transport, "chat", broken)
        monkeypatch.setattr(transport, "list_models", lambda config: ())
        router_module.reset_router()

        body = client.post(
            "/api/ask", json={"question": "如何保持平静？", "lang": "en", "top_k": 3}
        ).json()
        assert body["llm_used"] is False
        assert "经典怎么说" not in body["answer"]
        assert "What the classics say" in body["answer"]
