"""感悟模块：数据层 + 业务层。

对外只暴露 InsightService 与 Insight 视图模型，
数据结构与内部实现细节（data 模块）不外泄。
"""

from .data import Insight, VALID_THEMES, validate_insights
from .service import InsightService, InsightView, get_insight_service

__all__ = [
    "Insight",
    "InsightView",
    "InsightService",
    "VALID_THEMES",
    "get_insight_service",
    "validate_insights",
]
