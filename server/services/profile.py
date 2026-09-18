"""用户画像：从对话里归纳出"这个人是谁"。

为什么要有它
--------------------------------------------------------------------------
求教原本只看得见"这一句问题"，于是对谁都是同一套回答。画像把用户自己透露过
的信息（性格、年纪、在做的事、打算）攒起来，回答时一并交给模型，它才可能
按人说话。

只从用户说过的话里归纳
--------------------------------------------------------------------------
抽取提示词有两条硬要求：**只根据用户自己说过的内容判断**，以及**没线索就不写**。
宁可少几条，也不要让模型从"他问了职场问题"推出"他是上班族"——那是猜。画像
一旦开始编，用户就再也分不清哪条是真的、哪条是模型的自作多情。

归纳不出来不算故障
--------------------------------------------------------------------------
模型不可用时抽取直接返回失败原因，画像保持原样。它是锦上添花的东西，不该
因为上游抖动就往库里塞一批瞎编的特征。
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from .db import Database
from .llm import LLMTransportError, get_router, normalize_lang

#: 特征分类。界面上人形两侧的引线标签按它分组，所以是个封闭集合——
#: 模型给出别的分类会被丢掉，宁可少一条，也别让标签没地方挂。
TRAIT_CATEGORIES = ("性格", "年龄", "爱好", "生活条件", "成熟度", "专业", "规划")

#: 抽取时最多喂给模型多少条提问。再多也只是把同样的信息重复几遍。
EXTRACT_SOURCE_LIMIT = 40
#: 特征正文与依据的长度上限，防止模型写小作文
CONTENT_LIMIT = 120
EVIDENCE_LIMIT = 240

#: meta 表里存形象性别的键
META_AVATAR = "avatar_gender"
#: meta 表里存"上次归纳到哪一刻"的键
META_LAST_EXTRACT = "last_extract_ts"
#: meta 表里存"最像你的一位历史人物"的键前缀。**男女各存一份**（图鉴不同池子，
#: 来回切开关不该把对面的人弄丢），所以键长这样：``figure:male`` / ``figure:female``。
META_FIGURE_PREFIX = "figure"
#: 形象可选性别
AVATARS = ("male", "female")
DEFAULT_AVATAR = "male"

PROFILE_SYSTEM_PROMPT = """你是一位善于倾听的分析者。下面是一位用户与"人生导师"应用的问答记录。
请从中归纳出关于**这位用户本人**的画像特征。

硬性要求：
- 只根据记录里**用户自己说过的内容**判断。他问的话题不等于他的情况——问职场问题不代表他在上班。
- 某一方面没有任何线索时，不要写，也不要猜。宁缺毋滥。
- 每一条都要能指出依据（用户说过的话或大意）；找不到依据的不写。
- 分类只能是这几个之一：性格、年龄、爱好、生活条件、成熟度、专业、规划。
- 只输出 JSON 数组，不要任何解释文字。每项形如：
  {"category": "性格", "content": "做事偏谨慎，习惯先想清楚再动手", "evidence": "我说我总是犹豫很久才做决定", "confidence": 0.7}
- confidence 是你对这条判断的把握程度，0 到 1 之间的小数。
"""

#: 英文界面用的同一套要求。**分类仍然写中文**——那是后端与界面约定的封闭集合，
#: 界面负责把它译成英文标签；让模型翻一遍，自由发挥出来的词就没地方挂了。
PROFILE_SYSTEM_PROMPT_EN = """You are a perceptive reader. Below are questions a user asked the
"人生导师" (Life Mentor) app. Summarise what they reveal about **the user themselves**.

Hard rules:
- Judge only from what the user said. The topic they asked about is not their situation —
  asking about a workplace problem does not mean they are employed.
