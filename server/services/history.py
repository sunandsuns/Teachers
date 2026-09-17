"""求教历史（界面上的「回响」）：存取与保留策略。

为什么单独一层
--------------------------------------------------------------------------
「怎么存」在 ``db.py``（建库、连接、失败处理），这里只说「存什么、留多久」。
换存储时只动前者，改保留规则时只动这里。

保留策略：半个月
--------------------------------------------------------------------------
记录只留最近 ``retention_days``（默认 15 天）。清理是**机会式**的：每次用到
存储时先看一眼上次清理的时间，隔了半个月就顺手删掉过期记录、再记下这次时间。

为什么不用常驻定时器：桌面应用不是常开服务，进程没了就谈不上定时任务，
真起一个后台线程反而要处理"用户从不打开界面"这种大半时间都在发生的分支。
把清理挂在"用到它"的时刻，用户下次打开应用时库就已经被收拾干净了。

代价是清理有滞后：一条记录最多能活到"两个半个月"（正好在一轮清理之后写入，
就得等下一轮才被扫到）。对"只留半个月"这件事来说，这点误差无关紧要——
换来的是随时可中断、随时可重启，且不写任何额外状态。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .db import Database

#: 默认保留天数（半个月）
DEFAULT_RETENTION_DAYS = 15.0
#: 覆盖保留天数的环境变量。设 0 即"不留存"
RETENTION_ENV_VAR = "RSDS_HISTORY_RETENTION_DAYS"

#: 元信息表的键：上一次清理发生的时间戳
META_LAST_PURGE = "last_purge_ts"

#: 单次最多返回多少条。防止前端传个巨大的 limit 把整库读进内存
MAX_LIMIT = 200
DEFAULT_LIMIT = 20


def retention_days(env: Optional[dict[str, str]] = None) -> float:
    """从环境变量读保留天数；缺失或非法时用默认值。"""
    source = os.environ if env is None else env
    raw = source.get(RETENTION_ENV_VAR, "")
    try:
        value = float(raw) if raw else DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return value if value >= 0 else DEFAULT_RETENTION_DAYS


def _iso(ts: Optional[float]) -> Optional[str]:
    """时间戳 → 带时区的 ISO 8601（前端 ``new Date(…)`` 能直接解析）。"""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Record:
    """一条求教记录。"""

    id: int
    question: str
    answer: str
    #: 产出回答的模型名；None 表示这次是本地检索降级
    model: Optional[str]
    retrieved_count: int
    created_ts: float

    @property
    def llm_used(self) -> bool:
        """是否真由模型产出——以"有没有模型名"为准（与 ``qa.Answer`` 同一口径）。"""
        return self.model is not None

    @property
    def created_at(self) -> str:
        return _iso(self.created_ts) or ""


def _row_to_record(row: Any) -> Record:
    return Record(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        model=row["model"],
        retrieved_count=row["retrieved_count"],
        created_ts=row["created_ts"],
    )


def _read_meta(connection, key: str) -> Optional[float]:
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        return None


def _write_meta(connection, key: str, value: float) -> None:
    connection.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, repr(value)),
    )


class HistoryStore:
    """历史记录的读写。所有方法都**不抛异常**：数据库坏了就当这次没有记录。

    这看着像"把错误藏起来"，其实是这个功能的定位决定的：历史记录是附加项，
    书架、寻章、求教都不依赖它。为了"存一条历史失败"让用户看到 500、
    或者让一次已经成功的求教变成"请求失败"，是本末倒置。
    真正的故障信息留在 :meth:`status` 里，界面上照样看得见。
    """

    def __init__(self, db: Optional[Database] = None, *, days: Optional[float] = None) -> None:
        self._db = db if db is not None else Database()
        self._days = retention_days() if days is None else days
        self._lock = threading.Lock()
        #: 本进程内是否已经检查过"该不该清理"，省掉每次请求一次 meta 查询
        self._purge_checked = False

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

    @property
    def retention_seconds(self) -> float:
        return self._days * 86400.0

    @property
    def days(self) -> float:
        return self._days

    # ── 写 ──────────────────────────────────────────────────────────────

    def save(
        self,
        question: str,
        answer: str,
        *,
        model: Optional[str] = None,
        retrieved_count: int = 0,
        now: Optional[float] = None,
    ) -> Optional[int]:
        """存一条。返回新记录的 id；存不进去返回 None（调用方照常返回答案）。"""
        timestamp = time.time() if now is None else now
        try:
            self._maybe_purge(now=timestamp)
            with self._db.session() as connection:
                cursor = connection.execute(
                    "INSERT INTO history (question, answer, model, retrieved_count, created_ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (question, answer, model, int(retrieved_count), timestamp),
                )
                return int(cursor.lastrowid)
        except Exception:  # noqa: BLE001 — 库不可用或写入失败，都按"这次没记上"处理
            return None

    def delete(self, record_id: int) -> bool:
        """删一条。不存在返回 False。"""
        try:
            with self._db.session() as connection:
                cursor = connection.execute("DELETE FROM history WHERE id = ?", (record_id,))
                return cursor.rowcount > 0
        except Exception:  # noqa: BLE001
            return False

    def clear(self) -> int:
        """清空全部。返回删掉的条数（失败为 0）。"""
        try:
            with self._db.session() as connection:
                return connection.execute("DELETE FROM history").rowcount
        except Exception:  # noqa: BLE001
            return 0

    # ── 读 ──────────────────────────────────────────────────────────────

    def list(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> tuple[int, list[Record]]:
        """按时间倒序列出。返回 ``(总数, 本页记录)``——总数用于界面上"还有更多"。"""
        limit = max(1, min(int(limit), MAX_LIMIT))
        offset = max(0, int(offset))
        try:
            with self._db.session() as connection:
                total = int(connection.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"])
                rows = connection.execute(
                    "SELECT * FROM history ORDER BY created_ts DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                return total, [_row_to_record(row) for row in rows]
        except Exception:  # noqa: BLE001
            return 0, []

    def get(self, record_id: int) -> Optional[Record]:
        try:
            with self._db.session() as connection:
                row = connection.execute(
                    "SELECT * FROM history WHERE id = ?", (record_id,)
                ).fetchone()
                return _row_to_record(row) if row is not None else None
        except Exception:  # noqa: BLE001
            return None

    # ── 保留策略 ────────────────────────────────────────────────────────

    def purge(self, *, now: Optional[float] = None, force: bool = False) -> int:
        """删掉超过保留期的记录，返回删了几条。

        ``force=False`` 时受"每半个月才做一次"的节流约束（见模块头注释）；
        ``force=True`` 跳过节流，但仍然只删**已经过期**的，不是清空。
        """
        timestamp = time.time() if now is None else now
        cutoff = timestamp - self.retention_seconds
        try:
            with self._db.session() as connection:
                if not force:
                    last = _read_meta(connection, META_LAST_PURGE)
                    if last is not None and timestamp - last < self.retention_seconds:
                        return 0
                removed = connection.execute(
                    "DELETE FROM history WHERE created_ts < ?", (cutoff,)
                ).rowcount
                _write_meta(connection, META_LAST_PURGE, timestamp)
                return removed
        except Exception:  # noqa: BLE001
            return 0

    def _maybe_purge(self, *, now: Optional[float] = None) -> None:
        """进程内只认真检查一次；之后每次调用都直接返回。

        清一下这个标志也无妨——每小时最多重复一次 SQL，成本可以忽略，
        而"从不清理"才是真问题。
        """
        with self._lock:
            if self._purge_checked:
                return
            self._purge_checked = True
        self.purge(now=now)

    # ── 概览 ────────────────────────────────────────────────────────────

    def status(self, *, now: Optional[float] = None) -> dict[str, Any]:
        """给界面看的概览：可用与否、有多少条、什么时候会再清理。"""
        timestamp = time.time() if now is None else now
        available = self._db.available
        total = 0
        last_purge: Optional[float] = None
        if available:
            # 界面每次打开都会问一次状态，正好借这个时机做机会式清理
            self._maybe_purge(now=timestamp)
            try:
                with self._db.session() as connection:
                    total = int(
                        connection.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"]
                    )
                    last_purge = _read_meta(connection, META_LAST_PURGE)
            except Exception:  # noqa: BLE001
                total = 0
        return {
            "available": available,
            "error": self._db.error,
            "db_path": self.db_path,
            "total": total,
            "retention_days": self._days,
            "last_purge_at": _iso(last_purge),
            # 还没清理过时，把"下一次"说成从现在起算，界面上不至于空着
            "next_purge_at": _iso((last_purge if last_purge is not None else timestamp)
                                  + self.retention_seconds),
            "size_bytes": self._db.size_bytes() if available else 0,
        }


#: 进程级单例。历史记录是"一份数据"，多处各建一个 Database 只会互相打架
#: （各自持有连接、各自判断可用性）。
_store: Optional[HistoryStore] = None
_store_lock = threading.Lock()


def get_history_store() -> HistoryStore:
    """取历史记录存储（惰性创建，进程内共享）。"""
    global _store
    with _store_lock:
        if _store is None:
            _store = HistoryStore()
        return _store


def reset_history_store() -> None:
    """丢掉单例。测试用它隔离数据目录，运行时不必调用。"""
    global _store
    with _store_lock:
        _store = None
