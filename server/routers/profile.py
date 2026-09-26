"""用户画像 API 路由（界面上的「画像」）。

只做参数校验与响应建模，归纳逻辑与存取规则都在 ``services/profile.py``。

和其它路由一样，**"做不成"不等于"请求失败"**：还没有问答记录、模型不可用、
模型这次没看出什么，一律 200 + ``ok: false`` + 原因，界面照常渲染并把原因
说清楚。弹一个红色报错只会让用户以为功能坏了。

「库不可用」也走这条路：画像的响应里带着 ``available`` 与 ``error``，读不到就
明说读不到。这是全项目仅有的两处降级之一（另一处是回响），理由见
``routers/history.py`` 的模块说明。
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..deps import require_user
from ..errors import NOT_FOUND, UNAUTHORIZED, merge
from ..schemas.common import DeleteResponse
from ..schemas.profile import (
    AvatarRequest,
    AvatarResponse,
    ExtractRequest,
    ExtractResponse,
    FigureInfo,
    FigureResponse,
    ProfileResponse,
    TraitItem,
)
from ..services import figures as figures_service
from ..services.auth import User
from ..services.history import get_history_store
from ..services.profile import (
    DEFAULT_AVATAR,
    EXTRACT_SOURCE_LIMIT,
    TRAIT_CATEGORIES,
    extract,
    get_profile_store,
)

# 「画像」是从你自己的问答里归纳出来的，必须登录。理由与做法见 `deps.py`。
#
# 错误面比其他组窄：库故障在这里表现为 ``available: false``（不是 503），
# 而模型不可用表现为 ``ok: false``——两者都在响应体里，不占错误码。
router = APIRouter(
    prefix="/api/profile",
    tags=["profile"],
    dependencies=[Depends(require_user)],
    responses=merge(UNAUTHORIZED, NOT_FOUND),
)


def _to_item(trait) -> TraitItem:
    return TraitItem(
        id=trait.id,
        category=trait.category,
        content=trait.content,
        evidence=trait.evidence,
        confidence=trait.confidence,
    )


def _figure_info(store, lang: str, *, traits, user_id: int) -> FigureInfo:
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

    ``traits`` 由调用方递进来——``GET /api/profile`` 手上已经有一份，
    没必要为了这一处再向库里问一遍。
    """
    gender = store.avatar(user_id=user_id)
    stored = store.get_figure(gender, user_id=user_id)
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
async def get_profile(lang: str = "zh", user: User = Depends(require_user)):
    """读取**当前这个人**的画像：形象、全部特征、分类清单、还没归纳过的提问数、
    最像你的一位历史人物。
    """
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

    traits = store.list(user_id=user.id)
    return ProfileResponse(
        available=True,
        error="",
        avatar=store.avatar(user_id=user.id),
        total=store.count(user_id=user.id),
        traits=[_to_item(trait) for trait in traits],
        categories=list(TRAIT_CATEGORIES),
        # 只数个数，**不把最近 40 条回答的全文读出来**（见 HistoryStore.count_since）
        pending=get_history_store().count_since(
            store.last_extract_ts(user_id=user.id),
            user_id=user.id,
            window=EXTRACT_SOURCE_LIMIT,
        ),
        figure=_figure_info(store, lang, traits=traits, user_id=user.id),
    )


@router.post("/figure", response_model=FigureResponse)
def evaluate_figure(request: ExtractRequest | None = None, user: User = Depends(require_user)):
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
        store.list(user_id=user.id),
        gender=store.avatar(user_id=user.id),
        lang=lang,
        user_id=user.id,
    )
    return FigureResponse(
        ok=bool(result.figure_id),
        id=result.figure_id,
        llm_used=result.llm_used,
        error=result.error,
    )


@router.get(
    "/figure/portrait/{figure_id}",
    response_class=FileResponse,
    responses=merge(
        NOT_FOUND,
        {200: {"content": {"image/webp": {}}, "description": "这位候选人的画像（WebP）"}},
    ),
)
async def get_figure_portrait(figure_id: str):
    """取一位候选人的画像。

    **返回的是一张图，不是 JSON**——所以这个接口在文档里没有响应模型，
    只有 ``image/webp``。原先它在 OpenAPI 里是一片空白，看不出到底是没写完
    还是故意如此。

    路径只认名录里登记过的 id：不在这里自己拼文件名去查磁盘，
    免得 ``../`` 之类的 id 把程序目录外的文件读出去。
    """
    path = figures_service.portrait_path(figure_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "portrait_not_found", "message": f"没有这张画像: {figure_id}"},
        )
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.post("/extract", response_model=ExtractResponse)
def extract_profile(request: ExtractRequest | None = None, user: User = Depends(require_user)):
    """从**这个人自己**的问答记录里归纳画像特征。

    写成同步函数：内部要调用阻塞的模型请求（受 ``LLM_TOTAL_BUDGET`` 约束），
    声明成 ``async def`` 会把事件循环独占几十秒，别的接口跟着卡住。

    素材与归属必须配对：读的是 ``user_id`` 名下的记录，写进的是同一份画像。
    混着来会让 A 的提问变成 B 的画像。
    """
    lang = (request.lang if request is not None else "") or "zh"
    records = get_history_store().list(user_id=user.id, limit=EXTRACT_SOURCE_LIMIT)[1]
    result = extract(get_profile_store(), records, lang=lang, user_id=user.id)
    return ExtractResponse(
        ok=result.extracted > 0,
        extracted=result.extracted,
        total=result.total,
        llm_used=result.llm_used,
        error=result.error,
    )


@router.put("/avatar", response_model=AvatarResponse)
async def set_avatar(request: AvatarRequest, user: User = Depends(require_user)):
    """切换形象性别。存后端而不是浏览器本地：它属于画像这份数据。"""
    return AvatarResponse(avatar=get_profile_store().set_avatar(request.gender, user_id=user.id))


@router.delete("/traits/{trait_id}", response_model=DeleteResponse)
async def delete_trait(trait_id: int, user: User = Depends(require_user)):
    """删掉一条特征。用户不认同的判断就该能抹掉。**只删自己的**。"""
    if not get_profile_store().delete(trait_id, user_id=user.id):
        raise HTTPException(
            status_code=404,
            detail={"code": "trait_not_found", "message": f"特征不存在: id={trait_id}"},
        )
    return DeleteResponse(deleted=1)


@router.delete("", response_model=DeleteResponse)
async def clear_profile(user: User = Depends(require_user)):
    """清空**这个人**的画像（不删问答记录）。

    连带抹掉"最像你的一位历史人物"：那个人是从这份画像推出来的，画像没了，
    他还留在页面上就成了一个没有依据的判断。
    """
    store = get_profile_store()
    store.clear_figures(user_id=user.id)
    return DeleteResponse(deleted=store.clear(user_id=user.id))
