"""历史人物候选池：名录解析、画像指纹、周判定、以及一次完整的评定。

这个功能有两处最容易出错，测试也主要守这两处：

1. **名录是用户可编辑的数据**。一条缺字段的记录、一个写了 ``../`` 的画像名，
   都不该让画像页崩掉或让接口读到程序目录外的文件。所以解析层一律"不合格就
   丢掉那一条"，而不是抛异常。
2. **"最像你"应当是稳定的**。跨周之后画像没变，答案就该还是同一个人；否则
   用户每周打开都会看到一个新人，那不是"最像你"，那是抽签。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.services import figures as figures_module
from server.services.db import Database
from server.services.figures import (
    FIGURES_PROMPTS,
    REASON_LIMIT,
    TRAIT_LIMIT,
    Figure,
    build_figure_prompt,
    by_gender,
    choose_figure,
    describe,
    find,
    load_figures,
    parse_selection,
    portrait_path,
    should_evaluate,
    traits_signature,
    week_key,
)
from server.services.llm import LLMTransportError
from server.services.profile import ProfileStore

TRAITS = [
    {
        "category": "性格",
        "content": "喜欢独处，不爱应酬",
        "evidence": "我说我周末只想一个人待着",
        "confidence": 0.8,
    },
    {
        "category": "爱好",
        "content": "爱读古书",
        "evidence": "我常翻《庄子》",
        "confidence": 0.6,
    },
]


def stored_traits(pairs=TRAITS):
    """画像条目在库里是对象，不是字典——指纹只看 category 与 content。"""
    return [SimpleNamespace(category=p["category"], content=p["content"]) for p in pairs]


def record(**overrides) -> dict:
    base = {
        "id": "taoyuanming",
        "gender": "male",
        "portrait": "taoyuanming.webp",
        "name_zh": "陶渊明",
        "name_en": "Tao Yuanming",
        "era_zh": "东晋",
        "era_en": "Eastern Jin",
        "blurb_zh": "不为五斗米折腰，归去来兮。",
        "blurb_en": "He would not bow for five pecks of rice.",
        "traits_zh": "淡泊、自守、爱田园",
        "traits_en": "detached, self-possessed, fond of the fields",
        "credit_zh": "画像：公有领域",
        "credit_en": "Portrait: public domain",
    }
    base.update(overrides)
    return base


#: 一份自造的名录：测试不依赖 ``figures/figures.json`` 的内容，
#: 用户增删候选人不该让测试变红（那份名录另有一条整体校验）。
POOL = (
    Figure(
        id="taoyuanming",
        gender="male",
        portrait="taoyuanming.webp",
        text={
            "name_zh": "陶渊明",
            "name_en": "Tao Yuanming",
            "era_zh": "东晋",
            "era_en": "Eastern Jin",
            "blurb_zh": "不为五斗米折腰。",
            "blurb_en": "He would not bow for five pecks of rice.",
            "traits_zh": "淡泊、自守",
            "traits_en": "detached and self-possessed",
            "credit_zh": "画像：公有领域",
            "credit_en": "Portrait: public domain",
        },
    ),
    Figure(
        id="libai",
        gender="male",
        portrait="libai.webp",
        text={
            "name_zh": "李白",
            "name_en": "Li Bai",
            "era_zh": "唐",
            "era_en": "Tang",
            "blurb_zh": "斗酒诗百篇。",
            "blurb_en": "A hundred poems to a jug of wine.",
            "traits_zh": "豪放、不受拘束",
            "traits_en": "unbridled",
            "credit_zh": "画像：公有领域",
            "credit_en": "Portrait: public domain",
        },
    ),
    Figure(
        id="liqingzhao",
        gender="female",
        portrait="liqingzhao.webp",
        text={
            "name_zh": "李清照",
            "name_en": "Li Qingzhao",
            "era_zh": "宋",
            "era_en": "Song",
            "blurb_zh": "婉约词宗。",
            "blurb_en": "The great master of the quiet, restrained mode.",
            "traits_zh": "细腻、较真",
            "traits_en": "delicate, exacting",
            "credit_zh": "画像：公有领域",
            "credit_en": "Portrait: public domain",
        },
    ),
)


@pytest.fixture
def pool(monkeypatch):
    """把进程级候选池换成上面这份自造名录。"""
    monkeypatch.setattr(figures_module, "_pool", POOL)
    return POOL


@pytest.fixture
def store(tmp_path):
    return ProfileStore(Database(tmp_path / "history.db"))


class FakeRouter:
    """只为测"拿到回答之后怎么处理"，不关心挑模型那一套。"""

    def __init__(self, content: str, enabled: bool = True) -> None:
        self.content = content
        self.config = SimpleNamespace(enabled=enabled)
        self.seen: list = []

    def chat(self, messages):
        self.seen.append(messages)
        return self.content, "fake-model"


class BrokenRouter(FakeRouter):
    def chat(self, messages):
        raise LLMTransportError("HTTP 503：全挂了", 503)


# ── 名录 ────────────────────────────────────────────────────────────────


class TestParseRecords:
    """名录是数据，坏一条只丢一条。"""

    def test_good_record(self):
        figure = figures_module._parse_figure(record())
        assert figure is not None
        assert figure.id == "taoyuanming"
        assert figure.gender == "male"
        assert figure.name("zh") == "陶渊明"
        assert figure.name("en") == "Tao Yuanming"

    @pytest.mark.parametrize(
        "bad",
        [
            "不是字典",
            None,
            {},
            record(id=""),
            record(gender=""),
            record(gender="别的"),
            record(portrait=""),
            record(name_zh=""),
            record(era_zh="   "),
            record(credit_zh=""),
        ],
    )
    def test_unusable_records_are_dropped(self, bad):
        assert figures_module._parse_figure(bad) is None

    @pytest.mark.parametrize(
        "portrait",
        ["../.env", "..\\..\\key.txt", "portraits/../../x.webp", "/etc/passwd"],
    )
    def test_portrait_must_be_a_bare_filename(self, portrait):
        """一条带 ../ 的记录就能让接口读到程序目录外的文件，在解析层就挡掉。"""
        assert figures_module._parse_figure(record(portrait=portrait)) is None

    def test_english_is_optional_and_falls_back(self):
        """译文暂缺时显示中文，而不是一片空白。"""
        raw = record()
        raw.pop("name_en")
        figure = figures_module._parse_figure(raw)
        assert figure.name("en") == "陶渊明"

    def test_unknown_language_falls_back_to_chinese(self):
        assert figures_module._parse_figure(record()).name("fr") == "陶渊明"


class TestLoadFigures:
    def write(self, root: Path, payload) -> Path:
        directory = root / "figures"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "figures.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return directory

    def test_reads_a_list(self, tmp_path):
        self.write(tmp_path, [record(), record(id="libai", name_zh="李白")])
        assert [f.id for f in load_figures(tmp_path)] == ["taoyuanming", "libai"]

    def test_reads_a_wrapped_object(self, tmp_path):
        """``{"figures": [...]}`` 也认——将来想在文件里加版本号不必改代码。"""
        self.write(tmp_path, {"figures": [record()]})
        assert len(load_figures(tmp_path)) == 1

    def test_duplicate_ids_keep_the_first(self, tmp_path):
        self.write(tmp_path, [record(), record(name_zh="另一个陶渊明")])
        figures = load_figures(tmp_path)
        assert len(figures) == 1
        assert figures[0].name("zh") == "陶渊明"

    def test_broken_json_yields_nothing(self, tmp_path):
        """用户手改出一个语法错误是常事；整份读不出来也不该让接口报错。"""
        directory = tmp_path / "figures"
        directory.mkdir()
        (directory / "figures.json").write_text("{坏掉的", encoding="utf-8")
        assert load_figures(tmp_path) == ()

    def test_missing_file_yields_nothing(self, tmp_path):
        assert load_figures(tmp_path) == ()

    def test_wrong_shape_yields_nothing(self, tmp_path):
        self.write(tmp_path, {"figures": "不是列表"})
        assert load_figures(tmp_path) == ()


class TestShippedPool:
    """随包发出的那份名录得站得住——它坏了整个功能就静悄悄地没了。"""

    def test_loads_and_is_bilingual(self):
        pool = load_figures()
        assert pool, "figures/figures.json 读不出任何候选人"

        for figure in pool:
            for field in ("name", "era", "blurb", "traits", "credit"):
                assert figure.get(field, "zh"), f"{figure.id} 缺 {field}_zh"
                assert figure.get(field, "en"), f"{figure.id} 缺 {field}_en"

    def test_ids_are_unique(self):
        ids = [f.id for f in load_figures()]
        assert len(ids) == len(set(ids))

    def test_both_genders_are_represented(self):
        pool = load_figures()
        assert by_gender("male", pool)
        assert by_gender("female", pool)

    def test_every_portrait_is_on_disk(self):
        missing = [
            f.portrait for f in load_figures() if portrait_path(f.id) is None
        ]
        assert not missing, f"名录里登记了但磁盘上没有的画像：{missing}"


class TestLookup:
    def test_by_gender(self, pool):
        assert [f.id for f in by_gender("male")] == ["taoyuanming", "libai"]
        assert [f.id for f in by_gender("female")] == ["liqingzhao"]

    def test_by_gender_does_not_guess(self, pool):
        assert by_gender("别的") == []
        assert by_gender("") == []

    def test_find(self, pool):
        assert find("libai").name("zh") == "李白"
        assert find("查无此人") is None

    def test_portrait_path_uses_the_registered_filename(self, pool, monkeypatch, tmp_path):
        monkeypatch.setattr(figures_module, "PROJECT_ROOT", tmp_path)
        target = tmp_path / "figures" / "portraits" / "taoyuanming.webp"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"webp")

        assert portrait_path("taoyuanming") == target

    def test_portrait_path_is_none_when_the_file_is_gone(self, pool, monkeypatch, tmp_path):
        monkeypatch.setattr(figures_module, "PROJECT_ROOT", tmp_path)
        assert portrait_path("taoyuanming") is None

    def test_portrait_path_refuses_ids_outside_the_pool(self, pool):
        """路径由名录推出，而不是由调用者拼——穿越从源头就没有入口。"""
        assert portrait_path("../../.env") is None
        assert portrait_path("/etc/passwd") is None


# ── 指纹与周 ────────────────────────────────────────────────────────────


class TestTraitsSignature:
    def test_same_content_same_signature(self):
        a = stored_traits()
        b = stored_traits()
        assert traits_signature(a) == traits_signature(b)

    def test_order_does_not_matter(self):
        """抽取回来的顺序按把握度排，抖动是常态，那不等于画像变了。"""
        forward = stored_traits()
        backward = list(reversed(forward))
        assert traits_signature(forward) == traits_signature(backward)

    def test_changed_content_changes_it(self):
        other = stored_traits([TRAITS[0], {**TRAITS[1], "content": "改成了别的"}])
        assert traits_signature(stored_traits()) != traits_signature(other)

    def test_confidence_and_evidence_are_ignored(self):
        """置信度和依据都是"怎么说"，不是"说的是什么"。"""
        pairs = [
            SimpleNamespace(category="性格", content="喜欢独处，不爱应酬"),
            SimpleNamespace(category="爱好", content="爱读古书"),
        ]
        assert traits_signature(pairs) == traits_signature(stored_traits())

    def test_category_is_part_of_the_identity(self):
        moved = stored_traits([TRAITS[0], {**TRAITS[1], "category": "性格"}])
        assert traits_signature(stored_traits()) != traits_signature(moved)

    def test_empty_profile_has_a_signature(self):
        assert traits_signature([])

    def test_it_is_short(self):
        assert len(traits_signature(stored_traits())) == 16


class TestWeekKey:
    @staticmethod
    def at(year: int, month: int, day: int) -> float:
        return datetime(year, month, day, 12, 0).timestamp()

    def test_shape(self):
        assert week_key().count("-W") == 1

    def test_monday_starts_the_week(self):
        # 2026-09-14 是周一，2026-09-20 是周日 —— 同一周
        assert week_key(self.at(2026, 9, 14)) == week_key(self.at(2026, 9, 20))

    def test_next_monday_is_the_next_week(self):
        assert week_key(self.at(2026, 9, 14)) != week_key(self.at(2026, 9, 21))

    def test_zero_padded(self):
        assert week_key(self.at(2026, 1, 5)).endswith("-W02")


class TestShouldEvaluate:
    """一周之内答案不变；跨周而画像没变，答案也不该变。"""

    NOW = datetime(2026, 9, 17, 12, 0).timestamp()

    def stored(self, **overrides) -> dict:
        base = {
            "id": "taoyuanming",
            "week": week_key(self.NOW),
            "sig": traits_signature(stored_traits()),
        }
        base.update(overrides)
        return base

    def test_never_evaluated(self):
        assert should_evaluate({}, stored_traits(), now=self.NOW) is True

    def test_record_without_a_figure(self):
        assert should_evaluate({"week": "2026-W01"}, stored_traits(), now=self.NOW) is True

    def test_same_week_is_left_alone(self):
        assert should_evaluate(self.stored(), stored_traits(), now=self.NOW) is False

    def test_cross_week_with_an_unchanged_profile_keeps_the_same_person(self):
        """这正是"最像你"该有的样子：人没变，答案就不该变。"""
        old = self.stored(week="2026-W30")
        assert should_evaluate(old, stored_traits(), now=self.NOW) is False

    def test_cross_week_with_a_changed_profile(self):
        old = self.stored(week="2026-W30", sig="0000000000000000")
        assert should_evaluate(old, stored_traits(), now=self.NOW) is True


# ── 提示词与解析 ────────────────────────────────────────────────────────


class TestPrompts:
    @pytest.mark.parametrize("prompt", [FIGURES_PROMPTS["zh"], FIGURES_PROMPTS["en"]])
    def test_both_languages_forbid_choosing_by_identity(self, prompt):
        """按职业/身份比，这个功能就退化成星座配对了。"""
        assert "身份" in prompt or "status" in prompt
        assert "职业" in prompt or "occupation" in prompt

    @pytest.mark.parametrize("prompt", [FIGURES_PROMPTS["zh"], FIGURES_PROMPTS["en"]])
    def test_both_languages_confine_the_choice_to_the_list(self, prompt):
        assert "名录" in prompt or "list" in prompt

    @pytest.mark.parametrize("prompt", [FIGURES_PROMPTS["zh"], FIGURES_PROMPTS["en"]])
    def test_both_languages_demand_the_reason(self, prompt):
        assert "reason_zh" in prompt
        assert "reason_en" in prompt


class TestBuildPrompt:
    def test_lists_profile_and_candidates(self, pool):
        prompt = build_figure_prompt(stored_traits(), pool)
        assert "喜欢独处，不爱应酬" in prompt
        assert "taoyuanming" in prompt
        assert "陶渊明" in prompt
        assert "liqingzhao" in prompt

    def test_does_not_leak_the_evidence_column(self, pool):
        """依据是原话，模型只该看归纳后的判断——否则等于把语料又送一遍。"""
        prompt = build_figure_prompt(stored_traits(), pool)
        assert "我周末只想一个人待着" not in prompt

    def test_trait_count_is_capped(self, pool):
        many = [
            SimpleNamespace(category="性格", content=f"第{i}条")
            for i in range(TRAIT_LIMIT + 10)
        ]
        prompt = build_figure_prompt(many, pool)
        assert f"第{TRAIT_LIMIT - 1}条" in prompt
        assert f"第{TRAIT_LIMIT}条" not in prompt

    def test_english_when_asked_for(self, pool):
        prompt = build_figure_prompt(stored_traits(), pool, lang="en")
        assert "The user's profile" in prompt
        assert "这位用户的画像" not in prompt

    def test_unknown_language_falls_back_to_chinese(self, pool):
        assert "这位用户的画像" in build_figure_prompt(stored_traits(), pool, lang="fr")


class TestParseSelection:
    def test_plain_json(self):
        raw = json.dumps({"id": "libai", "reason_zh": "豪放", "reason_en": "unbridled"})
        assert parse_selection(raw) == {
            "id": "libai",
            "reason_zh": "豪放",
            "reason_en": "unbridled",
        }

    def test_fenced_json(self):
        raw = '```json\n{"id": "libai"}\n```'
        assert parse_selection(raw)["id"] == "libai"

    def test_small_talk_around_the_json(self):
        raw = '我认为是这位：{"id": "libai", "reason_zh": "爱酒"} 希望有帮助。'
        assert parse_selection(raw)["id"] == "libai"

    def test_reason_is_trimmed(self):
        raw = json.dumps({"id": "libai", "reason_zh": "长" * (REASON_LIMIT + 50)})
        assert len(parse_selection(raw)["reason_zh"]) == REASON_LIMIT

    @pytest.mark.parametrize("raw", ["", "我不知道该说什么", "{", "[]", "[1, 2]", "null"])
    def test_unparsable_input_yields_an_empty_id(self, raw):
        """解析不出来不抛异常——为此让整次评定失败不值得。"""
        assert parse_selection(raw)["id"] == ""

    def test_missing_fields_are_empty_strings(self):
        assert parse_selection('{"id": "libai"}')["reason_zh"] == ""


# ── 一次评定 ────────────────────────────────────────────────────────────


class TestChooseFigure:
    def test_picks_and_stores(self, pool, store):
        router = FakeRouter(
            json.dumps(
                {"id": "taoyuanming", "reason_zh": "你也不爱应酬", "reason_en": "You shun company too"},
                ensure_ascii=False,
            )
        )
        result = choose_figure(store, stored_traits(), gender="male", router=router)

        assert result.figure_id == "taoyuanming"
        assert result.llm_used is True
        assert result.error == ""

        saved = store.get_figure("male")
        assert saved["id"] == "taoyuanming"
        assert saved["reason_zh"] == "你也不爱应酬"
        assert saved["week"] == week_key()
        assert saved["sig"] == traits_signature(stored_traits())
        assert saved["ts"] > 0

    def test_the_two_genders_are_kept_apart(self, pool, store):
        choose_figure(
            store,
            stored_traits(),
            gender="male",
            router=FakeRouter('{"id": "libai"}'),
        )
        choose_figure(
            store,
            stored_traits(),
            gender="female",
            router=FakeRouter('{"id": "liqingzhao"}'),
        )

        assert store.get_figure("male")["id"] == "libai"
        assert store.get_figure("female")["id"] == "liqingzhao"

    def test_only_same_gender_candidates_are_offered(self, pool, store):
        """男女开关是筛选池——男性池里不该出现李清照。"""
        router = FakeRouter('{"id": "libai"}')
        choose_figure(store, stored_traits(), gender="male", router=router)

        user_message = router.seen[0][-1]["content"]
        assert "liqingzhao" not in user_message
        assert "taoyuanming" in user_message

    def test_same_week_second_call_is_not_needed(self, pool, store):
        choose_figure(store, stored_traits(), gender="male", router=FakeRouter('{"id": "libai"}'))
        assert should_evaluate(store.get_figure("male"), stored_traits()) is False

    def test_empty_profile_asks_for_nothing(self, pool, store):
        """还没有画像可依，选谁都成了瞎猜。"""
        router = FakeRouter('{"id": "libai"}')
        result = choose_figure(store, [], gender="male", router=router)

        assert result.figure_id == ""
        assert result.error == "no_traits"
        assert router.seen == []
        assert store.get_figure("male") == {}

    def test_llm_disabled(self, pool, store):
        result = choose_figure(
            store, stored_traits(), gender="male", router=FakeRouter("", enabled=False)
        )
        assert result.llm_used is False
        assert result.error == "llm_disabled"
        assert store.get_figure("male") == {}

    def test_llm_disabled_outranks_an_empty_profile(self, pool, store):
        """两样都缺时报"没配模型"：那是用户真正要动手解决的事（与归纳一致）。"""
        result = choose_figure(
            store, [], gender="male", router=FakeRouter("", enabled=False)
        )
        assert result.error == "llm_disabled"

    def test_model_failure_leaves_the_old_choice_alone(self, pool, store):
        """上游抖动不该让人物随机换一个——宁可停在旧的判断上。"""
        store.set_figure("male", {"id": "libai", "week": "2026-W01", "sig": "x"})

        result = choose_figure(store, stored_traits(), gender="male", router=BrokenRouter(""))

        assert result.figure_id == ""
        assert result.llm_used is False
        assert "503" in result.error
        assert store.get_figure("male")["id"] == "libai"

    def test_a_name_outside_the_pool_is_refused(self, pool, store):
        """模型编了一个人，不能就这么存下去——界面上会显示出查不到的人。"""
        result = choose_figure(
            store,
            stored_traits(),
            gender="male",
            router=FakeRouter('{"id": "苏东坡", "reason_zh": "…"}'),
        )

        assert result.figure_id == ""
        assert result.llm_used is True
        assert result.error == "not_in_pool"
        assert store.get_figure("male") == {}

    def test_unparsable_output_is_refused(self, pool, store):
        result = choose_figure(
            store, stored_traits(), gender="male", router=FakeRouter("我说不好")
        )
        assert result.error == "not_in_pool"
        assert store.get_figure("male") == {}

    def test_the_chosen_gender_filter_limits_what_can_be_stored(self, pool, store):
        """女性池里来了个男性 id，同样不算数。"""
        result = choose_figure(
            store, stored_traits(), gender="female", router=FakeRouter('{"id": "libai"}')
        )
        assert result.error == "not_in_pool"
        assert store.get_figure("female") == {}

    def test_english_asks_in_english(self, pool, store):
        router = FakeRouter('{"id": "libai"}')
        choose_figure(store, stored_traits(), gender="male", lang="en", router=router)
        assert router.seen[0][0]["content"] == FIGURES_PROMPTS["en"]

    def test_no_pool_at_all(self, monkeypatch, store):
        monkeypatch.setattr(figures_module, "_pool", ())
        result = choose_figure(store, stored_traits(), gender="male", router=FakeRouter(""))
        assert result.error == "no_pool"


class TestDescribe:
    def test_shape(self, pool, store):
        store.set_figure(
            "male",
            {
                "id": "taoyuanming",
                "reason_zh": "你也不爱应酬",
                "reason_en": "You shun company too",
                "week": "2026-W38",
                "ts": datetime(2026, 9, 17, 12, 0).timestamp(),
            },
        )
        info = describe(find("taoyuanming"), store.get_figure("male"), "zh")

        assert info["id"] == "taoyuanming"
        assert info["name"] == "陶渊明"
        assert info["era"] == "东晋"
        assert info["reason"] == "你也不爱应酬"
        assert info["portrait"] == "/api/profile/figure/portrait/taoyuanming"
        assert info["week"] == "2026-W38"
        assert info["chosen_at"] == "2026-09-17"
        assert info["pool_size"] == 2

    def test_english_reason(self, pool, store):
        store.set_figure(
            "male",
            {"id": "taoyuanming", "reason_zh": "中文理由", "reason_en": "English reason"},
        )
        info = describe(find("taoyuanming"), store.get_figure("male"), "en")
        assert info["reason"] == "English reason"
        assert info["name"] == "Tao Yuanming"

    def test_missing_translation_falls_back_to_chinese(self, pool, store):
        store.set_figure("male", {"id": "taoyuanming", "reason_zh": "中文理由"})
        assert describe(find("taoyuanming"), store.get_figure("male"), "en")["reason"] == "中文理由"

    def test_names_come_from_the_pool_not_the_record(self, pool, store):
        """存的是 id 与理由；改了名录就该立刻生效，不必等下一次评定。"""
        store.set_figure("male", {"id": "taoyuanming", "reason_zh": "…", "name_zh": "旧名字"})
        assert describe(find("taoyuanming"), store.get_figure("male"), "zh")["name"] == "陶渊明"

    def test_no_figure_is_all_empty(self, pool, store):
        info = describe(None, {}, "zh")
        assert info["id"] == ""
        assert info["name"] == ""
        assert info["portrait"] == ""
        assert info["pool_size"] == 0

    def test_broken_timestamp_is_dropped(self, pool, store):
        store.set_figure("male", {"id": "taoyuanming", "ts": "不是时间"})
        assert describe(find("taoyuanming"), store.get_figure("male"), "zh")["chosen_at"] == ""


class TestStoreRoundTrip:
    """存在 meta 表里的那段 JSON：写坏了、性别认不出，都只管返回空。"""

    def test_nothing_stored(self, store):
        assert store.get_figure("male") == {}

    def test_round_trip(self, store):
        store.set_figure("female", {"id": "liqingzhao", "reason_zh": "细腻"})
        assert store.get_figure("female")["reason_zh"] == "细腻"

    def test_unknown_gender_writes_nothing(self, store):
        store.set_figure("别的", {"id": "libai"})
        assert store.get_figure("male") == {}
        assert store.get_figure("female") == {}

    def test_corrupt_record_is_treated_as_absent(self, store):
        store._write_meta("figure:male", "不是 JSON")
        assert store.get_figure("male") == {}

    def test_a_json_array_is_not_a_record(self, store):
        store._write_meta("figure:male", "[1, 2]")
        assert store.get_figure("male") == {}
