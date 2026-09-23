"""求教场景的检索策略：主题路由 + 语料对口加权 + 相关度门槛。

为什么单独一层
--------------------------------------------------------------------------
「寻章」要的是"全库里谁提到过这句话"，召回越全越好；
「求教」要的是"针对这个人生困惑，哪几段真能帮上忙"。

两者目标不同，共用一套检索就会互相拖累。实测：索引里《毛泽东选集》占
40.6%、《易经》原典占 26%，而最对口的《论语》《菜根谭》《道德经》
《王阳明心学》加起来只有 5%。于是问一句"我最近很焦虑"，回来的前五条里
有毛选的抗战文章和王阳明仓库的 README 元信息——模型拿不到对口材料，
要么硬凑不相关的古文，要么干脆架空自己发挥，用户看到的就是"生搬硬套"。

本模块只做**决策**：这问的是哪个主题、哪本书更对口、多低的分数该丢。
真正的检索仍由 ``retriever`` 执行。因此它不依赖 FastAPI，可以单独测试。

主题从哪来
--------------------------------------------------------------------------
八主题不是新编的，就是每篇深读笔记末尾「八大主题归纳」那张表里写的
（``insight.data.VALID_THEMES``）。

但直接用"这本书挂了哪些主题"来做路由是**没有用的**：实测八本有主题表的书，
每本都把八个主题全挂上了，于是任何问题都命中同一批书，加成等于没做。

真正有区分度的是表里的**单元格**——「主题 × 书」各有一行判断和一句代表原文，
例如《菜根谭》· 处世 ＝"不责小过、不发阴私、不念旧恶"＋"三者可以养德，亦可以
远害"。一句话问的是处世，那这几行就是语料里**主题最对得上**的文字。本模块
把它们称为**主题锚**：拿它单独跑一路检索，再与原问那一路合并，召回的东西才
真的落在提问的主题上，而不只是"出自一本对口的书"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Optional, Sequence

from .retriever import KIND_NOTES, KIND_SOURCE

#: 主题命中后的加成。
THEME_BOOST = 1.3
MIN_SCORE_RATIO = 0.6
#: 门槛砍完之后至少留几条。一条太少——模型只有一份材料时要么复述它，
#: 要么绕开它自己发挥；两条以上才谈得上"比较着讲"。
#: 反过来，留得太多又会把刚砍掉的噪声放回来，所以只保底到 2。
MIN_RESULTS = 2
#: 一次求教里原典最多占几条。原典片段缺少语境，占多了会挤掉笔记的深解。
MAX_SOURCE_RESULTS = 2
#: 同一章节最多占几条。
#: 笔记里"核心思想"这类大章被切成几十个检索单元，词面一旦对上就会连中
#: 好几条——实测问"领导抢我功劳"时五席里有三席出自《菜根谭》· 核心思想。
#: 那三席讲的其实是同一件事，模型拿到的材料看着有三份，实际只有一份，
#: 回答自然就绕着它打转，看起来像"翻来覆去就这一句"。宁可少两条，
#: 把位置让给别的书，让模型有得比较。
MAX_PER_CHAPTER = 2
#: 默认给几段。宁可少而准——提示词明确允许"没找到直接对应的就直说"。
DEFAULT_TOP_K = 5

#: 合并两路检索时的配比。
#: 原问那路保证"答的是这件事"（问"朋友借钱不还"就得谈借钱），
#: 主题锚那路保证"落在主题上"（不然回来的是词面偶然撞上的段落）。
#: 原问占大头——主题是路标，不是目的地。
QUESTION_MIX = 0.6
THEME_MIX = 0.4

#: 一个主题最多取几本书的判断句做锚。
#: 取多了各家说法互相稀释，检索就变成"八本书的平均数"，谁都不突出。
ANCHORS_PER_THEME = 3
ANCHOR_LIMIT = 6

#: 现代白话书。它们写得直白、词面与口语高度重合，检索里天然占优——
#: 实测问"总是讨好别人"时《人性的弱点》能占掉五席里的四席，可用户来「求教」
#: 是问经典的。限定席位，把剩下的位置让给古籍；它们仍然能被检索到。
MODERN_BOOKS: frozenset = frozenset({"04", "05"})
MAX_MODERN_RESULTS = 2

#: 求教时不参与检索的章节。
#: - 「八大主题归纳」是**索引**不是内容，已经拿去做检索线索了，再当答案
#:   喂回去等于让模型复述我们的提问。
#: - 「导言/导读/说明」讲的是这本书怎么读，不是这本书说了什么。它用词
#:   普通、篇幅适中，在词面检索里稳定冒头，却答不上任何具体问题。
_SKIP_CHAPTER_RE = re.compile(r"主题归纳|导言|导读|前言|序言|凡例|阅读提示|^说明")


# ── 主题词表 ────────────────────────────────────────────────────────────
#
# 一边是用户的口语，一边是古人写下的主题名。两者对不上，纯词面检索就召回
# 不到东西——"创业"在古籍里是"开创帝业"，"小人"是"君子小人"。
# 这张表把口语接回主题，检索才对得上。命中即算，不做权重：
# 多一个同义词只影响"命中了没有"，不影响排序（排序交给 TF-IDF）。

THEME_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "逆境": (
        "低谷", "挫折", "失败", "困难", "倒霉", "不顺", "打击", "绝望", "崩溃",
        "熬", "撑不住", "失业", "被裁", "生病", "破产", "分手", "离婚", "被骗",
        "走不出来", "一团糟", "雪上加霜", "屋漏", "撑过去", "挺过去", "最难",
    ),
    "进退": (
        "选择", "抉择", "辞职", "跳槽", "创业", "转行", "要不要", "该不该",
        "去留", "机会", "时机", "取舍", "放手", "继续还是", "换工作", "offer",
        "稳定", "冒险", "赌一把", "分叉", "十字路口", "下一步",
    ),
    "修心": (
        "焦虑", "烦躁", "内耗", "不安", "心乱", "想不开", "压力", "睡不着",
        "失眠", "恐慌", "emo", "抑郁", "难受", "平静", "静下来", "情绪",
        "胡思乱想", "想太多", "放不下", "执着", "释怀", "心累",
    ),
    "立志": (
        "迷茫", "没方向", "找不到方向", "目标", "意义", "一事无成", "废物",
        "躺平", "摆烂", "没动力", "提不起劲", "努力", "上进", "三十岁",
        "人生规划", "想成为", "理想", "抱负", "荒废", "虚度", "平庸",
    ),
    "处世": (
        "人际", "相处", "同事", "领导", "上司", "老板", "父母", "家人", "朋友",
        "借钱", "小人", "拒绝", "讨好", "得罪", "沟通", "吵架", "矛盾",
        "孤立", "排挤", "八卦", "背后", "面子", "人情", "社交", "不会说话",
        "不合群", "委屈",
    ),
    "谋略": (
        "竞争", "博弈", "算计", "策略", "大局", "布局", "对手", "职场斗争",
        "站队", "权力", "博弈", "筹码", "谈判", "争取", "防着", "被针对",
        "利益", "局势",
    ),
    "谦逊": (
        "骄傲", "炫耀", "得意", "飘了", "自负", "听不进", "批评", "膨胀",
        "自满", "看不起", "傲慢", "锋芒", "低调",
    ),
    "恒心": (
        "坚持", "放弃", "半途", "耐心", "积累", "拖延", "懒", "习惯", "自律",
        "三天打鱼", "坚持不下去", "慢慢来", "长期", "复利", "练",
    ),
}


#: 词表的固定顺序。命中数相同时按它排序，保证同一句话每次得到同一组主题。
_THEME_ORDER: tuple[str, ...] = tuple(THEME_KEYWORDS)


def route_themes(question: str, *, limit: int = 2) -> tuple[str, ...]:
    """判断一句话问的是哪几个主题；认不出就返回空元组。

    **认不出比认错好**：空元组意味着"不对任何书提权"，检索退回全库平权，
    而不是把《孙子兵法》硬推到一个感情问题上。所以这里既不做模糊匹配，
    也不给没命中的主题打同情分。
    """
    text = (question or "").strip()
    if not text:
        return ()

    scored: list[tuple[str, int]] = []
    for theme, keywords in THEME_KEYWORDS.items():
        hits = sum(1 for word in keywords if word in text)
        if hits:
            scored.append((theme, hits))

    # 命中数相同时按词表顺序，保证同一句话每次都得到同一组主题
    scored.sort(key=lambda pair: (-pair[1], _THEME_ORDER.index(pair[0])))
    return tuple(theme for theme, _ in scored[:limit])


# ── 语料对口程度 ────────────────────────────────────────────────────────
#
# 一整套语料里，各书对"人生困惑"的距离差得很远，但 TF-IDF 只看词频，
# 于是篇幅最大的那本天然占优（毛选 3597 个单元 vs 论语 147 个）。
# 这里按"这本书是不是在讲做人做事"给一个系数，把篇幅优势抵消掉。

BOOK_AFFINITY: Mapping[str, float] = {
    "09": 1.5,   # 论语——直接讲做人
    "10": 1.5,   # 菜根谭——处世格言
    "08": 1.5,   # 道德经
    "06": 1.5,   # 王阳明心学
    "04": 1.25,  # 人性的弱点——现代人际，对口但它是白话励志书，
    #              词面还与口语高度重合，权重给高了会独占整个召回
    #              （实测 1.4 时占 55%），压到比古籍略低，让古籍上浮
    "02": 1.2,   # 厚黑学——职场权谋，偏但有用
    "12": 1.1,   # 战国策
    "07": 1.0,   # 孙子兵法
    "11": 1.0,   # 鬼谷子
    "01": 1.0,   # 易经（笔记部分）
    "15": 0.9,   # 贞观政要
    "13": 0.7,   # 史记——叙事，少判断
    "14": 0.7,   # 资治通鉴
    "03": 0.5,   # 奇门遁甲——术数，不对口
    "05": 0.35,  # 毛泽东选集——现代政论，与人生困惑基本无关
}

DEFAULT_AFFINITY = 1.0


def affinity(book_id: str) -> float:
    """一本书在求教场景下的对口系数。

    原典的折减不在这一层——那是**建索引时**就定好的（``retriever.SOURCE_BOOK_WEIGHT``），
    对「寻章」同样生效。这里只管"这次提问该不该更偏向某本书"。
    """
    return BOOK_AFFINITY.get(book_id, DEFAULT_AFFINITY)


# ── 书 → 主题 ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ThemeAnchor:
    """一本书对某个主题的一行判断，连同它的代表原文。

    出自笔记里「八大主题归纳」那张表的一个单元格，是语料中主题最明确、
    也最凝练的文字——它同时是检索线索（当查询用）和可用的回答材料
    （引它完全合规：原文照抄自语料，出处就是那本书）。
    """

    book_id: str
    book_title: str
    theme: str
    judgment: str
    quote: str

    @property
    def text(self) -> str:
        """判断 + 代表句，用作检索查询。"""
        return f"{self.judgment} {self.quote}".strip()


def build_theme_rows(books: Iterable) -> dict[str, dict[str, ThemeAnchor]]:
    """读出各书「八大主题归纳」表，得到 书 → {主题: 主题锚}。

    表里没写的书就没有主题——不猜、不补默认值（与知识库建图同一条规矩）。
    同一主题在同一本书里出现多次只取第一条：有的书被切成多个文件（如
    《人性的弱点》上/下篇），表里的内容是重复的，取两次只会让它在查询里
    占双倍分量。
    """
    from .kb.parse import parse_theme_table  # 局部导入：kb 只在建索引时需要

    from .insight.data import VALID_THEMES

    mapping: dict[str, dict[str, ThemeAnchor]] = {}
    for book in books:
        rows = mapping.setdefault(book.book_id, {})
        for chapter in getattr(book, "chapters", ()) or ():
            for row in parse_theme_table(getattr(chapter, "content", "") or ""):
                if row.theme not in VALID_THEMES or row.theme in rows:
                    continue
                rows[row.theme] = ThemeAnchor(
                    book_id=book.book_id,
                    book_title=getattr(book, "title", "") or "",
                    theme=row.theme,
                    judgment=row.judgment,
                    quote=row.quote,
                )
        if not rows:
            mapping.pop(book.book_id, None)
    return mapping


def build_book_themes(books: Iterable) -> dict[str, frozenset[str]]:
    """书 → 主题集合。由 :func:`build_theme_rows` 派生，避免重复解析。"""
    return {
        book_id: frozenset(rows)
        for book_id, rows in build_theme_rows(books).items()
    }


def theme_anchors(
    rows: Mapping[str, Mapping[str, ThemeAnchor]],
    themes: Sequence[str],
    *,
    per_theme: int = ANCHORS_PER_THEME,
    limit: int = ANCHOR_LIMIT,
) -> list[ThemeAnchor]:
    """取出这几个主题的主题锚，按对口程度排序、每主题限本数。

    排序先按主题顺序（路由结果本身有序），再按对口系数——同样讲处世，
    《论语》《菜根谭》的说法比《贞观政要》更值得先拿出来。
    """
    picked: list[ThemeAnchor] = []
    for theme in themes:
        candidates = [
            row[theme] for row in rows.values() if theme in row
        ]
        candidates.sort(key=lambda a: (-affinity(a.book_id), a.book_id))
        picked.extend(candidates[:per_theme])
    return picked[:limit]


def anchor_text(anchors: Sequence[ThemeAnchor]) -> str:
    """把主题锚拼成一路检索的查询。"""
    return " ".join(anchor.text for anchor in anchors if anchor.text)


def advice_weights(
    book_ids: Iterable[str],
    book_themes: Mapping[str, frozenset[str]],
    themes: Sequence[str],
) -> dict[str, float]:
    """把"对口程度"与"主题命中"合成一张 书 → 权重 的表。"""
    hit = set(themes)
    weights: dict[str, float] = {}
    for book_id in book_ids:
        weight = affinity(book_id)
        if hit and hit & set(book_themes.get(book_id, ())):
            weight *= THEME_BOOST
        weights[book_id] = weight
    return weights


# ── 门槛 ────────────────────────────────────────────────────────────────


def trim_by_score(
    results: Sequence,
    *,
    ratio: float = MIN_SCORE_RATIO,
    floor_count: int = MIN_RESULTS,
) -> list:
    """丢掉比最好的那条差太多的结果。

    用**相对**门槛而不是绝对分数：TF-IDF 的绝对分值随问句长短漂移很大
    （问得越短分越高），写死一个 0.1 会在长问题上把有用的结果也砍掉。

    按 :data:`MIN_RESULTS` 保底：零条时模型只能凭空发挥，而"给一两条 +
    允许它直说关系不大"比"零材料"更可控——提示词里已经写明了这一条。
    """
    if not results:
        return []
    best = results[0].score
    if best <= 0:
        return list(results[:floor_count])
    floor = best * ratio
    kept = [r for r in results if r.score >= floor]
    return kept if len(kept) >= floor_count else list(results[:floor_count])


def cap_source(results: Sequence, *, limit: int = MAX_SOURCE_RESULTS) -> list:
    """限制原典条数，其余位置让给笔记的深解。"""
    kept: list = []
    source_count = 0
    for result in results:
        if getattr(result, "kind", KIND_NOTES) == KIND_SOURCE:
            if source_count >= limit:
                continue
            source_count += 1
        kept.append(result)
    return kept


def cap_per_chapter(results: Sequence, *, limit: int = MAX_PER_CHAPTER) -> list:
    """限制同一章节的条数，把位置让给别的书。

    按 (书, 章) 计数而不是按书：同一本书的不同章节讲的是不同的事，
    挤在一起的才是同一个章节里被切碎的那些单元。
    """
    counts: dict[tuple[str, str], int] = {}
    kept: list = []
    for result in results:
        key = (getattr(result, "book_id", ""), getattr(result, "chapter_id", ""))
        if counts.get(key, 0) >= limit:
            continue
        counts[key] = counts.get(key, 0) + 1
        kept.append(result)
    return kept


def cap_modern(
    results: Sequence,
    *,
    limit: int = MAX_MODERN_RESULTS,
    modern: frozenset = MODERN_BOOKS,
) -> list:
    """限制现代白话书的条数，其余位置让给古籍。"""
    kept: list = []
    modern_count = 0
    for result in results:
        if getattr(result, "book_id", "") in modern:
            if modern_count >= limit:
                continue
            modern_count += 1
        kept.append(result)
    return kept


# ── 编排 ────────────────────────────────────────────────────────────────

#: 书 → 主题锚 的懒加载缓存。解析主题表只在首次提问时做一次；
#: 测试里换加载器时必须 :func:`reset_advice`（与 ``kb.reset_kb`` 同理）。
_theme_rows: Optional[dict[str, dict[str, ThemeAnchor]]] = None


def get_theme_rows(loader=None) -> dict[str, dict[str, ThemeAnchor]]:
    """书 → {主题: 主题锚}（懒加载）。"""
    global _theme_rows
    if _theme_rows is None:
        if loader is None:
            from .content_loader import get_loader

            loader = get_loader()
        _theme_rows = build_theme_rows(loader.get_books())
    return _theme_rows


def get_book_themes(loader=None) -> dict[str, frozenset[str]]:
    """书 → 主题集合（懒加载，由主题锚派生）。"""
    return {
        book_id: frozenset(rows)
        for book_id, rows in get_theme_rows(loader).items()
    }


def reset_advice() -> None:
    """丢弃主题锚缓存（测试换加载器时用）。"""
    global _theme_rows
    _theme_rows = None


@dataclass(frozen=True)
class AdviceHits:
    """一次求教检索的结果，连同它是怎么被路由的。

    带上 ``themes`` 是为了让它可被观测：召回不理想时，先看"主题判对了没"，
    比在权重数字里瞎调快得多。
    """

    results: tuple
    themes: tuple[str, ...]


def _hit_key(result) -> tuple:
    """一条结果的身份：同一段文字在两路检索里必须是同一条。"""
    return (
        getattr(result, "book_id", ""),
        getattr(result, "chapter_id", ""),
        getattr(result, "offset", 0),
        getattr(result, "kind", KIND_NOTES),
    )


def merge_passes(
    question_hits: Sequence,
    theme_hits: Sequence,
    *,
    question_mix: float = QUESTION_MIX,
    theme_mix: float = THEME_MIX,
) -> list:
    """把"按原问召回"与"按主题召回"两路合成一份排序。

    各自先按本路最高分归一化——两路的查询不同（原问 vs 主题锚），TF-IDF
    的绝对分值不可比，硬加会让一路压过另一路。归一化后再加权，配比才有意义。

    只在其中一路出现的结果保留它那一路的权重：只在主题那路出现的段落，
    说明它主题对得上、但没撞上原问的字面——这正是主题路由要捞的东西。

    合并后的分数**写回结果**：下游（门槛、限流、以及任何看分数的地方）
    都按它排序，留着各路自己的原始分值会出现"排在前面却分数更低"。
    """
    merged: dict[tuple, float] = {}

    def absorb(hits: Sequence, share: float) -> None:
        if not hits:
            return
        best = hits[0].score
        for hit in hits:
            ratio = (hit.score / best) if best > 0 else 0.0
            merged[_hit_key(hit)] = merged.get(_hit_key(hit), 0.0) + share * ratio

    absorb(question_hits, question_mix)
    absorb(theme_hits, theme_mix)

    by_key = {_hit_key(hit): hit for hit in list(question_hits) + list(theme_hits)}
    ranked = sorted(merged.items(), key=lambda pair: pair[1], reverse=True)
    return [
        replace(by_key[key], score=score)
        for key, score in ranked
        if key in by_key
    ]


def search_for_advice(
    retriever,
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    loader=None,
    context: str = "",
) -> AdviceHits:
    """求教场景的检索：主题路由 → 两路召回合并 → 原典限流 → 相关度门槛。

    两路各有分工，缺一路都会退回到"生搬硬套"：

    - **原问那路**：保证答的是这件事。问"朋友借钱不还"就得谈借钱。
    - **主题锚那路**：保证落在主题上。口语里的"焦虑""创业"在古籍里根本
      不存在，只有把它换成《论语》说的"内省、克己"才召得到东西。

    主题认不出时退回单路——认不出还要套主题，等于把某个主题硬安上去。

    ``context`` 是上一轮的问句，只在追问时非空。**追问必须带上它**：
    "那我具体该说什么""可是他不同意呢"这种话里没有主语也没有对象，
    词面全是指代词，单独拿去检索几乎召不回任何对得上的段落——
    于是模型拿到的材料与正在聊的事无关，回答看着就是答非所问。
    把它拼在问句前面，检索才落回那件事上（主题路由仍只看本轮问句，
    指代词本来也判不出主题）。
    """
    query = f"{context.strip()} {question.strip()}".strip() if context.strip() else question
    themes = route_themes(question)
    book_ids = {doc["book_id"] for doc in retriever.documents}
    weights = advice_weights(book_ids, get_book_themes(loader), themes)

    # 多取一些再筛：门槛会砍掉尾部，先多拿才不至于砍完不够数
    pool = top_k * 4
    # 门槛砍在**合并之前**：合并后的分数是两路的归一化加权和，分布与原始
    # TF-IDF 分值完全不同，拿同一把尺子量会把结果砍到只剩两三条。
    # 各路按自己的尺度砍自己的尾部，合并时再一起排序。
    question_hits = trim_by_score(
        retriever.search(query, top_k=pool, book_weights=weights)
    )

    anchors = theme_anchors(get_theme_rows(loader), themes) if themes else []
    theme_hits = (
        trim_by_score(
            retriever.search(anchor_text(anchors), top_k=pool, book_weights=weights)
        )
        if anchors
        else []
    )

    merged = merge_passes(question_hits, theme_hits)
    # 索引章与导言是"关于这本书的说明"，不是这本书的见解——不当答案
    # 索引章与导言是"关于这本书的说明"，不是这本书的见解——不当答案
    merged = [
        hit for hit in merged if not _SKIP_CHAPTER_RE.search(hit.chapter_title or "")
    ]
    # 现代白话书的"原典"就是白话叙述本身，没有可引的文言语料；它在语料里的
    # 价值是那几篇提炼过的笔记。笔记留着，原典的位置让给古籍。
    merged = [
        hit
        for hit in merged
        if not (hit.book_id in MODERN_BOOKS and hit.kind == KIND_SOURCE)
    ]

    kept = cap_per_chapter(cap_modern(cap_source(merged, limit=MAX_SOURCE_RESULTS)))
    return AdviceHits(results=tuple(kept[:top_k]), themes=themes)


__all__ = [
    "ANCHOR_LIMIT",
    "ANCHORS_PER_THEME",
    "BOOK_AFFINITY",
    "DEFAULT_TOP_K",
    "MAX_MODERN_RESULTS",
    "MAX_PER_CHAPTER",
    "MAX_SOURCE_RESULTS",
    "MIN_RESULTS",
    "MODERN_BOOKS",
    "MIN_SCORE_RATIO",
    "QUESTION_MIX",
    "THEME_BOOST",
    "THEME_KEYWORDS",
    "THEME_MIX",
    "AdviceHits",
    "ThemeAnchor",
    "advice_weights",
    "affinity",
    "anchor_text",
    "build_book_themes",
    "build_theme_rows",
    "cap_modern",
    "cap_per_chapter",
    "cap_source",
    "get_theme_rows",
    "merge_passes",
    "reset_advice",
    "route_themes",
    "search_for_advice",
    "theme_anchors",
    "trim_by_score",
]
