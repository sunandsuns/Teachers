"""求教检索策略的测试：主题路由、对口权重、门槛。

钉的都是**性质**而不是具体数值——权重与词表会随语料调整，
今天写死"焦虑 → 修心"的某条结果，明天往词表里加一个词就整片红。
"""

from __future__ import annotations

import pytest

from server.services import advice
from server.services.advice import (
    BOOK_AFFINITY,
    MAX_SOURCE_RESULTS,
    THEME_BOOST,
    affinity,
    advice_weights,
    build_book_themes,
    cap_per_chapter,
    cap_source,
    route_themes,
    search_for_advice,
    trim_by_score,
)
from server.services.insight.data import VALID_THEMES
from server.services.retriever import KIND_NOTES, KIND_SOURCE, SearchResult


class _Result:
    """够用的检索结果替身：score / kind / 出处坐标。"""

    def __init__(
        self,
        score: float,
        kind: str = KIND_NOTES,
        book_id: str = "08",
        chapter_id: str = "01",
    ) -> None:
        self.score = score
        self.kind = kind
        self.book_id = book_id
        self.chapter_id = chapter_id


# ── 主题路由 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question,expected",
    [
        ("我最近很焦虑，总觉得自己不够好", "修心"),
        ("该不该辞职去创业", "进退"),
        ("工作中遇到小人怎么办", "处世"),
        ("明知道该努力却提不起劲", "立志"),
        ("坚持不下去了，想放弃", "恒心"),
        ("同事在背后算计我", "谋略"),
    ],
)
def test_route_themes_hits_expected_theme(question, expected):
    assert expected in route_themes(question)


def test_route_themes_returns_empty_when_nothing_matches():
    """认不出就返回空——不对任何书提权，好过把某本书硬推上去。"""
    assert route_themes("今天天气不错") == ()


@pytest.mark.parametrize("question", ["", "   ", None])
def test_route_themes_handles_empty(question):
    assert route_themes(question) == ()


def test_route_themes_is_deterministic():
    """同一句话每次都要得到同一组主题：检索结果会随它变，不稳就会看到抖动。"""
    question = "和父母意见不合，还想辞职，心里很焦虑"
    assert route_themes(question) == route_themes(question)


def test_route_themes_respects_limit():
    themes = route_themes("焦虑，要不要辞职，还总被人排挤", limit=2)
    assert len(themes) <= 2


def test_all_themes_are_valid():
    """词表的键必须是那八个主题之一，写错了就永远命中不了。"""
    assert set(advice.THEME_KEYWORDS) == set(VALID_THEMES)


# ── 对口权重 ────────────────────────────────────────────────────────────


def test_affinity_known_and_unknown():
    assert affinity("09") == BOOK_AFFINITY["09"]
    assert affinity("不存在的书") == advice.DEFAULT_AFFINITY


def test_advice_weights_boosts_hit_books():
    book_themes = {"09": frozenset({"处世"}), "05": frozenset()}
    weights = advice_weights(["09", "05"], book_themes, ("处世",))

    assert weights["09"] == pytest.approx(affinity("09") * THEME_BOOST)
    assert weights["05"] == pytest.approx(affinity("05"))


def test_advice_weights_no_theme_means_no_boost():
    book_themes = {"09": frozenset({"处世"})}
    weights = advice_weights(["09"], book_themes, ())
    assert weights["09"] == pytest.approx(affinity("09"))


# ── 门槛与原典限流 ──────────────────────────────────────────────────────


def test_trim_drops_the_far_behind_tail():
    results = [_Result(1.0), _Result(0.9), _Result(0.4), _Result(0.3)]
    kept = trim_by_score(results, ratio=0.6)
    assert [r.score for r in kept] == [1.0, 0.9]


def test_trim_keeps_a_floor_so_the_model_is_not_left_with_one():
    results = [_Result(1.0), _Result(0.1)]
    kept = trim_by_score(results, ratio=0.6, floor_count=2)
    assert len(kept) == 2


def test_trim_of_empty_is_empty():
    assert trim_by_score([]) == []


def test_cap_source_limits_source_only():
    results = [
        _Result(0.9, KIND_SOURCE),
        _Result(0.8, KIND_NOTES),
        _Result(0.7, KIND_SOURCE),
        _Result(0.6, KIND_SOURCE),
    ]
    kept = cap_source(results, limit=MAX_SOURCE_RESULTS)
    assert sum(1 for r in kept if r.kind == KIND_SOURCE) == MAX_SOURCE_RESULTS
    assert len(kept) == 3


def test_cap_per_chapter_spreads_the_slots():
    """同一章节被切成很多单元时会连中好几条，占满席位，
    模型手里的"几份材料"其实只有一份。"""
    results = [
        _Result(0.9, book_id="10", chapter_id="02"),
        _Result(0.8, book_id="10", chapter_id="02"),
        _Result(0.7, book_id="10", chapter_id="02"),
        _Result(0.6, book_id="09", chapter_id="01"),
    ]
    kept = cap_per_chapter(results, limit=2)
    assert sum(1 for r in kept if r.chapter_id == "02") == 2
    assert len(kept) == 3
    # 砍的是同一章里多出来的那些，顺序不变
    assert [r.score for r in kept] == [0.9, 0.8, 0.6]


