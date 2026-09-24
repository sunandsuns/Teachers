"""统一检索：公共书架 + 用户私人书架。

为什么不"合并文档再建一个索引"
--------------------------------------------------------------------------
把用户的书直接塞进公共索引会**污染**它：公共索引是全局共享的，一旦混进某个
人的私人藏书，别人搜同一句话就会搜到不属于他的内容。反过来，给每个用户建一份
"公共 + 私人"的完整索引也太贵——公共语料 8500 多篇，每人复制一份不现实。

所以走"两路检索 + 排名融合"：公共一路、用户私人书架一路，各自独立打分，
再用 RRF（Reciprocal Rank Fusion）把两份排名合成一份。

为什么是 RRF 而不是直接比分数
--------------------------------------------------------------------------
两边的 IDF 基准不同——公共索引有 8500 篇文档，用户书架可能只有 5 篇。同一个
词在后者里的 IDF 天然大得多，余弦相似度也就整体偏高。直接比分数，用户书架的
结果会无脑压过公共语料，哪怕它其实没那么相关。RRF 只用**名次**不用分数，
天然免疫这种基准差异，是混合检索里的标准做法。
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Mapping, Optional, Sequence

from .retriever import (
    KIND_SHELF,
    SearchResult,
    TFIDFRetriever,
    ensure_retriever,
)
from .user_books import ShelfBook, get_user_book_store

#: RRF 的平滑常数。60 出自原论文，作用是把"第 1 名"与"第 2 名"的差距压得不
#: 那么悬殊——否则任何一路的第一名都会直接锁定最终第一名。
RRF_K = 60

#: 每路各取多少条候选再融合。取 top_k 的两倍，给融合留出腾挪空间。
CANDIDATE_FACTOR = 2

#: 书架子索引的缓存：``user_id -> (指纹, 索引)``。
_cache: dict[int, tuple[str, TFIDFRetriever]] = {}
_cache_lock = threading.Lock()


def _fingerprint(books: Sequence[ShelfBook]) -> str:
    """书架指纹。加书、删书、改状态、补上导读都会让它变化，从而触发重建。"""
    if not books:
        return "0"
    latest = max(b.updated_ts for b in books)
    return f"{len(books)}:{latest:.3f}:{sum(b.id for b in books)}"


def shelf_index(user_id: int) -> Optional[TFIDFRetriever]:
    """某个用户书架的检索索引（带缓存）。书架为空时返回 ``None``。

    只有几十本书，重建一次是毫秒级，所以缓存只是为了省掉"每次请求都重算"
    的那点开销，不必引入复杂的失效机制——指纹对不上就重建，简单且不会错。
    """
    books = get_user_book_store().searchable_for(user_id)
    if not books:
        return None

    stamp = _fingerprint(books)
    with _cache_lock:
        cached = _cache.get(user_id)
        if cached is not None and cached[0] == stamp:
            return cached[1]

    index = TFIDFRetriever()
    for book in books:
        index.add_document(
            book_id=f"shelf-{book.id}",
            book_title=book.title,
            chapter_id="guide" if book.has_guide else "meta",
            chapter_title="导读" if book.has_guide else "书目",
            content=book.searchable_text,
            kind=KIND_SHELF,
        )
    index.build_index()

    with _cache_lock:
        _cache[user_id] = (stamp, index)
    return index


def invalidate_shelf(user_id: Optional[int] = None) -> None:
    """丢掉书架索引缓存。``None`` 表示全丢（测试用）。"""
    with _cache_lock:
        if user_id is None:
            _cache.clear()
        else:
            _cache.pop(user_id, None)


def _key(result: SearchResult) -> str:
    """融合时的去重键。同一段落从两路都命中时要能认出来是同一条。"""
    return f"{result.book_id}|{result.chapter_id}|{result.content[:40]}"


def rrf_fuse(
    rankings: Sequence[Sequence[SearchResult]], *, top_k: int
) -> list[SearchResult]:
    """把多路排名合成一份。

    分数归一化到 (0, 1]：RRF 的原始分数量级在 0.01 上下，直接拿去展示会被
    读成"匹配度只有 1%"。除以最高分之后，分数仍与名次单调一致，量级也回到
    了前端熟悉的区间。
    """
    scores: dict[str, float] = {}
    items: dict[str, SearchResult] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking, start=1):
            key = _key(result)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            items.setdefault(key, result)

    if not scores:
        return []

    ordered = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    best = ordered[0][1]
    return [replace(items[key], score=score / best) for key, score in ordered[: max(1, top_k)]]


def search_all(
    query: str,
    *,
    top_k: int = 5,
    kind: Optional[str] = None,
    user_id: Optional[int] = None,
    book_weights: Optional[Mapping[str, float]] = None,
) -> list[SearchResult]:
    """检索。给了 ``user_id`` 就把他的私人书架一并纳入。

    ``kind`` 的语义：
    - ``None`` —— 全库（公共笔记 + 公共原典）**加上**私人书架
    - ``"notes"`` / ``"source"`` —— 只看公共的那一路（用户明确要的就是它）
    - ``"shelf"`` —— 只看私人书架
    """
    limit = max(1, top_k)

    if kind == KIND_SHELF:
        if user_id is None:
            return []
        index = shelf_index(user_id)
        return index.search(query, top_k=limit) if index is not None else []

    public = ensure_retriever()
    public_results = public.search(
        query, top_k=limit * CANDIDATE_FACTOR, kind=kind, book_weights=book_weights
    )

    # 指定了 notes / source 就不掺私人书架——用户要的就是"只看某一路"
    if user_id is None or kind is not None:
        return public_results[:limit]

    index = shelf_index(user_id)
    if index is None:
        return public_results[:limit]

    shelf_results = index.search(query, top_k=limit * CANDIDATE_FACTOR)
    if not shelf_results:
        return public_results[:limit]

    return rrf_fuse([public_results, shelf_results], top_k=limit)
