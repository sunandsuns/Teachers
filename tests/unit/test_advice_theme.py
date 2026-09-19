"""主题锚的测试：检索回来的东西，主题得是提问的那个主题。

与 ``test_advice.py`` 一样，钉的是**性质**：语料会增补、权重会调，
只有"主题锚把古籍捞回来了""两路合并时两者都在的排前面"这类性质不会变。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from server.services.advice import (
    ANCHORS_PER_THEME,
    MAX_MODERN_RESULTS,
    MODERN_BOOKS,
    ThemeAnchor,
    anchor_text,
    build_theme_rows,
    cap_modern,
    get_theme_rows,
    merge_passes,
    search_for_advice,
    theme_anchors,
)
from server.services.insight.data import VALID_THEMES
from server.services.retriever import KIND_NOTES, KIND_SOURCE


def _anchor(book_id: str, theme: str, judgment: str = "判断", quote: str = "代表句"):
    return ThemeAnchor(
        book_id=book_id,
        book_title="《%s》" % book_id,
        theme=theme,
        judgment=judgment,
        quote=quote,
    )


@dataclass(frozen=True)
class _Hit:
    """够用的检索结果替身：必须是 dataclass——合并时要把分数写回。"""

    book_id: str
    chapter_id: str
    score: float
    kind: str = KIND_NOTES
    chapter_title: str = "章"
    offset: int = 0


# ── 主题锚的读取 ────────────────────────────────────────────────────────


class _FakeChapter:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeBook:
    def __init__(self, book_id: str, contents, title: str = "") -> None:
        self.book_id = book_id
        self.title = title or ("书" + book_id)
        self.chapters = [_FakeChapter(c) for c in contents]


_TABLE = """## 五、八大主题归纳

