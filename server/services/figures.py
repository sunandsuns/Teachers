"""历史人物候选池：从语料目录读一份名录，再让模型挑出"最像你"的那一位。

这个功能在做什么
--------------------------------------------------------------------------
「画像」页从用户问过的话里归纳出他是谁；这一层再往前一步——**把这个人放进
历史里，指出他像哪位前人**。画像是抽象的判断，人物是一个具体的人。具体的
东西更容易记住，也更容易让人反驳（"我不像他"），而反驳正是自我认识的开始。

三条设计原则
--------------------------------------------------------------------------
1. **名录是数据，不是代码**：`figures/figures.json` 里一个人一条记录，画像放
   `figures/portraits/`。加人不需要改任何一行 Python，用户自己也能加。
2. **只按性情比，不按身份比**：提示词里写死这一条。用户的职业、处境、年代都
   不该影响判断——他是程序员不代表他像某个当过官的人。要让"像"落在为人处世
   的方式上，否则这个功能就退化成星座配对。
3. **每周重新评定，但不必每周换人**：一周过去了就拿最新的画像重看一遍。如果
   这一周画像没变，答案自然还是同一个人——"最像你"本来就该是稳定的。所以
   跨周之后先比画像指纹，指纹没变就沿用，不去打扰模型（也省一次调用）。

拉不到模型不算故障
--------------------------------------------------------------------------
和画像归纳一样：模型不可用时返回失败原因，原本选中的人保持不变。宁可停在
旧的判断上，也不要因为上游抖动而随机换一个人。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ..paths import FIGURES_DIRNAME, PROJECT_ROOT
from .llm import LLMTransportError, extract_json_block, get_router, normalize_lang

#: 名录文件名与画像子目录名
FIGURES_FILENAME = "figures.json"
PORTRAIT_DIRNAME = "portraits"

#: 允许的性别（与画像里的 AVATARS 同义；这里不 import 那个模块，避免循环依赖）
GENDERS = ("male", "female")

#: 每个候选人的双语字段。缺任何一个就丢掉这条记录——宁可名录里少一个人，
#: 也不要在界面上显示半条（英文界面冒出中文名，或署名是空的）。
_TEXT_FIELDS = ("name", "era", "blurb", "traits", "credit")

#: 喂给模型的最多特征条数。再多只是把同样的信息说几遍，且会推高延迟。
TRAIT_LIMIT = 24
#: 模型写的"像在哪里"的长度上限
REASON_LIMIT = 300

FIGURES_SYSTEM_PROMPT = """你是一位熟悉中外史书的人。下面给你一位用户的画像，以及一份历史人物名录。
请判断他最像名录里的哪一位。

硬性要求：
- 只能从名录里挑一个，输出它的 id。名录以外的名字一律不算。
- 比的是**为人处世的方式**——性情、在意什么、怎么做事、怎么过日子。
  不要比身份、职业、性别或处境：他是做什么的，与像谁无关。
- 画像里的线索少也要给出答案，选性情最接近的那一位；不要拒绝作答。
- 不要因为某个人更有名就选他。名气不是相似度。
- reason_zh 与 reason_en 各写两三句：**指明画像里的哪几点**让你选了他。
  要具体，不要写"气质相近"这种空话；也不要复述这个人的生平。
- 只输出 JSON，不要任何解释文字。形如：
  {"id": "taoyuanming", "reason_zh": "……", "reason_en": "……"}
"""

FIGURES_SYSTEM_PROMPT_EN = """You know the histories of China and the world. Below are a user's
profile and a list of historical figures. Decide which figure he or she most resembles.

Hard rules:
- Pick exactly one from the list and output its id. Names outside the list do not count.
- Compare **ways of living and acting** — temperament, what they care about, how they work,
  how they spend their days. Do not compare status, occupation, gender or circumstance:
  what the user does for a living has nothing to do with who they resemble.
- Give an answer even on thin evidence; choose the closest temperament. Do not refuse.
- Do not pick someone because they are more famous. Fame is not resemblance.
- Write reason_zh and reason_en, two or three sentences each, naming **which points in the
  profile** led to your choice. Be specific; no phrases like "a similar spirit", and do not
  retell the figure's biography.
