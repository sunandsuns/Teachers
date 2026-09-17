"""感悟 API 路由：薄 HTTP 层，仅做参数校验与格式转换。

所有业务逻辑在 InsightService 中，路由不包含任何业务规则，
保证 HTTP 层可随时替换（如换成 CLI / gRPC）而不影响核心逻辑。
"""

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.insight import get_insight_service

router = APIRouter(prefix="/api/insight", tags=["insight"])


class InsightItem(BaseModel):
    """单条感悟的响应模型。"""
    id: int
    text: str
    interpretation: str
    source: str
    book_id: str
    themes: list[str]


class InsightListResponse(BaseModel):
    """感悟列表响应。"""
    total: int
    items: list[InsightItem]


class ThemeListResponse(BaseModel):
    """主题列表响应。"""
    themes: list[str]
    counts: dict[str, int]


def _to_item(view) -> InsightItem:
    """视图模型转响应模型（隔离内部结构）。"""
    return InsightItem(
        id=view.id,
        text=view.text,
        interpretation=view.interpretation,
        source=view.source,
        book_id=view.book_id,
        themes=list(view.themes),
    )


@router.get("/daily", response_model=InsightItem)
async def daily_insight(day: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天")):
    """今日感悟：按日期确定性选择，同一天返回同一条。"""
    service = get_insight_service()
    target: date_type
    if day:
        try:
            target = date_type.fromisoformat(day)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效日期格式: {day}，应为 YYYY-MM-DD")
    else:
        target = date_type.today()
    return _to_item(service.daily(target))


@router.get("/random", response_model=InsightItem)
async def random_insight():
    """随机感悟。"""
    service = get_insight_service()
    return _to_item(service.random())


@router.get("/themes", response_model=ThemeListResponse)
async def list_themes():
    """主题列表及每个主题的感悟数量。"""
    service = get_insight_service()
    return ThemeListResponse(
        themes=service.themes(),
        counts=service.theme_counts(),
    )


@router.get("/by-theme/{theme}", response_model=InsightListResponse)
async def by_theme(theme: str):
    """按主题获取感悟列表。"""
    service = get_insight_service()
    if not service.is_valid_theme(theme):
        raise HTTPException(status_code=404, detail=f"未知主题: {theme}")
    items = service.by_theme(theme)
    return InsightListResponse(total=len(items), items=[_to_item(v) for v in items])


@router.get("/by-book/{book_id}", response_model=InsightListResponse)
async def by_book(book_id: str):
    """按书目获取感悟列表。"""
    service = get_insight_service()
    items = service.by_book(book_id)
    return InsightListResponse(total=len(items), items=[_to_item(v) for v in items])


@router.get("/{insight_id}", response_model=InsightItem)
async def get_insight(insight_id: int):
    """按ID获取单条感悟。"""
    service = get_insight_service()
    view = service.get(insight_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"感悟不存在: id={insight_id}")
    return _to_item(view)
