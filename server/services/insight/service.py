"""感悟业务层：选择、主题筛选与日期确定算法。

不依赖 FastAPI / HTTP / 检索器，只依赖 data 层，
保证可独立单元测试。
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .data import INSIGHTS, Insight, VALID_THEMES


@dataclass(frozen=True)
class InsightView:
    """对外暴露的感悟视图（含稳定ID）。"""
    id: int
    text: str
    interpretation: str
    source: str
    book_id: str
    themes: tuple[str, ...]


def _to_view(index: int, ins: Insight) -> InsightView:
    """内部模型转视图模型，隔离数据结构变化对外的影响。"""
    return InsightView(
        id=index,
        text=ins.text,
        interpretation=ins.interpretation,
        source=ins.source,
        book_id=ins.book_id,
        themes=ins.themes,
    )


class InsightService:
    """感悟服务：管理金句的选择与主题检索。

    状态只有惰性构建的主题索引，无外部 IO，线程安全（只读）。
    """

    def __init__(self, insights: tuple[Insight, ...] = INSIGHTS):
        self._insights = insights
        self._views: tuple[InsightView, ...] = tuple(
            _to_view(i, ins) for i, ins in enumerate(insights)
        )
        self._by_theme: dict[str, list[InsightView]] = {}
        for v in self._views:
            for t in v.themes:
                self._by_theme.setdefault(t, []).append(v)

    # ── 查询接口 ──────────────────────────────────────────

    def all(self) -> list[InsightView]:
        """全部感悟。"""
        return list(self._views)

    def count(self) -> int:
        """感悟总数。"""
        return len(self._views)

    def themes(self) -> list[str]:
        """可用主题列表（按数量降序）。"""
        return sorted(self._by_theme, key=lambda t: -len(self._by_theme[t]))

    def theme_counts(self) -> dict[str, int]:
        """每个主题的感悟数量。"""
        return {t: len(v) for t, v in self._by_theme.items()}

    def get(self, insight_id: int) -> Optional[InsightView]:
        """按ID获取单条感悟。"""
        if 0 <= insight_id < len(self._views):
            return self._views[insight_id]
        return None

    def by_theme(self, theme: str) -> list[InsightView]:
        """按主题获取感悟列表。"""
        return list(self._by_theme.get(theme, []))

    def by_book(self, book_id: str) -> list[InsightView]:
        """按书目获取感悟列表。"""
        return [v for v in self._views if v.book_id == book_id]

    # ── 特殊选择 ──────────────────────────────────────────

    def daily(self, day: Optional[date] = None) -> InsightView:
        """今日感悟：按日期确定性选择。

        同一天返回同一条（刷新不变），不同日期大概率轮换。
        用日期字符串哈希而非取模，避免日期数字的周期性偏置。
        """
        day = day or date.today()
        seed = int(hashlib.sha256(day.isoformat().encode()).hexdigest(), 16)
        return self._views[seed % len(self._views)]

    def random(self) -> InsightView:
        """随机感悟。"""
        return random.choice(self._views)

    def is_valid_theme(self, theme: str) -> bool:
        """校验主题是否有效。"""
        return theme in VALID_THEMES


# 全局单例（只读，线程安全）
_service: Optional[InsightService] = None


def get_insight_service() -> InsightService:
    """获取感悟服务单例。"""
    global _service
    if _service is None:
        _service = InsightService()
    return _service