- Output the JSON only, with no commentary:
  {"id": "taoyuanming", "reason_zh": "……", "reason_en": "……"}
"""

FIGURES_PROMPTS = {"zh": FIGURES_SYSTEM_PROMPT, "en": FIGURES_SYSTEM_PROMPT_EN}

#: 用户消息的头尾，按语言取
_PROMPT_WRAPPER = {
    "zh": ("这位用户的画像：", "请从名录里选出他最像的一位。"),
    "en": (
        "The user's profile:",
        "Choose the figure from the list that this user most resembles.",
    ),
}

#: 名录的引子
_POOL_HEADER = {"zh": "历史人物名录（只能从中选一个）：", "en": "The list (choose one only):"}


# ── 候选池 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Figure:
    """一位候选历史人物。

    ``text`` 直接就是 JSON 里那几对双语字段（``name_zh`` / ``name_en`` …），
    取用时一律走 :meth:`get`——它会自动回落到中文，这样英文界面在译文暂缺时
    最多显示中文，而不是一片空白。
    """

    id: str
    gender: str
    portrait: str
    text: Mapping[str, str]

    def get(self, field: str, lang: str = "zh") -> str:
        code = normalize_lang(lang)
        return (
            self.text.get(f"{field}_{code}")
            or self.text.get(f"{field}_zh")
            or ""
        )

    def name(self, lang: str = "zh") -> str:
        return self.get("name", lang)

    def era(self, lang: str = "zh") -> str:
        return self.get("era", lang)

    def blurb(self, lang: str = "zh") -> str:
        return self.get("blurb", lang)

    def traits(self, lang: str = "zh") -> str:
        return self.get("traits", lang)

    def credit(self, lang: str = "zh") -> str:
        return self.get("credit", lang)


def _parse_figure(raw: Any) -> Optional[Figure]:
    """把一条 JSON 记录转成 Figure；不合格返回 None（**不抛异常**）。"""
    if not isinstance(raw, dict):
        return None
    identifier = str(raw.get("id", "")).strip()
    gender = str(raw.get("gender", "")).strip().lower()
    portrait = str(raw.get("portrait", "")).strip()
    if not identifier or gender not in GENDERS or not portrait:
        return None
    # 画像名必须是**纯文件名**：名录是用户可编辑的数据，一条带 ../ 的记录
    # 就能让接口去读程序目录外的文件。在这里挡住，而不是等接口层再校验。
    if portrait != Path(portrait).name:
        return None
    text: dict[str, str] = {}
    for field in _TEXT_FIELDS:
        for lang in ("zh", "en"):
            value = raw.get(f"{field}_{lang}")
            if isinstance(value, str) and value.strip():
                text[f"{field}_{lang}"] = value.strip()
    # 中文是必需项：它是兜底语言，也是名录的编写语言
    if any(f"{field}_zh" not in text for field in _TEXT_FIELDS):
        return None
    return Figure(id=identifier, gender=gender, portrait=portrait, text=text)


def load_figures(root: Optional[Path] = None) -> tuple[Figure, ...]:
    """读取候选池。文件缺失、JSON 坏了、记录不合格，一律跳过。

    这是"可增补的语料"：用户手改出一个语法错误是常事，那种情况下整个功能
    消失（书架空了、求教不能用了）才是真正糟糕的结果。
    """
    path = (root or PROJECT_ROOT) / FIGURES_DIRNAME / FIGURES_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    records = data.get("figures") if isinstance(data, dict) else data
    if not isinstance(records, list):
        return ()
    figures: list[Figure] = []
    seen: set[str] = set()
    for raw in records:
        figure = _parse_figure(raw)
        if figure is None or figure.id in seen:
            continue
        seen.add(figure.id)
        figures.append(figure)
    return tuple(figures)


#: 进程级单例（名录在运行期不变，每次请求重读是白费磁盘）
_pool: Optional[tuple[Figure, ...]] = None
_pool_lock = threading.Lock()


def figure_pool() -> tuple[Figure, ...]:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = load_figures()
        return _pool


def reset_figure_pool() -> None:
    """丢掉缓存。测试与"用户刚改了名录"时用。"""
    global _pool
    with _pool_lock:
        _pool = None


def by_gender(gender: str, pool: Optional[Sequence[Figure]] = None) -> list[Figure]:
    """某一性别的候选人。认不出的性别返回空表——界面上的开关只有两个值，不猜。"""
    code = (gender or "").strip().lower()
    return [f for f in (pool if pool is not None else figure_pool()) if f.gender == code]


def find(figure_id: str, pool: Optional[Sequence[Figure]] = None) -> Optional[Figure]:
    for figure in pool if pool is not None else figure_pool():
        if figure.id == figure_id:
            return figure
    return None


def portrait_path(figure_id: str) -> Optional[Path]:
    """画像文件的绝对路径；不在名录里、或文件不在，返回 None。

    只认名录里登记的 id——这样接口拿到的路径一定是池内的文件名，
    不必再自己拼字符串去防目录穿越。
    """
    figure = find(figure_id)
    if figure is None:
        return None
    path = PROJECT_ROOT / FIGURES_DIRNAME / PORTRAIT_DIRNAME / figure.portrait
    return path if path.is_file() else None


# ── 画像指纹与周 ────────────────────────────────────────────────────────


def traits_signature(traits: Sequence[Any]) -> str:
    """画像的指纹：内容相同就是同一个指纹。

    **不看 id、不看时间、不看把握度**——换了条目的行内 id、重新归纳导致
    updated_ts 变化，都不该让人物跟着换。只有内容真的变了才算变。

    先排序再拼接：抽取回来的顺序（按把握度排）可能抖动，那不等于画像变了。
    """
    parts = sorted(
        f"{getattr(t, 'category', '')}:{getattr(t, 'content', '')}".strip()
        for t in traits
    )
    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def week_key(when: Optional[float] = None) -> str:
    """本地时间的 ISO 周，形如 ``2026-W38``。周一算一周的开始。"""
    moment = datetime.now() if when is None else datetime.fromtimestamp(when)
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def should_evaluate(
    stored: Optional[Mapping[str, Any]],
    traits: Sequence[Any],
    *,
    now: Optional[float] = None,
) -> bool:
    """现在要不要重新评定一次。

    - 从来没评过 → 要。
    - 还没跨周 → 不要（一周之内答案不变，这是"每周更新"的含义）。
    - 跨周了、但画像指纹没变 → 不要。答案本就该是同一个，重算只会浪费一次
      调用，还可能因为模型的不确定性把同一个人换成别人。
    - 跨周了、画像也变了 → 要。
    """
    if not stored or not stored.get("id"):
        return True
    if stored.get("week") == week_key(now):
        return False
    return stored.get("sig") != traits_signature(traits)


# ── 让模型挑人 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SelectionResult:
    """一次评定的结果。"""

    #: 选中的人（失败时是空串）
    figure_id: str
    #: 本次是否真的走了模型
    llm_used: bool
    #: 没选出来时的原因，可直接给人看
    error: str = ""


def build_figure_prompt(
    traits: Sequence[Any],
    pool: Sequence[Figure],
    *,
    lang: str = "zh",
    limit: int = TRAIT_LIMIT,
) -> str:
    """把画像与名录拼成评定用的输入。"""
    code = normalize_lang(lang)
    intro, outro = _PROMPT_WRAPPER[code]
    trait_lines = []
    for trait in list(traits)[:limit]:
        category = getattr(trait, "category", "") or ""
        content = (getattr(trait, "content", "") or "").strip()
        if content:
            trait_lines.append(f"- [{category}] {content}")
    body = "\n".join(trait_lines)
    people = "\n".join(
        f"- {figure.id}｜{figure.name(code)}｜{figure.era(code)}｜{figure.traits(code)}"
        for figure in pool
    )
    return f"{intro}\n\n{body}\n\n{_POOL_HEADER[code]}\n\n{people}\n\n{outro}"


def parse_selection(raw: str) -> dict[str, str]:
    """解析模型输出，返回 ``{"id", "reason_zh", "reason_en"}``。

    **解析不出来就返回空 id，不抛异常**：模型偶尔会先写两句"我认为……"，
    或者把 JSON 包在解释里。为此让整次评定失败不值得。
    """
    try:
        data = json.loads(extract_json_block(raw))
    except (ValueError, TypeError):
        return {"id": "", "reason_zh": "", "reason_en": ""}
    if not isinstance(data, dict):
        return {"id": "", "reason_zh": "", "reason_en": ""}
    return {
        "id": str(data.get("id", "")).strip(),
        "reason_zh": str(data.get("reason_zh", "")).strip()[:REASON_LIMIT],
        "reason_en": str(data.get("reason_en", "")).strip()[:REASON_LIMIT],
    }


def choose_figure(
    profile,
    traits: Sequence[Any],
    *,
    gender: str,
    lang: str = "zh",
    router=None,
    user_id: Optional[int] = None,
    now: Optional[float] = None,
) -> SelectionResult:
    """让模型从名录里挑出最像用户的那一位，并记进画像里。

    ``profile`` 是 :class:`~server.services.profile.ProfileStore`。传进来而不是
    在这里 get 单例，是为了让测试塞一个临时的库就能跑。

    ``user_id`` 决定这份"选出来的人"记在谁名下——它和 ``traits`` 必须来自同一个人，
    否则会把 A 的画像与 B 的选人混在一起。
    """
    pool = by_gender(gender)
    if not pool:
        return SelectionResult("", False, error="no_pool")

    # 先看模型：跟归纳那一步同一个道理——它没有的话，别的条件齐了也没用，
    # 而"去设置里配一个"才是用户真正能动手做的事。
    target = router if router is not None else get_router()
    if not target.config.enabled:
        return SelectionResult("", False, error="llm_disabled")

    if not traits:
        # 还没有画像可依，选谁都成了瞎猜
        return SelectionResult("", False, error="no_traits")

    code = normalize_lang(lang)
    messages = [
        {"role": "system", "content": FIGURES_PROMPTS[code]},
        {"role": "user", "content": build_figure_prompt(traits, pool, lang=code)},
    ]
    try:
        content, _model = target.chat(messages)
    except LLMTransportError as exc:
        return SelectionResult("", False, error=str(exc))

    picked = parse_selection(content)
    figure = find(picked["id"], pool)
    if figure is None:
        # 模型答了，但给的不是名录里的 id（编了一个人，或写了错别字）。
        # 不能就这么存下去——界面上会显示出"一个查不到的人"。
        return SelectionResult("", True, error="not_in_pool")

    profile.set_figure(
        gender,
        {
            "id": figure.id,
            "reason_zh": picked["reason_zh"],
            "reason_en": picked["reason_en"],
            "week": week_key(now),
            "sig": traits_signature(traits),
            "ts": float(now) if now is not None else time.time(),
        },
        user_id=user_id,
    )
    return SelectionResult(figure.id, True)


def describe(figure: Optional[Figure], stored: Mapping[str, Any], lang: str) -> dict[str, Any]:
    """把"选中的人 + 存下来的记录"整理成接口要的形状。

    存的是 id 与理由；名字、时代、署名每次都从名录现取——**改了名录就立刻生效**，
    不必等下一次评定。
    """
    code = normalize_lang(lang)
    if figure is None:
        return {
            "id": "",
            "name": "",
            "era": "",
            "blurb": "",
            "reason": "",
            "credit": "",
            "portrait": "",
            "week": "",
            "chosen_at": "",
            "pool_size": 0,
        }
    reason = (
        stored.get(f"reason_{code}")
        or stored.get("reason_zh")
        or ""
    )
    return {
        "id": figure.id,
        "name": figure.name(code),
        "era": figure.era(code),
        "blurb": figure.blurb(code),
        "reason": reason,
        "credit": figure.credit(code),
        "portrait": f"/api/profile/figure/portrait/{figure.id}",
        "week": str(stored.get("week", "")),
        "chosen_at": _iso_date(stored.get("ts")),
        "pool_size": len(by_gender(figure.gender)),
    }


def _iso_date(stamp: Any) -> str:
    """时间戳 → ``2026-09-17``；给不出来就空串（界面据此不显示这一行）。"""
    try:
        return datetime.fromtimestamp(float(stamp)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""