- If there is no clue on some aspect, omit it. Never guess. Fewer, solid items beat many.
- Every item must point to its evidence (the user's own words or their gist). No evidence, no item.
- category must be exactly one of these Chinese labels: 性格、年龄、爱好、生活条件、成熟度、专业、规划.
- Write "content" and "evidence" in English.
- Output the JSON array only, with no commentary. Each item looks like:
  {"category": "性格", "content": "Careful by temperament; likes to think before acting", "evidence": "I said I always hesitate for ages before deciding", "confidence": 0.7}
- confidence is how sure you are of that item, a decimal between 0 and 1.
"""

#: 按语言取抽取提示词
PROFILE_PROMPTS = {"zh": PROFILE_SYSTEM_PROMPT, "en": PROFILE_SYSTEM_PROMPT_EN}

#: 用户消息的头尾两句话，按语言取
_PROMPT_WRAPPER = {
    "zh": ("以下是这位用户问过的问题：", "请归纳关于他本人的画像特征。"),
    "en": (
        "Here are the questions this user asked:",
        "Summarise what they reveal about the user.",
    ),
}

#: 模型常把 JSON 包在 ```json 围栏里
_FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


@dataclass(frozen=True)
class Trait:
    """一条画像特征。"""

    id: int
    category: str
    content: str
    #: 依据：用户说过的哪句话让模型这么判断
    evidence: str
    confidence: float
    created_ts: float
    updated_ts: float


def _row_to_trait(row: Any) -> Trait:
    return Trait(
        id=row["id"],
        category=row["category"],
        content=row["content"],
        evidence=row["evidence"],
        confidence=float(row["confidence"]),
        created_ts=float(row["created_ts"]),
        updated_ts=float(row["updated_ts"]),
    )


def _figure_key(gender: str) -> Optional[str]:
    """人物记录的 meta 键。性别认不出时返回 None（调用方据此跳过读写）。"""
    code = (gender or "").strip().lower() if isinstance(gender, str) else ""
    return f"{META_FIGURE_PREFIX}:{code}" if code in AVATARS else None


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, number))


def _candidate_json(raw: str) -> str:
    """从模型的回答里抠出最可能是 JSON 的那一段。"""
    fenced = _FENCED_JSON.search(raw)
    if fenced:
        return fenced.group(1).strip()
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw.strip()


def parse_traits(raw: str) -> list[dict[str, Any]]:
    """把模型输出解析成特征列表。**解析不出来就返回空表，不抛异常。**

    模型偶尔会在 JSON 前后加两句"好的，我看出以下几点"，也可能忘了引号，
    这些都是常态。为此让整次抽取失败不值得——没有特征入库，画像保持原样，
    用户再点一次就好。
    """
    try:
        data = json.loads(_candidate_json(raw))
    except (ValueError, TypeError):
        return []

    if isinstance(data, dict):
        # 有的模型会多包一层 {"traits": [...]}
        for key in ("traits", "items", "data", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return []
    if not isinstance(data, list):
        return []

    traits: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        content = str(item.get("content", "")).strip()
        # 分类不在封闭集合里就丢掉：引线没有落脚的地方
        if category not in TRAIT_CATEGORIES or not content:
            continue
        traits.append(
            {
                "category": category,
                "content": content[:CONTENT_LIMIT],
                "evidence": str(item.get("evidence", "")).strip()[:EVIDENCE_LIMIT],
                "confidence": _clamp_confidence(item.get("confidence")),
            }
        )
    return traits


def build_profile_prompt(
    records: Sequence[Any], *, limit: int = EXTRACT_SOURCE_LIMIT, lang: str = "zh"
) -> str:
    """把问答记录拼成抽取用的输入。

    只用**用户自己写的问句**：回答是模型说的，拿它当依据等于自己证明自己。
    """
    questions = [record.question.strip() for record in records if record.question.strip()]
    body = "\n".join(f"- {question}" for question in questions[-limit:])
    intro, outro = _PROMPT_WRAPPER[normalize_lang(lang)]
    return f"{intro}\n\n{body}\n\n{outro}"


class ProfileStore:
    """画像的读写。与历史记录同一套约定：**所有方法都不抛异常**。"""

    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db if db is not None else Database()

    # ── 状态 ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._db.available

    @property
    def error(self) -> str:
        return self._db.error

    @property
    def db_path(self) -> str:
        return str(self._db.path)

    # ── 写 ──────────────────────────────────────────────────────────────

    def upsert(self, traits: Sequence[dict[str, Any]], *, now: Optional[float] = None) -> int:
        """写入一批特征，返回本次新增或更新的条数。

        同一个分类下正文完全相同的不重复插入，只更新把握与时间——反复抽取
        不该让画像越长越多份。
        """
        timestamp = time.time() if now is None else now
        if not traits:
            return 0
        try:
            written = 0
            with self._db.session() as connection:
                for trait in traits:
                    existing = connection.execute(
                        "SELECT id FROM traits WHERE category = ? AND content = ?",
                        (trait["category"], trait["content"]),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            "INSERT INTO traits "
                            "(category, content, evidence, confidence, created_ts, updated_ts) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                trait["category"],
                                trait["content"],
                                trait.get("evidence", ""),
                                float(trait.get("confidence", 0.5)),
                                timestamp,
                                timestamp,
                            ),
                        )
                    else:
                        connection.execute(
                            "UPDATE traits SET evidence = ?, confidence = ?, updated_ts = ? "
                            "WHERE id = ?",
                            (
                                trait.get("evidence", ""),
                                float(trait.get("confidence", 0.5)),
                                timestamp,
                                existing["id"],
                            ),
                        )
                    written += 1
                return written
        except Exception:  # noqa: BLE001 — 库坏了就当这次没记上
            return 0

    def delete(self, trait_id: int) -> bool:
        try:
            with self._db.session() as connection:
                cursor = connection.execute("DELETE FROM traits WHERE id = ?", (trait_id,))
                return cursor.rowcount > 0
        except Exception:  # noqa: BLE001
            return False

    def clear(self) -> int:
        """清空画像。返回删掉的条数。"""
        try:
            with self._db.session() as connection:
                return connection.execute("DELETE FROM traits").rowcount
        except Exception:  # noqa: BLE001
            return 0

    def set_avatar(self, gender: str) -> str:
        """存形象性别。认不出的值一律按默认，返回实际生效的那个。"""
        chosen = gender.strip().lower() if isinstance(gender, str) else ""
        if chosen not in AVATARS:
            chosen = DEFAULT_AVATAR
        self._write_meta(META_AVATAR, chosen)
        return chosen

    def mark_extracted(self, *, now: Optional[float] = None) -> None:
        """记下"已经归纳过截至此刻的提问"。

        界面靠它判断"下次打开时还要不要再归纳一遍"。写不进去也无所谓——
        最多是把同一批提问再送模型看一次。
        """
        self._write_meta(META_LAST_EXTRACT, repr(time.time() if now is None else now))

    def set_figure(self, gender: str, payload: Mapping[str, Any]) -> None:
        """存下"这个性别最像你的一位历史人物"。

        存成一段 JSON：里面是人物的 id、模型写的理由、评定时的周、以及当时
        画像的指纹。**分开存是刻意的**——指纹留着，下次跨周时才能判断"画像
        到底变没变"，而不是每次都要重算一遍再赌模型给出同一个答案。

        认不出的性别直接不写：与其塞进一个谁也读不到的键，不如什么都不做。
        """
        key = _figure_key(gender)
        if key is None:
            return
        try:
            blob = json.dumps(dict(payload), ensure_ascii=False)
        except (TypeError, ValueError):
            return
        self._write_meta(key, blob)

    def get_figure(self, gender: str) -> dict[str, Any]:
        """读回该性别的人物记录；没有、或记录坏了都返回空字典。"""
        key = _figure_key(gender)
        if key is None:
            return {}
        raw = self._read_meta(key)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def clear_figures(self) -> None:
        """抹掉两个性别各自选中的人物。

        与 :meth:`clear` 配套：画像都清空了，"最像你的是谁"就失去了依据。
        留着它只会显示一个不再有来由的判断——用户删掉全部特征，就是想说
        "这些都不对"，此时还坚持指认一个人是与他作对。
        """
        keys = [k for k in (_figure_key(g) for g in AVATARS) if k]
        try:
            with self._db.session() as connection:
                connection.executemany(
                    "DELETE FROM meta WHERE key = ?", [(key,) for key in keys]
                )
        except Exception:  # noqa: BLE001
            pass

    def _write_meta(self, key: str, value: str) -> None:
        """meta 表的 upsert。库不可用时静默跳过（这类数据丢了不影响主流程）。"""
        try:
            with self._db.session() as connection:
                connection.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
        except Exception:  # noqa: BLE001
            pass

    def _read_meta(self, key: str) -> Optional[str]:
        try:
            with self._db.session() as connection:
                row = connection.execute(
                    "SELECT value FROM meta WHERE key = ?", (key,)
                ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        return None if row is None else str(row["value"])

    # ── 读 ──────────────────────────────────────────────────────────────

    def list(self) -> list[Trait]:
        """按分类顺序返回，同类别内把握高的在前（界面上的引线顺序）。"""
        try:
            with self._db.session() as connection:
                rows = connection.execute(
                    "SELECT * FROM traits ORDER BY confidence DESC, id ASC"
                ).fetchall()
                return [_row_to_trait(row) for row in rows]
        except Exception:  # noqa: BLE001
            return []

    def count(self) -> int:
        try:
            with self._db.session() as connection:
                return int(connection.execute("SELECT COUNT(*) AS n FROM traits").fetchone()["n"])
        except Exception:  # noqa: BLE001
            return 0

    def avatar(self) -> str:
        value = (self._read_meta(META_AVATAR) or "").strip().lower()
        return value if value in AVATARS else DEFAULT_AVATAR

    def last_extract_ts(self) -> float:
        """上次归纳的时刻；从没归纳过为 0。"""
        raw = self._read_meta(META_LAST_EXTRACT)
        try:
            return float(raw) if raw else 0.0
        except (TypeError, ValueError):
            return 0.0

    def status(self) -> dict[str, Any]:
        """给界面看的概况。"""
        return {
            "available": self._db.available,
            "error": self._db.error,
            "db_path": self.db_path,
            "total": self.count() if self._db.available else 0,
            "avatar": self.avatar() if self._db.available else DEFAULT_AVATAR,
            "last_extract_ts": self.last_extract_ts() if self._db.available else 0.0,
        }


@dataclass(frozen=True)
class ExtractionResult:
    """一次归纳的结果。"""

    #: 本次写入（新增或更新）了几条
    extracted: int
    #: 画像里现在共有几条
    total: int
    #: 是否真的走了模型
    llm_used: bool
    #: 没归纳出东西时的原因，直接给人看
    error: str = ""


def extract(
    profile: ProfileStore,
    records: Sequence[Any],
    *,
    router=None,
    lang: str = "zh",
) -> ExtractionResult:
    """从问答记录里归纳出画像特征并入库。

    ``records`` 由调用方给（通常是历史记录里最近的一批），这样本函数不必知道
    历史存在哪，测试里塞几条假的就能跑。
    """
    # 先看模型：它没有的话，攒再多记录也归纳不出东西，先报这个更贴近"你该做什么"
    target = router if router is not None else get_router()
    if not target.config.enabled:
        return ExtractionResult(0, profile.count(), False, error="llm_disabled")

    if not records:
        return ExtractionResult(0, profile.count(), False, error="no_records")

    answer_lang = normalize_lang(lang)
    messages = [
        {"role": "system", "content": PROFILE_PROMPTS[answer_lang]},
        {"role": "user", "content": build_profile_prompt(records, lang=answer_lang)},
    ]
    try:
        content, _model = target.chat(messages)
    except LLMTransportError as exc:
        return ExtractionResult(0, profile.count(), False, error=str(exc))

    traits = parse_traits(content)
    if not traits:
        # 模型答了，但里面没有可用的特征。不算错误，只是这次没收获。
        #
        # 这里**不能**推进"已归纳到此刻"：那等于把这批提问永久消费掉了。
        # 模型把思维链当答案吐回来、或把 JSON 裹在散文里，都是常态；
        # 一旦因为这种一次性的答歪就推进时刻，下次换了模型也再没机会重看这批
        # 提问——画像会卡死在"没有新内容可归纳"上，再也长不出东西。
        # 宁可下次再送一遍，也不能把素材悄悄丢掉。
        return ExtractionResult(0, profile.count(), True, error="nothing_usable")

    written = profile.upsert(traits)
    # 确实落库了才算"这批提问已经被消化"，这时才记时刻，
    # 免得下次打开画像页又把同一批送一遍
    profile.mark_extracted()
    return ExtractionResult(written, profile.count(), True)


#: 进程级单例
_store: Optional[ProfileStore] = None
_lock = threading.Lock()


def get_profile_store() -> ProfileStore:
    global _store
    with _lock:
        if _store is None:
            _store = ProfileStore()
        return _store


def reset_profile_store() -> None:
    """丢掉单例。测试用它隔离数据目录。"""
    global _store
    with _lock:
        _store = None