def test_cap_per_chapter_counts_per_book_not_globally():
    """同一本书的不同章节讲的是不同的事，不该互相挤。"""
    results = [
        _Result(0.9, book_id="10", chapter_id="02"),
        _Result(0.8, book_id="10", chapter_id="03"),
        _Result(0.7, book_id="10", chapter_id="04"),
    ]
    assert len(cap_per_chapter(results, limit=1)) == 3


class _RecordingRetriever:
    """只记录查询的假检索器：追问到底把什么送进了检索，看这里就知道。

    ``book_ids`` 是 ``advice`` 算书权重时要读的接口——真检索器上是缓存着的
    一个属性（"我索引了哪些书"），这里按同样的口径给出来。
    """

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.documents = [{"book_id": "09"}]
        self.book_ids = frozenset({"09"})

    def search(self, query, top_k=5, book_weights=None):
        self.queries.append(query)
        return []


class _EmptyLoader:
    """没有主题表的加载器：主题锚那一路会空着，只留原问那一路可查。"""

    def get_books(self):
        return []


@pytest.fixture
def clean_theme_cache():
    """用完把主题锚缓存清掉。

    ``_EmptyLoader`` 会让 ``get_theme_rows`` 把"空主题表"写进**模块级**缓存，
    而那个缓存只在 session 级的 ``loader`` fixture 建立时重置一次。一旦被写成
    空，同一次 pytest 会话里后续所有测试的主题加权就全废了。

    症状很隐蔽：失败的是**另一个文件**里的用例（"召回里没有一本对口古籍"），
    而且单独跑那个文件又是绿的——只因为 loader fixture 恰好在污染之后才建立。
    加一个新测试文件改变了 fixture 的建立时机，就会把它翻出来。
    """
    advice.reset_advice()
    yield
    advice.reset_advice()


def test_follow_up_carries_the_previous_question_into_search(clean_theme_cache):
    """"那我具体该说什么"里没有主语也没有对象，单独检索几乎召不回东西，
    于是材料与正在聊的事无关，回答看着就是答非所问。"""
    retriever = _RecordingRetriever()
    search_for_advice(
        retriever, "那我具体该说什么？", context="朋友借钱不还", loader=_EmptyLoader()
    )
    assert retriever.queries
    assert "朋友借钱不还" in retriever.queries[0]


def test_first_question_is_not_diluted(clean_theme_cache):
    """没有上文时查询就是原句，不该凭空多出东西。"""
    retriever = _RecordingRetriever()
    search_for_advice(retriever, "朋友借钱不还怎么办", loader=_EmptyLoader())
    assert retriever.queries[0] == "朋友借钱不还怎么办"


# ── 书 → 主题 ───────────────────────────────────────────────────────────


class _FakeChapter:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeBook:
    def __init__(self, book_id: str, contents) -> None:
        self.book_id = book_id
        self.chapters = [_FakeChapter(c) for c in contents]


_THEME_TABLE = """## 五、八大主题归纳

| 主题 | 本书的判断 | 代表章句 |
| --- | --- | --- |
| 处世 | 与人为善 | "己所不欲，勿施于人" |
| 修心 | 反求诸己 | "吾日三省吾身" |
| 不存在的主题 | 会被丢掉 | —— |
"""


def test_build_book_themes_reads_the_table():
    books = [_FakeBook("09", [_THEME_TABLE])]
    themes = build_book_themes(books)
    assert themes["09"] == frozenset({"处世", "修心"})


def test_build_book_themes_skips_books_without_a_table():
    books = [_FakeBook("05", ["没有主题表的一段话"])]
    assert build_book_themes(books) == {}


# ── 编排 ────────────────────────────────────────────────────────────────


def test_search_for_advice_prefers_classics_over_mao(index):
    """问一句现代口语，回来的不该是《毛泽东选集》。

    这是整套策略存在的理由：毛选占索引 40%，平权检索时它是默认答案。
    """
    hits = search_for_advice(index, "我最近很焦虑，总觉得自己不够好")

    assert hits.results, "至少要给出一条，否则模型只能凭空发挥"
    assert hits.themes, "这句话应该认得出主题"
    assert "毛泽东选集" not in {r.book_title for r in hits.results}


def test_search_for_advice_caps_source_and_top_k(index):
    hits = search_for_advice(index, "工作中遇到小人怎么办？", top_k=5)
    assert len(hits.results) <= 5
    assert sum(1 for r in hits.results if r.kind == KIND_SOURCE) <= MAX_SOURCE_RESULTS


def test_search_for_advice_scores_descend(index):
    hits = search_for_advice(index, "和父母意见不合，该怎么相处")
    scores = [r.score for r in hits.results]
    assert scores == sorted(scores, reverse=True)


def test_search_results_carry_a_real_citation(index):
    """喂给模型的每条都要能标出处——提示词要求"引用原文并标出处"。"""
    for question in ("工作中遇到小人怎么办？", "被领导当众批评，心里很难受"):
        for result in search_for_advice(index, question).results:
            assert result.source, question
            assert result.content.strip(), question


def test_advice_does_not_poison_plain_search(index):
    """「寻章」仍然是全库平权：加权只在求教那条路上。"""
    plain = index.search("创业", top_k=5)
    assert plain, "寻章不该被求教的权重影响"
    assert isinstance(plain[0], SearchResult)
