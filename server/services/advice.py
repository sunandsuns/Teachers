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
（``insight.data.VALID_THEMES``）。问题是**书级**的，所以对命中的书整体
提权，而不是去猜某一章属于哪个主题。
"""

from __future__ import annotations

from dataclasses import dataclass
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
#: 默认给几段。宁可少而准——提示词明确允许"没找到直接对应的就直说"。
DEFAULT_TOP_K = 5


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


def build_book_themes(books: Iterable) -> dict[str, frozenset[str]]:
    """从各书的深读笔记里读出「八大主题归纳」表，得到 书 → 主题集合。

    表里没写的书就没有主题——不猜、不补默认值（与知识库建图同一条规矩）。
    这样的书在主题路由里拿不到加成，按基础权重参与检索。
    """
    from .kb.parse import parse_theme_table  # 局部导入：kb 只在建索引时需要

    from .insight.data import VALID_THEMES

    mapping: dict[str, frozenset[str]] = {}
    for book in books:
        themes: set[str] = set()
        for chapter in getattr(book, "chapters", ()) or ():
            for row in parse_theme_table(getattr(chapter, "content", "") or ""):
                if row.theme in VALID_THEMES:
                    themes.add(row.theme)
        if themes:
            mapping[book.book_id] = frozenset(themes)
    return mapping


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


# ── 编排 ────────────────────────────────────────────────────────────────

#: 书 → 主题的懒加载缓存。解析 15 张主题表只在首次提问时做一次；
#: 测试里换加载器时必须 :func:`reset_advice`（与 ``kb.reset_kb`` 同理）。
_book_themes: Optional[dict[str, frozenset[str]]] = None


def get_book_themes(loader=None) -> dict[str, frozenset[str]]:
    """书 → 主题集合（懒加载）。"""
    global _book_themes
    if _book_themes is None:
        if loader is None:
            from .content_loader import get_loader

            loader = get_loader()
        _book_themes = build_book_themes(loader.get_books())
    return _book_themes


def reset_advice() -> None:
    """丢弃书 → 主题缓存（测试换加载器时用）。"""
    global _book_themes
    _book_themes = None


@dataclass(frozen=True)
class AdviceHits:
    """一次求教检索的结果，连同它是怎么被路由的。

    带上 ``themes`` 是为了让它可被观测：召回不理想时，先看"主题判对了没"，
    比在权重数字里瞎调快得多。
    """

    results: tuple
    themes: tuple[str, ...]


def search_for_advice(
    retriever,
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    loader=None,
) -> AdviceHits:
    """求教场景的检索：主题路由 → 对口加权 → 原典限流 → 相关度门槛。"""
    themes = route_themes(question)
    book_ids = {doc["book_id"] for doc in retriever.documents}
    weights = advice_weights(book_ids, get_book_themes(loader), themes)

    # 多取一些再筛：门槛会砍掉尾部，先多拿才不至于砍完不够数
    raw = retriever.search(question, top_k=top_k * 4, book_weights=weights)
    trimmed = trim_by_score(cap_source(raw, limit=MAX_SOURCE_RESULTS))
    return AdviceHits(results=tuple(trimmed[:top_k]), themes=themes)


__all__ = [
    "BOOK_AFFINITY",
    "DEFAULT_TOP_K",
    "MAX_SOURCE_RESULTS",
    "MIN_RESULTS",
    "MIN_SCORE_RATIO",
    "THEME_BOOST",
    "THEME_KEYWORDS",
    "AdviceHits",
    "advice_weights",
    "affinity",
    "build_book_themes",
    "cap_source",
    "reset_advice",
    "route_themes",
    "search_for_advice",
    "trim_by_score",
]
