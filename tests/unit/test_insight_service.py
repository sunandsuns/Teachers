"""insight 服务与数据层单元测试。"""

from datetime import date, timedelta

import pytest

from server.services.insight.data import INSIGHTS, VALID_THEMES, validate_insights
from server.services.insight.service import InsightService, get_insight_service


class TestDataIntegrity:
    def test_data_has_reasonable_size(self):
        assert len(INSIGHTS) >= 40

    def test_validate_returns_no_errors(self):
        errors = validate_insights()
        assert errors == []

    def test_all_themes_are_valid(self):
        for ins in INSIGHTS:
            assert ins.themes, f"{ins.text[:10]} 缺主题"
            assert set(ins.themes) <= VALID_THEMES


class TestInsightService:
    def test_daily_deterministic_same_day(self):
        svc = InsightService()
        d = date(2026, 9, 16)
        assert svc.daily(d).id == svc.daily(d).id

    def test_daily_rotates_across_days(self):
        svc = InsightService()
        ids = {svc.daily(date(2026, 9, i)).id for i in range(1, 29)}
        assert len(ids) > 1, "不同日期应轮换不同感悟"

    def test_daily_accepts_default_today(self):
        assert svc_daily() is not None

    def test_random_returns_item(self):
        svc = InsightService()
        item = svc.random()
        assert item.text

    def test_get_by_id_valid_and_invalid(self):
        svc = InsightService()
        assert svc.get(0) is not None
        assert svc.get(-1) is None
        assert svc.get(len(svc.all())) is None

    def test_by_theme_filters(self):
        svc = InsightService()
        items = svc.by_theme("逆境")
        assert items
        assert all("逆境" in v.themes for v in items)

    def test_by_theme_unknown_returns_empty(self):
        assert InsightService().by_theme("不存在的主题") == []

    def test_by_book(self):
        svc = InsightService()
        items = svc.by_book("01")
        assert items
        assert all(v.book_id == "01" for v in items)

    def test_themes_sorted_by_count(self):
        svc = InsightService()
        themes = svc.themes()
        counts = svc.theme_counts()
        assert counts[themes[0]] >= counts[themes[-1]]

    def test_theme_counts_match_by_theme(self):
        svc = InsightService()
        for theme, count in svc.theme_counts().items():
            assert len(svc.by_theme(theme)) == count

    def test_is_valid_theme(self):
        svc = InsightService()
        assert svc.is_valid_theme("修心")
        assert not svc.is_valid_theme("不存在")

    def test_singleton(self):
        assert get_insight_service() is get_insight_service()


def svc_daily():
    return InsightService().daily(date.today() + timedelta(days=1))
