"""集成测试：画像接口在 HTTP 上跑通。

包括"模型可用时真的写进库"这条完整链路——用假 transport，不联网。
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from server.services import figures as figures_service
from server.services.llm import router as router_module
from server.services.llm import transport

MODEL = "test-model"

TRAITS = [
    {
        "category": "性格",
        "content": "做事偏谨慎，习惯想清楚再动手",
        "evidence": "我说我总是犹豫很久才决定",
        "confidence": 0.8,
    }
]

#: 自造的名录。测试不依赖 ``figures/figures.json`` 的内容——那份名录是用户可
#: 增删的语料，改它不该让接口测试变红（它另有一条整体校验）。
FIGURES = [
    {
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
    },
    {
        "id": "liqingzhao",
        "gender": "female",
        "portrait": "liqingzhao.webp",
        "name_zh": "李清照",
        "name_en": "Li Qingzhao",
        "era_zh": "宋",
        "era_en": "Song",
        "blurb_zh": "婉约词宗，一生较真。",
        "blurb_en": "The great master of the quiet, restrained mode.",
        "traits_zh": "细腻、较真",
        "traits_en": "delicate, exacting",
        "credit_zh": "画像：公有领域",
        "credit_en": "Portrait: public domain",
    },
]

SELECTION = {
    "id": "taoyuanming",
    "reason_zh": "你也不爱应酬",
    "reason_en": "You shun company too",
}

#: 名录在提问里的排法：``- id｜名字｜时代｜性情``
_LISTED_ID = re.compile(r"^- (\S+?)｜", re.M)

#: 一行就把"名录被认出来了"这件事写清楚——两个假模型都要用它
_IS_FIGURE_PROMPT = ("历史人物名录", "historical figures")


def install_fake_transport(monkeypatch, responder):
    """配置成"有密钥"，把 transport 换成 ``responder(messages) -> str``。

    返回一个记录器：``.messages`` 是历次送出的消息，用来断言内容真的送进了
    模型（以及用的是哪种语言）。
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://fake/v1")
    monkeypatch.setenv("LLM_MODEL", MODEL)
    monkeypatch.setenv("LLM_MODEL_CANDIDATES", MODEL)

    sent: list[list[dict]] = []

    def fake_chat(config, model, messages, **kwargs):
        sent.append(messages)
        return responder(messages)

    monkeypatch.setattr(transport, "chat", fake_chat)
    monkeypatch.setattr(transport, "list_models", lambda config: ())
    router_module.reset_router()
    return SimpleNamespace(messages=sent)


@pytest.fixture
def fake_model(monkeypatch):
    """只有归纳：任何提问都得到同一段画像特征。"""
    recorder = install_fake_transport(
        monkeypatch, lambda messages: json.dumps(TRAITS, ensure_ascii=False)
    )
    yield recorder
    router_module.reset_router()