| 主题 | 本书的判断 | 代表章句 |
| --- | --- | --- |
| 处世 | 周而不比 | "君子和而不同" |
| 修心 | 内省克己 | "吾日三省吾身" |
| 不存在的主题 | 会被丢掉 | —— |
"""


def test_build_theme_rows_keeps_the_judgment_and_the_quote():
    """单元格里的判断句和代表句都要留住——它们是检索线索，也是可引的原文。"""
    rows = build_theme_rows([_FakeBook("09", [_TABLE])])

    assert set(rows["09"]) == {"处世", "修心"}
    assert rows["09"]["处世"].judgment == "周而不比"
    assert rows["09"]["处世"].quote == '"君子和而不同"'


def test_build_theme_rows_drops_unknown_themes_and_empty_books():
    rows = build_theme_rows([_FakeBook("09", [_TABLE]), _FakeBook("05", ["没有表"])])
    assert "不存在的主题" not in rows["09"]
    assert "05" not in rows


def test_build_theme_rows_first_wins_when_a_book_is_split():
    """同一本书被切成多个文件时表是重复的，取两次会让它在查询里占双倍分量。"""
    rows = build_theme_rows(
        [_FakeBook("04", [_TABLE]), _FakeBook("04", [_TABLE.replace("周而不比", "另一版")])]
    )
    assert rows["04"]["处世"].judgment == "周而不比"


def test_every_theme_in_the_corpus_is_valid():
    assert set(get_theme_rows()) , "语料里应当有主题表"
    for rows in get_theme_rows().values():
        assert set(rows) <= set(VALID_THEMES)


# ── 取锚 ────────────────────────────────────────────────────────────────


def test_theme_anchors_prefers_the_most_relevant_books():
    rows = {
        "13": {"处世": _anchor("13", "处世")},   # 史记，对口系数低
        "09": {"处世": _anchor("09", "处世")},   # 论语
        "10": {"处世": _anchor("10", "处世")},   # 菜根谭
        "15": {"处世": _anchor("15", "处世")},   # 贞观政要
    }
    picked = theme_anchors(rows, ("处世",), per_theme=2)

    assert [a.book_id for a in picked] == ["09", "10"]
    assert "13" not in [a.book_id for a in picked]


def test_theme_anchors_respects_per_theme_and_limit():
    rows = {str(i): {"处世": _anchor(str(i), "处世")} for i in range(1, 9)}
    assert len(theme_anchors(rows, ("处世",), per_theme=3)) == 3
    assert len(theme_anchors(rows, ("处世", "修心"), per_theme=ANCHORS_PER_THEME)) <= 6


def test_theme_anchors_empty_without_a_theme():
    """认不出主题就不该有锚——硬套一个主题等于替用户把问题改了。"""
    assert theme_anchors({"09": {"处世": _anchor("09", "处世")}}, ()) == []
    assert anchor_text([]) == ""


def test_anchor_text_joins_judgment_and_quote():
    text = anchor_text([_anchor("09", "处世", "周而不比", "君子和而不同")])
    assert "周而不比" in text
    assert "君子和而不同" in text


# ── 两路合并 ────────────────────────────────────────────────────────────


def test_merge_prefers_hits_present_in_both_passes():
    """又答这件事、又落在主题上的段落，排在只占一头的前面。"""
    both = _Hit("09", "a", 0.5)
    question_only = _Hit("09", "b", 0.4)
    theme_only = _Hit("10", "c", 0.3)

    merged = merge_passes([both, question_only], [both, theme_only])

    assert [h.chapter_id for h in merged] == ["a", "b", "c"]


def test_merge_keeps_theme_only_hits():
    """只在主题那路出现的段落要留下：它主题对得上，只是没撞上原问的字面。"""
    merged = merge_passes([_Hit("09", "a", 0.9)], [_Hit("10", "c", 0.9)])
    assert {h.chapter_id for h in merged} == {"a", "c"}


def test_merge_writes_the_merged_score_back():
    """排序按合并分，留着各路自己的原始分值会出现"排前面却分更低"。"""
    merged = merge_passes([_Hit("09", "a", 0.9)], [_Hit("10", "c", 0.9)])
    scores = [h.score for h in merged]
    assert scores == sorted(scores, reverse=True)


def test_merge_of_empty_sides():
    assert merge_passes([], []) == []
    only = merge_passes([_Hit("09", "a", 0.5)], [])
    assert [h.chapter_id for h in only] == ["a"]


# ── 现代书限流 ──────────────────────────────────────────────────────────


def test_cap_modern_keeps_a_seat_for_the_classics():
    modern = "04"
    results = [
        _Hit(modern, "a", 0.9),
        _Hit(modern, "b", 0.8),
        _Hit(modern, "c", 0.7),
        _Hit("09", "d", 0.6),
    ]
    kept = cap_modern(results, limit=MAX_MODERN_RESULTS)

    assert sum(1 for h in kept if h.book_id == modern) == MAX_MODERN_RESULTS
    assert "d" in [h.chapter_id for h in kept]


def test_cap_modern_does_not_touch_other_books():
    results = [_Hit("09", "a", 0.9), _Hit("10", "b", 0.8)]
    assert len(cap_modern(results)) == 2


def test_modern_books_are_defined():
    assert MODERN_BOOKS, "现代白话书名单不能为空，否则限流形同虚设"


# ── 端到端：主题对不对得上 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "我最近很焦虑",
        "工作中遇到小人怎么办",
        "总是讨好别人，很累",
    ],
)
def test_advice_returns_theme_matching_passages(index, question):
    """口语里问的事，回来的得是讲这件事的经典段落。

    这是主题锚存在的理由："焦虑""小人"这类词的字面在古籍里对不上，
    靠主题锚（《论语》"内省、克己"、《菜根谭》"待小人"）才能捞回来。
    """
    hits = search_for_advice(index, question, top_k=5)

    assert hits.themes, "这句话应当认得出主题"
    assert hits.results
    titles = {r.book_title for r in hits.results}
    assert titles & {"论语", "菜根谭", "道德经"}, (
        "%s 的召回里没有一本对口古籍：%s" % (question, sorted(titles))
    )


def test_advice_drops_index_and_intro_chapters(index):
    """「八大主题归纳」是索引、「导言」是阅读说明——它们答不上任何具体问题。"""
    for question in ("工作中遇到小人怎么办", "三十岁了一事无成"):
        for result in search_for_advice(index, question, top_k=5).results:
            assert "主题归纳" not in result.chapter_title, question
            assert "导言" not in result.chapter_title, question


def test_advice_source_hits_are_not_modern_prose(index):
    """现代白话书的原文不该占着原典的位置——那位置是留给古籍的。"""
    hits = search_for_advice(index, "朋友借钱不还怎么办", top_k=5)
    for result in hits.results:
        assert not (
            result.book_id in MODERN_BOOKS and result.kind == KIND_SOURCE
        ), result.source
