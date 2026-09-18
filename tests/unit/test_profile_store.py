"""用户画像：存储规则、归纳解析、以及一次完整的归纳。

画像最怕"编"——所以解析层守得最细：分类不在集合里要丢、没有正文的要丢、
模型胡写的 confidence 要夹到 0~1。宁可少几条，也不要让用户看到一条凭空
推断出来的"他 30 岁"。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from server.services.db import Database
from server.services.profile import (
    DEFAULT_AVATAR,
    META_LAST_EXTRACT,
    PROFILE_SYSTEM_PROMPT,
    PROFILE_SYSTEM_PROMPT_EN,
    TRAIT_CATEGORIES,
    ProfileStore,
    build_profile_prompt,
    extract,
    parse_traits,
    pending_count,
)


@pytest.fixture
def store(tmp_path):
    return ProfileStore(Database(tmp_path / "history.db"))


def trait(category="性格", content="做事谨慎", evidence="我说我常犹豫", confidence=0.7):
    return {
        "category": category,
        "content": content,
        "evidence": evidence,
        "confidence": confidence,
    }


def record(question: str):
    return SimpleNamespace(question=question, answer="（模型的话）")


class TestStore:
    def test_upsert_then_list(self, store):
        assert store.upsert([trait()]) == 1
        traits = store.list()
        assert len(traits) == 1
        assert traits[0].category == "性格"
        assert traits[0].evidence == "我说我常犹豫"

    def test_same_trait_is_not_duplicated(self, store):
        """反复点"归纳"不该让画像越长越多份。"""
        store.upsert([trait(confidence=0.5)])
        store.upsert([trait(confidence=0.9)])

        traits = store.list()
        assert len(traits) == 1
        assert traits[0].confidence == 0.9

    def test_same_content_in_another_category_is_a_different_trait(self, store):
        store.upsert([trait(category="性格", content="爱读书")])
        store.upsert([trait(category="爱好", content="爱读书")])
        assert store.count() == 2

    def test_sorted_by_confidence(self, store):
        store.upsert([trait(content="低", confidence=0.2), trait(content="高", confidence=0.9)])
        assert [t.content for t in store.list()] == ["高", "低"]

    def test_delete_one(self, store):
        store.upsert([trait()])
        trait_id = store.list()[0].id

        assert store.delete(trait_id) is True
        assert store.list() == []
        assert store.delete(9999) is False

    def test_clear(self, store):
        store.upsert([trait(content="一"), trait(content="二")])
        assert store.clear() == 2
        assert store.count() == 0

    def test_upsert_nothing_is_a_noop(self, store):
        assert store.upsert([]) == 0
        assert store.count() == 0


class TestAvatar:
    def test_default(self, store):
        assert store.avatar() == DEFAULT_AVATAR

    def test_set_and_read_back(self, store):
        assert store.set_avatar("female") == "female"
        assert store.avatar() == "female"

    def test_case_and_space_insensitive(self, store):
        assert store.set_avatar("  FEMALE ") == "female"

    def test_unknown_value_falls_back(self, store):
        assert store.set_avatar("别的") == DEFAULT_AVATAR
        assert store.avatar() == DEFAULT_AVATAR


class TestExtractStamp:
    """「上次归纳到哪一刻」——界面靠它决定打开时要不要自动归纳。"""

    def test_never_extracted_is_zero(self, store):
        assert store.last_extract_ts() == 0.0

    def test_mark_and_read_back(self, store):
        store.mark_extracted(now=1000.0)
        assert store.last_extract_ts() == 1000.0

    def test_marking_again_overwrites(self, store):
        store.mark_extracted(now=1000.0)
        store.mark_extracted(now=2000.0)
        assert store.last_extract_ts() == 2000.0

    def test_garbage_in_meta_is_treated_as_never(self, store):
        """meta 是 TEXT 列，被人手改坏了也不该让画像页崩掉。"""
        store._write_meta(META_LAST_EXTRACT, "不是数字")
        assert store.last_extract_ts() == 0.0

    def test_status_reports_it(self, store):
        store.mark_extracted(now=1234.0)
        assert store.status()["last_extract_ts"] == 1234.0


class TestPendingCount:
    """「还有多少条提问没归纳过」。"""

    @staticmethod
    def at(ts: float):
        return SimpleNamespace(question="问", answer="答", created_ts=ts)

    def test_never_extracted_counts_everything(self):
        assert pending_count([self.at(10.0), self.at(20.0)], 0.0) == 2

    def test_only_newer_than_the_stamp(self):
        # > 而不是 >=：归纳恰好发生在那条提问的同一秒时，它已经被看过了
        assert pending_count([self.at(10.0), self.at(20.0)], 10.0) == 1

    def test_nothing_new(self):
        assert pending_count([self.at(10.0)], 20.0) == 0

    def test_no_records(self):
        assert pending_count([], 0.0) == 0


class TestParseTraits:
    def test_plain_json(self):
        raw = json.dumps([trait()], ensure_ascii=False)
        assert parse_traits(raw) == [trait()]

    def test_fenced_json(self):
        raw = "```json\n" + json.dumps([trait()], ensure_ascii=False) + "\n```"
        assert len(parse_traits(raw)) == 1

    def test_small_talk_around_the_json(self):
        raw = (
            "好的，我看出以下几点：\n"
            + json.dumps([trait()], ensure_ascii=False)
            + "\n希望有帮助。"
        )
        assert len(parse_traits(raw)) == 1

    def test_wrapped_in_an_object(self):
        raw = json.dumps({"traits": [trait()]}, ensure_ascii=False)
        assert len(parse_traits(raw)) == 1

    def test_unknown_category_is_dropped(self):
        """分类是封闭集合——界面上人形两侧的引线得有地方挂。"""
        raw = json.dumps([trait(category="星座")], ensure_ascii=False)
        assert parse_traits(raw) == []

    def test_entry_without_content_is_dropped(self):
        raw = json.dumps([{"category": "性格", "content": "  "}], ensure_ascii=False)
        assert parse_traits(raw) == []

    def test_confidence_is_clamped(self):
        high = json.dumps([trait(confidence=5)], ensure_ascii=False)
        low = json.dumps([trait(confidence=-2)], ensure_ascii=False)
        assert parse_traits(high)[0]["confidence"] == 1.0
        assert parse_traits(low)[0]["confidence"] == 0.0

    def test_missing_confidence_gets_a_neutral_value(self):
        raw = json.dumps([{"category": "性格", "content": "谨慎"}], ensure_ascii=False)
        assert parse_traits(raw)[0]["confidence"] == 0.5

    @pytest.mark.parametrize("raw", ["", "完全不是 JSON", "{", "[]", "[1, 2]", "null"])
    def test_unparsable_or_empty_input_yields_nothing(self, raw):
        """解析失败不是故障——画像保持原样，用户再点一次就好。"""
        assert parse_traits(raw) == []


class TestBuildPrompt:
    def test_only_the_users_own_words_are_used(self):
        prompt = build_profile_prompt([record("我最近很迷茫")])
        assert "我最近很迷茫" in prompt
        # 回答是模型说的，拿它当依据等于自己证明自己
        assert "（模型的话）" not in prompt

    def test_empty_records_produce_an_empty_list_body(self):
        assert "以下是这位用户问过的问题：" in build_profile_prompt([])

    def test_english_when_asked_for(self):
        prompt = build_profile_prompt([record("How do I choose?")], lang="en")
        assert "questions this user asked" in prompt
        assert "以下是这位用户问过的问题" not in prompt

    def test_unknown_language_falls_back_to_chinese(self):
        assert "以下是这位用户问过的问题" in build_profile_prompt([], lang="fr")


class TestPrompts:
    """两种语言的要求必须一致——否则英文用户拿到的画像会松一档。"""

    @pytest.mark.parametrize("prompt", [PROFILE_SYSTEM_PROMPT, PROFILE_SYSTEM_PROMPT_EN])
    def test_both_languages_forbid_guessing(self, prompt):
        assert "猜" in prompt or "guess" in prompt

    @pytest.mark.parametrize("prompt", [PROFILE_SYSTEM_PROMPT, PROFILE_SYSTEM_PROMPT_EN])
    def test_both_languages_list_the_closed_category_set(self, prompt):
        for category in TRAIT_CATEGORIES:
            assert category in prompt

    def test_english_prompt_keeps_chinese_categories(self):
        """分类是后端与界面约定的键，翻成英文就没地方挂了。"""
        assert "性格" in PROFILE_SYSTEM_PROMPT_EN


class FakeRouter:
    """只为测"拿到回答之后怎么处理"，不关心挑模型那一套。"""

    def __init__(self, content: str, enabled: bool = True) -> None:
        self.content = content
        self.config = SimpleNamespace(enabled=enabled)
        self.seen: list = []

    def chat(self, messages):
        self.seen.append(messages)
        return self.content, "fake-model"


class TestExtract:
    def test_no_records(self, store):
        """模型是好的，只是还没问过什么——这时才该说"没有记录"。"""
        result = extract(store, [], router=FakeRouter(""))
        assert result.extracted == 0
        assert result.llm_used is False
        assert result.error == "no_records"

    def test_llm_disabled(self, store):
        result = extract(store, [record("我最近很迷茫")], router=FakeRouter("", enabled=False))
        assert result.llm_used is False
        assert result.error == "llm_disabled"
        assert store.count() == 0

    def test_missing_model_outranks_missing_records(self, store):
        """两样都缺时报"没配模型"：那才是用户真正要动手解决的事。"""
        result = extract(store, [], router=FakeRouter("", enabled=False))
        assert result.error == "llm_disabled"

    def test_writes_parsed_traits(self, store):
        payload = json.dumps([trait(), trait(category="规划", content="想转行")], ensure_ascii=False)
        result = extract(store, [record("我总是犹豫很久才决定")], router=FakeRouter(payload))

        assert result.extracted == 2
        assert result.llm_used is True
        assert result.total == 2
        assert store.count() == 2

    def test_model_gave_nothing_usable(self, store):
        """模型答了，但里面没有可用的特征——这不算错误，只是这次没收获。"""
        result = extract(store, [record("随便问问")], router=FakeRouter("我不知道该说什么"))

        assert result.extracted == 0
        assert result.llm_used is True
        assert result.error == "nothing_usable"

    def test_extracting_stamps_the_moment(self, store):
        """归纳过就记下时刻，免得下次打开画像页又把同一批提问送一遍。"""
        extract(store, [record("我最近很迷茫")], router=FakeRouter("[]"))

        assert store.last_extract_ts() > 0

    def test_a_failed_call_does_not_stamp(self, store):
        """上游挂了什么都没看到，不该假装归纳过。"""
        from server.services.llm import LLMTransportError

        class BrokenRouter(FakeRouter):
            def chat(self, messages):
                raise LLMTransportError("HTTP 503：全挂了", 503)

        extract(store, [record("我最近很迷茫")], router=BrokenRouter(""))

        assert store.last_extract_ts() == 0.0

    def test_english_language_picks_the_english_prompt(self, store):
        router = FakeRouter("[]")
        extract(store, [record("How do I choose?")], router=router, lang="en")

        assert router.seen[0][0]["content"] == PROFILE_SYSTEM_PROMPT_EN

    def test_model_failure_leaves_the_profile_untouched(self, store):
        """上游挂了就往库里塞瞎编的特征，是最糟的结果。"""
        from server.services.llm import LLMTransportError

        class BrokenRouter(FakeRouter):
            def chat(self, messages):
                raise LLMTransportError("HTTP 503：全挂了", 503)

        result = extract(store, [record("我最近很迷茫")], router=BrokenRouter(""))

        assert result.extracted == 0
        assert result.llm_used is False
        assert "503" in result.error
        assert store.count() == 0

    def test_prompt_only_lists_questions(self, store):
        router = FakeRouter(json.dumps([trait()], ensure_ascii=False))
        extract(store, [record("我最近很迷茫")], router=router)

        user_message = router.seen[0][-1]["content"]
        assert "我最近很迷茫" in user_message
        assert "（模型的话）" not in user_message