@pytest.fixture
def fake_models(monkeypatch):
    """"归纳"与"挑人物"两个接口都要模型，用同一个假 transport。

    回答按**提问的台词**分开：认出是行家的口吻（名录）就从名录里挑第一个，
    否则给画像特征。挑"第一个"而不是固定返回一个 id，是为了让"男女开关确实
    换了池子"这件事可断言——顺带也证明了名录确实被列进了提问里。
    """

    def responder(messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        if any(marker in system for marker in _IS_FIGURE_PROMPT):
            found = _LISTED_ID.findall(user)
            return json.dumps(
                {**SELECTION, "id": found[0] if found else ""}, ensure_ascii=False
            )
        return json.dumps(TRAITS, ensure_ascii=False)

    recorder = install_fake_transport(monkeypatch, responder)
    yield recorder
    router_module.reset_router()


@pytest.fixture
def figure_pool(monkeypatch):
    """把进程级候选池换成上面那份自造名录。"""
    pool = tuple(figures_service._parse_figure(raw) for raw in FIGURES)
    monkeypatch.setattr(figures_service, "_pool", pool)
    return pool


def build_profile(client) -> None:
    """走一遍真实路径，把画像填上（没有画像就没法挑人物）。"""
    client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
    client.post("/api/profile/extract")


class TestProfileBasics:
    def test_empty_profile(self, client):
        body = client.get("/api/profile").json()
        assert body["available"] is True
        assert body["traits"] == []
        assert body["avatar"] == "male"
        # 分类清单给界面排引线用，必须是完整的封闭集合
        assert "性格" in body["categories"]
        assert "规划" in body["categories"]

    def test_nothing_pending_on_a_fresh_install(self, client):
        """没问过问题就没有待归纳的东西，画像页不该自动去调模型。"""
        assert client.get("/api/profile").json()["pending"] == 0

    def test_pending_counts_questions_asked_after_the_last_extraction(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        assert client.get("/api/profile").json()["pending"] == 1

        client.post("/api/profile/extract")
        # 归纳过了，这批提问就不再算"新"
        assert client.get("/api/profile").json()["pending"] == 0

        client.post("/api/ask", json={"question": "那我该怎么办", "top_k": 1})
        assert client.get("/api/profile").json()["pending"] == 1

    def test_extract_without_model_reports_why(self, client):
        """没有模型不是 500——画像本来就是附加功能。"""
        body = client.post("/api/profile/extract").json()
        assert body["ok"] is False
        assert body["llm_used"] is False
        assert body["error"] == "llm_disabled"

    def test_extract_with_no_history_says_so(self, client, fake_model):
        body = client.post("/api/profile/extract").json()
        assert body["ok"] is False
        assert body["error"] == "no_records"


class TestLanguage:
    """归纳提示词的语言。

    ``/api/ask`` 也会走同一个假 transport，所以要看的是**最后一次**调用——
    归纳排在求教之后。
    """

    def test_english_asks_the_model_in_english(self, client, fake_model):
        client.post("/api/ask", json={"question": "How do I choose?", "top_k": 1})
        client.post("/api/profile/extract", json={"lang": "en"})

        system, user = fake_model.messages[-1]
        assert "questions this user asked" in user["content"]
        # 分类仍然是中文封闭集合，否则界面上的引线没有落脚点
        assert "性格" in system["content"]

    def test_missing_language_defaults_to_chinese(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract", json={})

        assert "以下是这位用户问过的问题" in fake_model.messages[-1][-1]["content"]


class TestAvatar:
    def test_can_be_switched_and_read_back(self, client):
        body = client.put("/api/profile/avatar", json={"gender": "female"}).json()
        assert body["avatar"] == "female"
        assert client.get("/api/profile").json()["avatar"] == "female"

    def test_unknown_value_falls_back(self, client):
        body = client.put("/api/profile/avatar", json={"gender": "别的"}).json()
        assert body["avatar"] == "male"


class TestExtractWithModel:
    def test_traits_are_stored_and_listed(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})

        body = client.post("/api/profile/extract").json()
        assert body["ok"] is True
        assert body["extracted"] == 1

        profile = client.get("/api/profile").json()
        assert profile["total"] == 1
        assert profile["traits"][0]["category"] == "性格"
        assert profile["traits"][0]["evidence"]

    def test_extract_twice_does_not_duplicate(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})

        client.post("/api/profile/extract")
        client.post("/api/profile/extract")

        assert client.get("/api/profile").json()["total"] == 1

    def test_delete_one_trait(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")
        trait_id = client.get("/api/profile").json()["traits"][0]["id"]

        assert client.delete(f"/api/profile/traits/{trait_id}").json()["deleted"] == 1
        assert client.get("/api/profile").json()["total"] == 0

    def test_delete_missing_trait_is_a_404(self, client):
        assert client.delete("/api/profile/traits/9999").status_code == 404

    def test_clear_the_whole_profile(self, client, fake_model):
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")

        assert client.delete("/api/profile").json()["deleted"] == 1
        assert client.get("/api/profile").json()["total"] == 0

    def test_clearing_the_profile_keeps_the_history(self, client, fake_model):
        """画像和问答记录是两份数据，清空一个不该动另一个。"""
        client.post("/api/ask", json={"question": "我总是犹豫很久才决定", "top_k": 1})
        client.post("/api/profile/extract")

        client.delete("/api/profile")

        assert client.get("/api/history").json()["total"] == 1


class TestFigure:
    """「最像你的一位历史人物」在 HTTP 上的样子。

    界面靠 ``needs_refresh`` 决定要不要在后台补一次评定——所以这个字段的
    取值是本组测试的重点：该评的时候必须为真，不该评的时候必须为假。
    """

    def test_nothing_chosen_on_a_fresh_install(self, client, figure_pool):
        figure = client.get("/api/profile").json()["figure"]
        assert figure["id"] == ""
        assert figure["name"] == ""
        assert figure["portrait"] == ""
        # 还没选出谁，但候选人数要先给出来——界面靠它区分"还没评"与"没人可评"
        assert figure["pool_size"] == 1
        # 还没有画像就不该去调模型——打开画像页会白跑一次请求
        assert figure["needs_refresh"] is False

    def test_an_empty_pool_is_never_evaluated(self, client, monkeypatch):
        """名录空着就别去调模型了：调了也只会得到 no_pool。"""
        monkeypatch.setattr(figures_service, "_pool", ())
        build_profile(client)

        figure = client.get("/api/profile").json()["figure"]
        assert figure["pool_size"] == 0
        assert figure["needs_refresh"] is False

    def test_a_filled_profile_asks_for_an_evaluation(self, client, fake_models, figure_pool):
        build_profile(client)

        figure = client.get("/api/profile").json()["figure"]
        assert figure["id"] == ""
        assert figure["needs_refresh"] is True

    def test_evaluating_stores_and_returns_it(self, client, fake_models, figure_pool):
        build_profile(client)

        body = client.post("/api/profile/figure").json()
        assert body["ok"] is True
        assert body["id"] == "taoyuanming"
        assert body["llm_used"] is True
        assert body["error"] == ""

        figure = client.get("/api/profile").json()["figure"]
        assert figure["name"] == "陶渊明"
        assert figure["era"] == "东晋"
        assert figure["blurb"]
        assert figure["reason"] == "你也不爱应酬"
        assert figure["credit"]
        assert figure["portrait"] == "/api/profile/figure/portrait/taoyuanming"
        assert figure["week"]
        assert figure["chosen_at"]
        assert figure["pool_size"] == 1
        # 理由两种语言都有：切到英文界面不该只剩中文
        assert client.get("/api/profile?lang=en").json()["figure"]["reason"] == "You shun company too"

    def test_a_fresh_evaluation_is_not_repeated_within_the_week(self, client, fake_models, figure_pool):
        """一周之内答案不变——这正是"每周更新"的含义。"""
        build_profile(client)
        client.post("/api/profile/figure")

        assert client.get("/api/profile").json()["figure"]["needs_refresh"] is False

    def test_english_gets_english_names_and_reasons(self, client, fake_models, figure_pool):
        build_profile(client)
        client.post("/api/profile/figure", json={"lang": "en"})

        figure = client.get("/api/profile?lang=en").json()["figure"]
        assert figure["name"] == "Tao Yuanming"
        assert figure["reason"] == "You shun company too"

    def test_the_evaluation_is_asked_in_the_right_language(self, client, fake_models, figure_pool):
        build_profile(client)
        client.post("/api/profile/figure", json={"lang": "en"})

        system = fake_models.messages[-1][0]["content"]
        assert "historical figures" in system

    def test_changing_the_gender_switches_the_pool(self, client, fake_models, figure_pool):
        """男女开关是筛选池：换过去是另一份名录，也是另一个人。"""
        build_profile(client)
        assert client.post("/api/profile/figure").json()["id"] == "taoyuanming"

        client.put("/api/profile/avatar", json={"gender": "female"})
        figure = client.get("/api/profile").json()["figure"]
        assert figure["id"] == ""  # 女性这边还没评过
        assert figure["needs_refresh"] is True

        assert client.post("/api/profile/figure").json()["id"] == "liqingzhao"

    def test_the_other_genders_choice_is_not_lost(self, client, fake_models, figure_pool):
        """来回切开关不该把对面的人弄丢。"""
        build_profile(client)
        client.post("/api/profile/figure")

        client.put("/api/profile/avatar", json={"gender": "female"})
        client.put("/api/profile/avatar", json={"gender": "male"})

        assert client.get("/api/profile").json()["figure"]["name"] == "陶渊明"

    def test_without_a_model_it_says_why(self, client, figure_pool):
        """没有模型不是 500——人物本来就是附加功能。"""
        body = client.post("/api/profile/figure").json()
        assert body["ok"] is False
        assert body["llm_used"] is False
        assert body["error"] == "llm_disabled"

    def test_a_model_answer_outside_the_pool_is_refused(self, client, monkeypatch, figure_pool):
        """模型编了一个人：不能存，否则界面上会出现一个查不到的人。"""

        def responder(messages):
            if any(marker in messages[0]["content"] for marker in _IS_FIGURE_PROMPT):
                return '{"id": "苏东坡", "reason_zh": "…"}'
            return json.dumps(TRAITS, ensure_ascii=False)

        install_fake_transport(monkeypatch, responder)

        build_profile(client)
        body = client.post("/api/profile/figure").json()
        router_module.reset_router()

        assert body["ok"] is False
        assert body["error"] == "not_in_pool"
        assert client.get("/api/profile").json()["figure"]["id"] == ""

    def test_clearing_the_profile_also_drops_the_figure(self, client, fake_models, figure_pool):
        """人是从画像推出来的；画像都清空了，他还留着就成了没来由的判断。"""
        build_profile(client)
        client.post("/api/profile/figure")
        assert client.get("/api/profile").json()["figure"]["id"] == "taoyuanming"

        client.delete("/api/profile")

        figure = client.get("/api/profile").json()["figure"]
        assert figure["id"] == ""
        assert figure["needs_refresh"] is False


class TestPortrait:
    def test_serves_a_registered_portrait(self, client):
        """随包发出的画像要真的取得到，且是 webp——前端 <img> 直接用它。"""
        response = client.get("/api/profile/figure/portrait/taoyuanming")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"
        assert len(response.content) > 1024

    def test_unknown_id_is_a_404(self, client):
        assert client.get("/api/profile/figure/portrait/查无此人").status_code == 404

    def test_a_path_traversal_id_is_a_404(self, client):
        """路径由名录推出，调用者拼不出程序目录外的文件。"""
        assert client.get("/api/profile/figure/portrait/..%2F..%2F.env").status_code == 404
        assert client.get("/api/profile/figure/portrait/.env").status_code == 404

