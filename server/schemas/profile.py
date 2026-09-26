"""profile 接口的出入参。

从 ``routers/profile.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

class TraitItem(BaseModel):
    """一条画像特征。"""

    id: int
    category: str = Field(..., description="分类：性格 / 年龄 / 爱好 / 生活条件 / 成熟度 / 专业 / 规划。后端是封闭集合，界面把它译成标签，不要当成自由文本处理")
    content: str
    evidence: str = Field("", description="依据：用户说过的哪句话")
    confidence: float = Field(..., description="模型的把握程度，0~1")

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

    model_config = ConfigDict(title="ExtractResult")

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

    model_config = ConfigDict(title="FigureResult")

    ok: bool
    id: str = ""
    llm_used: bool
    error: str

class AvatarRequest(BaseModel):
    """切换形象。"""

    gender: str = Field("", description="male / female；认不出的值按默认")

class AvatarResponse(BaseModel):
    avatar: str

