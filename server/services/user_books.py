"""个人书库：用户自己加进来的书，以及"申请进公共书架"的审核流。

一本书会在两个地方出现
--------------------------------------------------------------------------
- ``user_books`` —— **私人书架**，每个用户只看得到自己的。
- ``public_books`` —— 公共书架里"由用户贡献"的那部分，审核通过后才写进来。

公共书架的另一半（内置 15 本）在代码里（``BOOK_SPECS``）与 ``books/`` 目录下，
不在库里。检索时两边合并。

权限怎么保证
--------------------------------------------------------------------------
凡是"某本书"的操作都带 ``user_id`` 一起进 SQL 的 ``WHERE``，而不是先查出来
再在 Python 里比对。前者少一次往返，也不会因为漏写一句 ``if`` 就让人删掉
别人的书——把边界交给数据库，比交给记性可靠。
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .book_search import BookCandidate
from .db import Database, DatabaseUnavailable
from .errors import DomainError
from .store import StoreBase

#: 阅读状态的合法取值
STATUSES = ("wish", "reading", "done")

#: 可见性取值
VISIBILITY_PRIVATE = "private"    # 自己看
VISIBILITY_PENDING = "pending"    # 已申请公开，等审核
VISIBILITY_PUBLIC = "public"      # 已进公共书架
VISIBILITY_REJECTED = "rejected"  # 被驳回
VISIBILITIES = (
    VISIBILITY_PRIVATE, VISIBILITY_PENDING, VISIBILITY_PUBLIC, VISIBILITY_REJECTED,
)

#: 单次列表返回上限
MAX_LIMIT = 200


class UserBookError(DomainError):
    """可预期的业务错误（重复添加、状态非法、无权操作）。"""

    default_code = "shelf_error"


@dataclass(frozen=True)
class ShelfBook:
    """私人书架上的一本书。"""

    id: int
    user_id: int
    title: str
    author: str
    source_key: str
    source: str
    year: str
    cover_url: str
    summary: str
    subjects: tuple[str, ...]
    guide: str
    status: str
    visibility: str
    review_note: str
    created_ts: float
    updated_ts: float

    @property
    def has_guide(self) -> bool:
        return bool(self.guide.strip())

    @property
    def searchable_text(self) -> str:
        """参与检索的正文。

        书名与作者各写两遍：它们是相关性最强的信号，而 TF-IDF 里词频是有
        权重的。用户搜"余华"时，一本作者是余华的《活着》应当排在"只在导读里
        顺带提了一句余华"的书前面。
        """
        parts = [
            f"{self.title} {self.title}",
            f"{self.author} {self.author}" if self.author else "",
            " ".join(self.subjects),
            self.summary,
            self.guide,
        ]
        return "\n".join(p for p in parts if p.strip())


@dataclass(frozen=True)
class PublicBook:
    """公共书架里由用户贡献的一本。"""

    id: int
    book_id: str
    title: str
    author: str
    category: str
    summary: str
    guide: str
    subjects: tuple[str, ...]
    from_user_id: Optional[int]
    created_ts: float

    @property
    def searchable_text(self) -> str:
        parts = [
            f"{self.title} {self.title}",
            f"{self.author} {self.author}" if self.author else "",
            " ".join(self.subjects),
            self.summary,
            self.guide,
        ]
        return "\n".join(p for p in parts if p.strip())


def _parse_subjects(raw: Any) -> tuple[str, ...]:
    """``subjects`` 列存的是 JSON 数组字符串。解析失败就当空——
    一条坏数据不该让整张书架列表打不开。"""
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(s).strip() for s in parsed if str(s).strip())


def _row_to_book(row: Any) -> ShelfBook:
    return ShelfBook(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        title=str(row["title"]),
        author=str(row["author"] or ""),
        source_key=str(row["source_key"] or ""),
        source=str(row["source"] or ""),
        year=str(row["year"] or ""),
        cover_url=str(row["cover_url"] or ""),
        summary=str(row["summary"] or ""),
        subjects=_parse_subjects(row["subjects"]),
        guide=str(row["guide"] or ""),
        status=str(row["status"] or "wish"),
        visibility=str(row["visibility"] or VISIBILITY_PRIVATE),
        review_note=str(row["review_note"] or ""),
        created_ts=float(row["created_ts"]),
        updated_ts=float(row["updated_ts"]),
    )


def _row_to_public(row: Any) -> PublicBook:
    return PublicBook(
        id=int(row["id"]),
        book_id=str(row["book_id"]),
        title=str(row["title"]),
        author=str(row["author"] or ""),
        category=str(row["category"] or ""),
        summary=str(row["summary"] or ""),
        guide=str(row["guide"] or ""),
        subjects=_parse_subjects(row["subjects"]),
        from_user_id=int(row["from_user_id"]) if row["from_user_id"] is not None else None,
        created_ts=float(row["created_ts"]),
    )


class UserBookStore(StoreBase):
    """私人书架与"贡献到公共书架"的读写。"""

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__(db)

    # ── 私人书架 ────────────────────────────────────────────────────

    def add(
        self,
        user_id: int,
        candidate: BookCandidate,
        *,
        guide: str = "",
        status: str = "wish",
    ) -> ShelfBook:
        """把一本书加进私人书架。同一本书重复添加时抛 :class:`UserBookError`。"""
        if status not in STATUSES:
            raise UserBookError("阅读状态不合法", "bad_status")
        title = (candidate.title or "").strip()
        if not title:
            raise UserBookError("书名不能为空", "bad_title")

        now = time.time()
        payload = (
            user_id,
            title,
            (candidate.author or "").strip(),
            (candidate.source_key or "").strip(),
            (candidate.source or "").strip(),
            (candidate.year or "").strip(),
            (candidate.cover_url or "").strip(),
            (candidate.summary or "").strip(),
            json.dumps(list(candidate.subjects), ensure_ascii=False),
            (guide or "").strip(),
            status,
            VISIBILITY_PRIVATE,
            now,
            now,
        )
        with self._db.session() as conn:
            if payload[3]:  # 有来源标识才判重；没标识的书允许重复加
                existing = conn.execute(
                    "SELECT id FROM user_books WHERE user_id = ? AND source_key = ?",
                    (user_id, payload[3]),
                ).fetchone()
                if existing is not None:
                    raise UserBookError("这本书已经在你的书架里了", "duplicate")
            try:
                cursor = conn.execute(
                    "INSERT INTO user_books "
                    "(user_id, title, author, source_key, source, year, cover_url, summary, "
                    " subjects, guide, status, visibility, created_ts, updated_ts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload,
                )
            except sqlite3.IntegrityError as exc:
                # 并发下唯一索引兜底（上面的先查后插有竞态窗口）
                raise UserBookError("这本书已经在你的书架里了", "duplicate") from exc
            book_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (book_id,)
            ).fetchone()
        return _row_to_book(row)

    def list_for(
        self,
        user_id: int,
        *,
        status: Optional[str] = None,
        limit: int = MAX_LIMIT,
        offset: int = 0,
    ) -> tuple[int, list[ShelfBook]]:
        """列出某人的书架，返回 ``(总数, 当前页)``。"""
        capped = max(1, min(int(limit), MAX_LIMIT))
        where = "user_id = ?"
        params: list[Any] = [user_id]
        if status:
            if status not in STATUSES:
                raise UserBookError("阅读状态不合法", "bad_status")
            where += " AND status = ?"
            params.append(status)

        with self._db.session() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM user_books WHERE {where}", tuple(params)
                ).fetchone()["n"]
            )
            rows = conn.execute(
                f"SELECT * FROM user_books WHERE {where} "
                "ORDER BY created_ts DESC, id DESC LIMIT ? OFFSET ?",
                tuple(params) + (capped, max(0, int(offset))),
            ).fetchall()
        return total, [_row_to_book(r) for r in rows]

    def get(self, book_id: int, *, user_id: Optional[int] = None) -> Optional[ShelfBook]:
        """取一本书。给了 ``user_id`` 就顺带校验归属——**别人的书查不到**，
        而不是"查到了但你不许看"。"""
        where = "id = ?"
        params: list[Any] = [int(book_id)]
        if user_id is not None:
            where += " AND user_id = ?"
            params.append(user_id)
        try:
            with self._db.session() as conn:
                row = conn.execute(
                    f"SELECT * FROM user_books WHERE {where}", tuple(params)
                ).fetchone()
        except DatabaseUnavailable:
            return None
        return _row_to_book(row) if row is not None else None

    def update(
        self,
        book_id: int,
        user_id: int,
        *,
        status: Optional[str] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Optional[ShelfBook]:
        """改自己的书。返回改后的记录；不存在或不属于该用户时返回 ``None``。"""
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            if status not in STATUSES:
                raise UserBookError("阅读状态不合法", "bad_status")
            sets.append("status = ?")
            params.append(status)
        if title is not None:
            clean = title.strip()
            if not clean:
                raise UserBookError("书名不能为空", "bad_title")
            sets.append("title = ?")
            params.append(clean)
        if author is not None:
            sets.append("author = ?")
            params.append(author.strip())
        if not sets:
            return self.get(book_id, user_id=user_id)

        sets.append("updated_ts = ?")
        params.append(time.time())
        params.extend([int(book_id), user_id])

        with self._db.session() as conn:
            cursor = conn.execute(
                f"UPDATE user_books SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                tuple(params),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (int(book_id),)
            ).fetchone()
        return _row_to_book(row)

    def remove(self, book_id: int, user_id: int) -> bool:
        """从自己的书架上删掉一本。"""
        with self._db.session() as conn:
            cursor = conn.execute(
                "DELETE FROM user_books WHERE id = ? AND user_id = ?",
                (int(book_id), user_id),
            )
            return cursor.rowcount > 0

    def submit_for_review(self, book_id: int, user_id: int) -> Optional[ShelfBook]:
        """申请把这本书放进公共书架。

        已被批准（``public``）或被驳回（``rejected``）的都能再申请一次：
        前者是重复动作，保持原状即可；后者给用户一个"改好了再来"的机会——
        驳回不该是一次性的终局。
        """
        book = self.get(book_id, user_id=user_id)
        if book is None:
            return None
        if book.visibility == VISIBILITY_PUBLIC:
            return book

        now = time.time()
        with self._db.session() as conn:
            conn.execute(
                "UPDATE user_books SET visibility = ?, review_note = '', "
                "reviewed_ts = NULL, updated_ts = ? WHERE id = ? AND user_id = ?",
                (VISIBILITY_PENDING, now, int(book_id), user_id),
            )
            row = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (int(book_id),)
            ).fetchone()
        return _row_to_book(row)

    def cancel_review(self, book_id: int, user_id: int) -> Optional[ShelfBook]:
        """撤回公开申请。"""
        book = self.get(book_id, user_id=user_id)
        if book is None or book.visibility != VISIBILITY_PENDING:
            return book
        now = time.time()
        with self._db.session() as conn:
            conn.execute(
                "UPDATE user_books SET visibility = ?, updated_ts = ? WHERE id = ? AND user_id = ?",
                (VISIBILITY_PRIVATE, now, int(book_id), user_id),
            )
            row = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (int(book_id),)
            ).fetchone()
        return _row_to_book(row)

    def counts_for_user(self, user_id: int) -> dict[str, int]:
        """某人的书架概览：总数与各状态数量。"""
        with self._db.session() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM user_books WHERE user_id = ? "
                "GROUP BY status",
                (user_id,),
            ).fetchall()
            pending = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM user_books "
                    "WHERE user_id = ? AND visibility = ?",
                    (user_id, VISIBILITY_PENDING),
                ).fetchone()["n"]
            )
        by_status = {str(r["status"]): int(r["n"]) for r in rows}
        return {
            "total": sum(by_status.values()),
            "wish": by_status.get("wish", 0),
            "reading": by_status.get("reading", 0),
            "done": by_status.get("done", 0),
            "pending": pending,
        }

    # ── 检索用 ──────────────────────────────────────────────────────

    def searchable_for(self, user_id: int) -> list[ShelfBook]:
        """某人的全部藏书，供检索融合使用。

        库不可用时返回空列表——**不是**"这个人没有书"，而是"这次取不到"。
        取不到就不融这一路，求教拿公共语料照样能答；为几本取不到的书把整次
        求教变成 500 是不划算的（与 :meth:`public_books` 同一做法）。

        这条不是理论问题：登录之后求教会**都**走到这里（匿名时 `user_id`
        为空、这一路根本不会被调用），所以"库一坏、求教就崩"是在账号体系
        上线之后才出现的，`test_history_api.py` 的降级用例把它抓了出来。
        """
        try:
            _, books = self.list_for(user_id, limit=MAX_LIMIT)
        except DatabaseUnavailable:
            return []
        return books

    def public_books(self) -> list[PublicBook]:
        """公共书架里由用户贡献的全部书。"""
        try:
            with self._db.session() as conn:
                rows = conn.execute(
                    "SELECT * FROM public_books ORDER BY created_ts DESC"
                ).fetchall()
        except DatabaseUnavailable:
            return []
        return [_row_to_public(r) for r in rows]

    # ── 审核（后台用）──────────────────────────────────────────────

    def list_pending(self, *, limit: int = MAX_LIMIT, offset: int = 0) -> tuple[int, list[ShelfBook]]:
        capped = max(1, min(int(limit), MAX_LIMIT))
        with self._db.session() as conn:
            total = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM user_books WHERE visibility = ?",
                    (VISIBILITY_PENDING,),
                ).fetchone()["n"]
            )
            rows = conn.execute(
                "SELECT * FROM user_books WHERE visibility = ? "
                "ORDER BY updated_ts ASC, id ASC LIMIT ? OFFSET ?",
                (VISIBILITY_PENDING, capped, max(0, int(offset))),
            ).fetchall()
        return total, [_row_to_book(r) for r in rows]

    def review(
        self,
        book_id: int,
        *,
        approve: bool,
        note: str = "",
        category: str = "",
    ) -> Optional[ShelfBook]:
        """审核一本书。批准则同时写进公共书架。

        批准是**幂等**的：重复批准不会在 ``public_books`` 里留下两条。
        """
        now = time.time()
        with self._db.session() as conn:
            row = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (int(book_id),)
            ).fetchone()
            if row is None:
                return None
            book = _row_to_book(row)

            if approve:
                conn.execute(
                    "UPDATE user_books SET visibility = ?, review_note = ?, reviewed_ts = ?, "
                    "updated_ts = ? WHERE id = ?",
                    (VISIBILITY_PUBLIC, note.strip(), now, now, book.id),
                )
                existing = conn.execute(
                    "SELECT id FROM public_books WHERE from_book_id = ?", (book.id,)
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "INSERT INTO public_books "
                        "(book_id, title, author, category, summary, guide, subjects, "
                        " from_user_id, from_book_id, created_ts) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _next_public_book_id(conn),
                            book.title,
                            book.author,
                            (category or "").strip() or "其他",
                            book.summary,
                            book.guide,
                            json.dumps(list(book.subjects), ensure_ascii=False),
                            book.user_id,
                            book.id,
                            now,
                        ),
                    )
            else:
                conn.execute(
                    "UPDATE user_books SET visibility = ?, review_note = ?, reviewed_ts = ?, "
                    "updated_ts = ? WHERE id = ?",
                    (VISIBILITY_REJECTED, note.strip(), now, now, book.id),
                )

            fresh = conn.execute(
                "SELECT * FROM user_books WHERE id = ?", (book.id,)
            ).fetchone()
        return _row_to_book(fresh)

    def set_guide(self, book_id: int, guide: str) -> bool:
        """写入导读。给后台任务用——加书时先入库、后补导读，用户不必等模型。

        空导读直接拒绝：它只会把"还没生成"和"生成了但为空"混成同一种状态。
        """
        text = (guide or "").strip()
        if not text:
            return False
        with self._db.session() as conn:
            cursor = conn.execute(
                "UPDATE user_books SET guide = ?, updated_ts = ? WHERE id = ?",
                (text, time.time(), int(book_id)),
            )
            return cursor.rowcount > 0

    def remove_public(self, public_id: int) -> bool:
        """把一本贡献书从公共书架撤下。``user_books`` 里的可见性跟着退回。"""
        with self._db.session() as conn:
            row = conn.execute(
                "SELECT from_book_id FROM public_books WHERE id = ?", (int(public_id),)
            ).fetchone()
            if row is None:
                return False
            cursor = conn.execute("DELETE FROM public_books WHERE id = ?", (int(public_id),))
            source_id = row["from_book_id"]
            if source_id is not None:
                conn.execute(
                    "UPDATE user_books SET visibility = ?, updated_ts = ? WHERE id = ?",
                    (VISIBILITY_PRIVATE, time.time(), int(source_id)),
                )
            return cursor.rowcount > 0

    def _count(self, sql: str, params: Sequence[Any] = ()) -> int:
        """跑一个 COUNT。库不可用时算 0——计数只用于展示，不该让整个页面挂掉。

        四个计数入口以前各抄了一遍 ``try/session/execute/int`` 的骨架，
        于是"库坏了返回 0"这条约定有四个副本。收在这里，以后改一处就够。
        """
        try:
            with self._db.session() as conn:
                return int(conn.execute(sql, tuple(params)).fetchone()["n"])
        except DatabaseUnavailable:
            return 0

    def count_all(self) -> int:
        return self._count("SELECT COUNT(*) AS n FROM user_books")

    def count_public(self) -> int:
        return self._count("SELECT COUNT(*) AS n FROM public_books")

    def count_pending(self) -> int:
        return self._count(
            "SELECT COUNT(*) AS n FROM user_books WHERE visibility = ?", (VISIBILITY_PENDING,)
        )

    def count_added_since(self, since: float) -> int:
        """某时刻之后新增了多少本（后台"今日新增"用）。"""
        return self._count("SELECT COUNT(*) AS n FROM user_books WHERE created_ts >= ?", (since,))


def _next_public_book_id(conn: Any) -> str:
    """分配下一个公共书号，形如 ``u01``。

    前缀 ``u`` 与内置的 ``01``..``15`` 天然分开，不会撞号。取当前最大号 +1，
    而不是"取总数 +1"——后者在删过书之后会发重号。
    """
    row = conn.execute(
        "SELECT book_id FROM public_books WHERE book_id LIKE 'u%' "
        "ORDER BY CAST(SUBSTR(book_id, 2) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return "u01"
    try:
        number = int(str(row["book_id"])[1:])
    except ValueError:
        return "u01"
    return f"u{number + 1:02d}"


# ── 全局单例 ────────────────────────────────────────────────────────────

_store: Optional[UserBookStore] = None


def get_user_book_store() -> UserBookStore:
    global _store
    if _store is None:
        _store = UserBookStore()
    return _store


def reset_user_book_store(store: Optional[UserBookStore] = None) -> None:
    global _store
    _store = store
