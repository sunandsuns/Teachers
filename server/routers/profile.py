"""用户画像 API 路由（界面上的「画像」）。

只做参数校验与响应建模，归纳逻辑与存取规则都在 ``services/profile.py``。

和其它路由一样，**"做不成"不等于"请求失败"**：还没有问答记录、模型不可用、
模型这次没看出什么，一律 200 + ``ok: false`` + 原因，界面照常渲染并把原因
说清楚。弹一个红色报错只会让用户以为功能坏了。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services import figures as figures_service
from ..services.history import get_history_store
from ..services.profile import (
    DEFAULT_AVATAR,
    EXTRACT_SOURCE_LIMIT,
    TRAIT_CATEGORIES,
    extract,
    get_profile_store,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class TraitItem(BaseModel):
    """一条画像特征。"""

    id: int
    category: str
    content: str
    evidence: str = Field("", description="依据：用户说过的哪句话")
    confidence: float


class FigureInfo(BaseModel):
    """「最像你的一位历史人物」。

    整块都可能为空（还没选出 / 名录为空 / 库不可用）：那时 ``id`` 是空串，
    界面退回默认的两页册页。
    """

    id: str = ""
    name: str = ""
    era: str = ""
    blurb: str = Field("", description="一句话说他是谁")
    reason: str = Field("", description="模型写的：像在哪里")
    credit: str = Field("", description="题签式的出处")
    portrait: str = Field("", description="画像的相对 URL，可直接放进 <img src>")
    week: str = Field("", description="选出时的 ISO 周，如 2026-W38")
    chosen_at: str = Field("", description="选出的日期，YYYY-MM-DD")
    pool_size: int = Field(0, description="该性别下的候选人数")
    needs_refresh: bool = Field(
        False,
        description="是否该重新评定一次。跨周且画像有变化、或还没评过、或选中的人"
        "已不在名录里，都为真。界面据此在后台补一次评定。",
    )


class ProfileResponse(BaseModel):
    """画像全貌。"""

    available: bool
    error: str
    avatar: str = Field(..., description="形象性别：male / female")
    total: int
    traits: list[TraitItem]
    categories: list[str] = Field(..., description="全部分类，界面按它排引线")
    pending: int = Field(
        ...,
        description="上次归纳之后又问了多少条（最多 EXTRACT_SOURCE_LIMIT 条）。"
        "界面靠它决定要不要自动归纳一次。",
    )
    figure: FigureInfo = Field(
        default_factory=FigureInfo, description="最像你的一位历史人物"
    )


class ExtractResponse(BaseModel):
    """一次归纳的结果。``error`` 为机器可读的代号或上游错误文本。"""

    ok: bool
    extracted: int = Field(..., description="本次新增或更新的条数")
    total: int = Field(..., description="画像里现在共有几条")
    llm_used: bool
    error: str


class ExtractRequest(BaseModel):
    """归纳请求。`lang` 决定特征正文用哪种语言写；分类始终是中文封闭集合。"""

    lang: str = Field("zh", description="zh / en")


class FigureResponse(BaseModel):
    """一次历史人物评定的结果。``error`` 为机器可读的代号或上游错误文本。"""

    ok: bool
    id: str = ""
    llm_used: bool
    error: str


class AvatarRequest(BaseModel):
    """切换形象。"""

    gender: str = Field("", description="male / female；认不出的值按默认")


class AvatarResponse(BaseModel):
    avatar: str


class DeleteResponse(BaseModel):
    deleted: int


def _to_item(trait) -> TraitItem:
    return TraitItem(
        id=trait.id,
        category=trait.category,
        content=trait.content,
        evidence=trait.evidence,
        confidence=trait.confidence,
    )


def _figure_info(store, lang: str, *, traits=None) -> FigureInfo:
    """把"该性别当前选中的人"读成接口形状。

    这里做四件事：取出记录、从名录里还原出那个人、数一下候选人数、判断要不要重评。

    候选人数按**当前性别现算**，而不是等 ``describe`` 从选中的人身上带出来：
    界面在还没选出谁的时候也要靠它区分"还没评过"与"这一册名录里根本没人"。

    两种"该重评"的情形分开写：
    - 名录还在、指纹变了 → 交给 ``should_evaluate``（它懂"跨周才看指纹"的规则）；
    - 记录里有人、但名录里已经查不到（用户改了 figures.json）→ 直接重评。
      **不能漏这一条**：否则界面会一直显示默认册页，而 needs_refresh 是 False，
      等于卡死在一个永远不重算的状态。

    名录空着时一律不评：调了也只有 ``no_pool``，白白占掉一次模型调用。

    ``traits`` 可以由调用方递进来——``GET /api/profile`` 手上已经有一份，
    没必要为了这一处再向库里问一遍。
    """
    if traits is None:
        traits = store.list()
    gender = store.avatar()
    stored = store.get_figure(gender)
    figure = figures_service.find(stored.get("id")) if stored.get("id") else None
    info = figures_service.describe(figure, stored, lang)
    info["pool_size"] = len(figures_service.by_gender(gender))
    needs = (
        info["pool_size"] > 0
        and bool(traits)
        and (figure is None or figures_service.should_evaluate(stored, traits))
    )
    return FigureInfo(needs_refresh=needs, **info)


@router.get("", response_model=ProfileResponse)
async def get_profile(lang: str = "zh"):
    """读取画像：形象、全部特征、分类清单、还没归纳过的提问数、最像你的一位历史人物。"""
    store = get_profile_store()
    if not store.available:
        return ProfileResponse(
            available=False,
            error=store.error,
            avatar=DEFAULT_AVATAR,
            total=0,
            traits=[],
            categories=list(TRAIT_CATEGORIES),
            pending=0,
            figure=FigureInfo(),
        )

    traits = store.list()
    return ProfileResponse(
        available=True,
        error="",
        avatar=store.avatar(),
        total=store.count(),
        traits=[_to_item(trait) for trait in traits],
        categories=list(TRAIT_CATEGORIES),
        # 只数个数，**不把最近 40 条回答的全文读出来**（见 HistoryStore.count_since）
        pending=get_history_store().count_since(
            store.last_extract_ts(), window=EXTRACT_SOURCE_LIMIT
        ),
        figure=_figure_info(store, lang, traits=traits),
    )


@router.post("/figure", response_model=FigureResponse)
def evaluate_figure(request: ExtractRequest | None = None):
    """让模型从名录里挑出最像你的一位历史人物，并存下来。

    写成同步函数：内部要调用阻塞的模型请求（受 ``LLM_TOTAL_BUDGET`` 约束），
    声明成 ``async def`` 会把事件循环独占几十秒，别的接口跟着卡住。

    **不判断"该不该评"**：那是 GET 的活儿（它把结论放在 ``needs_refresh`` 里）。
    这里被调用就评——用户也可能就是想让它重看一遍。
    """
    lang = (request.lang if request is not None else "") or "zh"
    store = get_profile_store()
    if not store.available:
        return FigureResponse(ok=False, llm_used=False, error="history_unavailable")

    result = figures_service.choose_figure(
        store,
        store.list(),
        gender=store.avatar(),
        lang=lang,
    )
    return FigureResponse(
        ok=bool(result.figure_id),
        id=result.figure_id,
        llm_used=result.llm_used,
        error=result.error,
    )


@router.get("/figure/portrait/{figure_id}")
async def get_figure_portrait(figure_id: str):
    """取一位候选人的画像。

    路径只认名录里登记过的 id：不在这里自己拼文件名去查磁盘，
    免得 ``../`` 之类的 id 把程序目录外的文件读出去。
    """
    path = figures_service.portrait_path(figure_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"没有这张画像: {figure_id}")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.post("/extract", response_model=ExtractResponse)
def extract_profile(request: ExtractRequest | None = None):
    """从已有的问答记录里归纳画像特征。

    写成同步函数：内部要调用阻塞的模型请求（受 ``LLM_TOTAL_BUDGET`` 约束），
    声明成 ``async def`` 会把事件循环独占几十秒，别的接口跟着卡住。
    """
    lang = (request.lang if request is not None else "") or "zh"
    records = get_history_store().list(limit=EXTRACT_SOURCE_LIMIT)[1]
    result = extract(get_profile_store(), records, lang=lang)
    return ExtractResponse(
        ok=result.extracted > 0,
        extracted=result.extracted,
        total=result.total,
        llm_used=result.llm_used,
        error=result.error,
    )


@router.put("/avatar", response_model=AvatarResponse)
async def set_avatar(request: AvatarRequest):
    """切换形象性别。存后端而不是浏览器本地：它属于画像这份数据。"""
    return AvatarResponse(avatar=get_profile_store().set_avatar(request.gender))


@router.delete("/traits/{trait_id}", response_model=DeleteResponse)
async def delete_trait(trait_id: int):
    """删掉一条特征。用户不认同的判断就该能抹掉。"""
    if not get_profile_store().delete(trait_id):
        raise HTTPException(status_code=404, detail=f"特征不存在: id={trait_id}")
    return DeleteResponse(deleted=1)


@router.delete("", response_model=DeleteResponse)
async def clear_profile():
    """清空画像（不删问答记录）。

    连带抹掉"最像你的一位历史人物"：那个人是从这份画像推出来的，画像没了，
    他还留在页面上就成了一个没有依据的判断。
    """
    store = get_profile_store()
    store.clear_figures()
    return DeleteResponse(deleted=store.clear())
