"""用户画像 API 路由（界面上的「画像」）。

只做参数校验与响应建模，归纳逻辑与存取规则都在 ``services/profile.py``。

和其它路由一样，**"做不成"不等于"请求失败"**：还没有问答记录、模型不可用、
模型这次没看出什么，一律 200 + ``ok: false`` + 原因，界面照常渲染并把原因
说清楚。弹一个红色报错只会让用户以为功能坏了。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.history import get_history_store
from ..services.profile import (
    DEFAULT_AVATAR,
    EXTRACT_SOURCE_LIMIT,
    TRAIT_CATEGORIES,
    extract,
    get_profile_store,
    pending_count,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class TraitItem(BaseModel):
    """一条画像特征。"""

    id: int
    category: str
    content: str
    evidence: str = Field("", description="依据：用户说过的哪句话")
    confidence: float


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


@router.get("", response_model=ProfileResponse)
async def get_profile():
    """读取画像：形象、全部特征、分类清单、以及还没归纳过的提问数。"""
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
        )

    _, records = get_history_store().list(limit=EXTRACT_SOURCE_LIMIT)
    return ProfileResponse(
        available=True,
        error="",
        avatar=store.avatar(),
        total=store.count(),
        traits=[_to_item(trait) for trait in store.list()],
        categories=list(TRAIT_CATEGORIES),
        pending=pending_count(records, store.last_extract_ts()),
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
    """清空画像（不删问答记录）。"""
    return DeleteResponse(deleted=get_profile_store().clear())
