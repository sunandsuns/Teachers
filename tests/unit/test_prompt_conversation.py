"""提示词层：追问的对话编排与作答语言。

两件事都在 ``llm/prompt.py`` 里，都是纯函数，所以直接测——不必起 HTTP
客户端，也不必碰模型。
"""

from __future__ import annotations

import pytest

from server.services.llm.prompt import (
    DEFAULT_LANG,
    MAX_HISTORY_TURNS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EN,
    build_messages,
    local_fallback,
    normalize_lang,
    system_prompt,
)


class FakeResult:
    """检索结果的最小替身：提示词层只用到 source 与 content。"""

    def __init__(self, source: str, content: str) -> None:
        self.source = source
        self.content = content


def make_result(source: str = "《易经》· 乾卦", content: str = "天行健，君子以自强不息"):
    return FakeResult(source, content)


class TestNormalizeLang:
    def test_accepts_supported(self):
        assert normalize_lang("zh") == "zh"
        assert normalize_lang("en") == "en"

    def test_is_case_and_space_insensitive(self):
        assert normalize_lang("  EN ") == "en"

    @pytest.mark.parametrize("value", ["", "fr", None, 42, ["en"], "english"])
    def test_falls_back_to_chinese(self, value):
        """语言只是个渲染选项，认不出来就按中文，不该让整次提问失败。"""
        assert normalize_lang(value) == DEFAULT_LANG


class TestSystemPrompt:
    def test_chinese_prompt_marks_the_four_sections(self):
        for section in ("你的处境", "经典怎么说", "我的分析", "建议你怎么办"):
            assert section in system_prompt("zh")

    def test_english_prompt_is_english(self):
        prompt = system_prompt("en")
        assert "Your situation" in prompt
        assert "What the classics say" in prompt
        assert "你的处境" not in prompt

    def test_unknown_language_gets_chinese_prompt(self):
        assert system_prompt("klingon") == SYSTEM_PROMPT

    def test_both_prompts_forbid_inventing_quotes(self):
        """"不许编造原文"是这套提示词的底线，两种语言都得写着。"""
        assert "不许说成是经典说的" in SYSTEM_PROMPT
        assert "do not invent a quotation" in SYSTEM_PROMPT_EN

    def test_both_prompts_require_citing_the_source(self):
        assert "标注出处" in SYSTEM_PROMPT
        assert "cite its source" in SYSTEM_PROMPT_EN


class TestBuildMessages:
    def test_without_history_only_system_and_question(self):
        messages = build_messages("如何坚持？", [make_result()])
        assert [m["role"] for m in messages] == ["system", "user"]
        assert "如何坚持？" in messages[-1]["content"]

    def test_history_is_replayed_in_order(self):
        messages = build_messages(
            "那具体怎么做？",
            [make_result()],
            history=[("我总是半途而废", "先立一个小目标")],
        )
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert messages[1]["content"] == "我总是半途而废"
        assert messages[2]["content"] == "先立一个小目标"
        assert "那具体怎么做？" in messages[3]["content"]

    def test_keeps_only_the_most_recent_turns(self):
        history = [(f"问题{i}", f"回答{i}") for i in range(1, 7)]
        messages = build_messages("最后一个问题", [make_result()], history=history)
        replayed = [m["content"] for m in messages if m["role"] == "assistant"]
        assert len(replayed) == MAX_HISTORY_TURNS
        # 留下的必须是最新的那几轮，而不是最早的
        assert replayed[-1] == f"回答{len(history)}"
        assert "回答1" not in replayed

    def test_drops_empty_and_malformed_turns(self):
        messages = build_messages(
            "问题",
            [make_result()],
            history=[("", "空问题"), ("有问题的", ""), "不是一对", ("  有效  ", "答")],
        )
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert messages[1]["content"] == "有效"
        assert messages[2]["content"] == "答"

    def test_long_old_answers_are_trimmed(self):
        """旧回答只留梗概：全带进去上下文会成倍膨胀。"""
        long_answer = "字" * 5000
        messages = build_messages("追问", [make_result()], history=[("旧问题", long_answer)])
        assert len(messages[2]["content"]) < len(long_answer)
        assert messages[2]["content"].endswith("…")

    def test_history_turns_do_not_repeat_retrieved_passages(self):
        """历史轮次不附检索片段——模型要的是"聊过什么"，不是再读一遍当时引的原文。"""
        messages = build_messages("追问", [make_result()], history=[("旧问题", "旧回答")])
        assert "《易经》· 乾卦" not in messages[1]["content"]

    def test_english_request_uses_english_prompt_and_labels(self):
        messages = build_messages("How do I persist?", [make_result()], lang="en")
        assert messages[0]["content"] == SYSTEM_PROMPT_EN
        assert "Retrieved passages" in messages[-1]["content"]

    def test_current_turn_carries_the_retrieved_sources(self):
        """当前轮必须带检索片段与出处，模型才有可引用的东西。"""
        messages = build_messages("如何坚持？", [make_result()])
        assert "《易经》· 乾卦" in messages[-1]["content"]
        assert "天行健" in messages[-1]["content"]


class TestGuidance:
    """题型要求拼在系统提示词末尾；认不出题型时一个字都不该多加。"""

    def test_guidance_is_appended_to_the_system_prompt(self):
        messages = build_messages("我该忍还是该说？", [make_result()], guidance="必须明确选一个")
        assert messages[0]["content"].startswith(SYSTEM_PROMPT)
        assert "必须明确选一个" in messages[0]["content"]

    def test_empty_guidance_leaves_the_prompt_untouched(self):
        messages = build_messages("如何坚持？", [make_result()], guidance="")
        assert messages[0]["content"] == SYSTEM_PROMPT

    @pytest.mark.parametrize("value", ["   ", "\n"])
    def test_blank_guidance_is_ignored(self, value):
        messages = build_messages("如何坚持？", [make_result()], guidance=value)
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_english_gets_the_english_prompt_plus_guidance(self):
        messages = build_messages(
            "我该忍还是该说？", [make_result()], lang="en", guidance="Pick one."
        )
        assert messages[0]["content"].startswith(SYSTEM_PROMPT_EN)
        assert messages[0]["content"].endswith("Pick one.")


class TestFallbackLanguage:
    def test_english_fallback_has_no_chinese_sections(self):
        answer = local_fallback("How do I persist?", [make_result()], lang="en")
        assert "## What the classics say" in answer
        assert "经典怎么说" not in answer

    def test_english_empty_message(self):
        assert "Nothing in the classics" in local_fallback("q", [], lang="en")

    def test_english_error_note(self):
        answer = local_fallback("q", [make_result()], error="timeout", lang="en")
        assert "AI generation unavailable" in answer

    def test_chinese_is_the_default(self):
        assert "## 经典怎么说" in local_fallback("q", [make_result()])

    def test_unknown_language_gets_chinese_fallback(self):
        assert "## 经典怎么说" in local_fallback("q", [make_result()], lang="nope")
