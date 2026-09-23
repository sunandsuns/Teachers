"""意图识别：一句话到底在问什么。

判错的代价不小（把倾诉判成行动清单，比不给建议更让人难受），所以这里
钉两件事：**句式信号要准**、**认不出时必须退回通用型**。
"""

from __future__ import annotations

import pytest

from server.services.intent import (
    ASK_DECISION,
    ASK_GENERAL,
    ASK_HOWTO,
    ASK_KNOWLEDGE,
    ASK_MEANING,
    ASK_VENT,
    ASK_WHY,
    GUIDANCE_EN,
    GUIDANCE_ZH,
    guidance,
    parse_intent,
)


class TestKinds:
    @pytest.mark.parametrize(
        "question",
        [
            "领导抢我功劳，我该忍还是该说？",
            "我该不该辞职去创业？",
            "要不要跟父母说实话",
        ],
    )
    def test_choice_is_decision(self, question):
        assert parse_intent(question).kind == ASK_DECISION

    @pytest.mark.parametrize(
        "question",
        [
            "朋友借钱不还，我该怎么开口要？",
            "如何面对失败和挫折？",
            "有什么办法能坚持下来",
        ],
    )
    def test_how_is_howto(self, question):
        assert parse_intent(question).kind == ASK_HOWTO

    @pytest.mark.parametrize(
        "question",
        ["为什么会有人总是针对我？", "我怎么会变成这样", "凭什么总是我背锅"],
    )
    def test_why_is_why(self, question):
        assert parse_intent(question).kind == ASK_WHY

    @pytest.mark.parametrize(
        "question",
        ["因材施教是什么意思？", "「无为」怎么理解"],
    )
    def test_meaning_is_meaning(self, question):
        assert parse_intent(question).kind == ASK_MEANING

    def test_naming_a_classic_is_knowledge(self):
        assert parse_intent("《道德经》怎么看竞争这件事？").kind == ASK_KNOWLEDGE

    @pytest.mark.parametrize(
        "question", ["我最近很焦虑，晚上睡不着", "今天被骂了，心里很委屈"],
    )
    def test_feelings_without_a_question_is_vent(self, question):
        """说了情绪却没提要求——此刻给行动清单是不合时宜的。"""
        assert parse_intent(question).kind == ASK_VENT

    def test_unrecognized_falls_back_to_general(self):
        assert parse_intent("今天天气不错").kind == ASK_GENERAL

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty_input_is_general(self, value):
        assert parse_intent(value).kind == ASK_GENERAL


class TestOptions:
    def test_splits_the_two_sides(self):
        """指令里得带上具体选项，才压得住"各有道理"式的骑墙。"""
        intent = parse_intent("领导抢我功劳，我该忍还是该说？")
        assert intent.options == ("忍", "说")

    def test_strips_particles_on_both_sides(self):
        intent = parse_intent("该忍还是该说")
        assert intent.options == ("忍", "说")

    def test_same_on_both_sides_is_not_a_choice(self):
        """"辞职还是不辞职"其实是是非题，交给"该不该"那条指令更准。"""
        assert parse_intent("辞职还是不辞职").options == ()

    def test_no_pivot_means_no_options(self):
        assert parse_intent("我该不该辞职").options == ()

    def test_long_sides_are_not_options(self):
        assert parse_intent("我在想是这份工作的问题还是我自己的问题呢").options == ()


class TestGuidance:
    def test_decision_without_options_still_gets_instruction(self):
        """认出是选择题却说不出选项时，指令要换成"给明确的该或不该"，
        而不是整个作废——这种情况最容易滑向"看你自己"。"""
        text = guidance(parse_intent("我该不该辞职？"))
        assert "该" in text and "不该" in text

    def test_decision_with_options_names_them(self):
        text = guidance(parse_intent("我该忍还是该说？"))
        assert "忍" in text and "说" in text

    def test_general_gets_nothing(self):
        """认不出题型就不追加指令：替用户改写他的问题比不给指令更糟。"""
        assert guidance(parse_intent("今天天气不错")) == ""

    def test_language_selects_the_table(self):
        intent = parse_intent("我该怎么开口要？")
        assert guidance(intent, lang="en") == GUIDANCE_EN[ASK_HOWTO]
        assert guidance(intent) == GUIDANCE_ZH[ASK_HOWTO]

    @pytest.mark.parametrize("kind", [ASK_HOWTO, ASK_WHY, ASK_MEANING, ASK_KNOWLEDGE, ASK_VENT])
    def test_every_kind_has_both_languages(self, kind):
        """只写一半的话，英文界面就退回中文指令了。"""
        assert GUIDANCE_ZH[kind]
        assert GUIDANCE_EN[kind]
