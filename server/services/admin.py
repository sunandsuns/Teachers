"""后台管理：数据总览、直接操作数据库、审计留痕。

直接操作数据库这件事
--------------------------------------------------------------------------
这是运维工具，也是整个系统里最容易把库搞坏的地方。所以设了三道闸：

1. **表名白名单**：只认 ``sqlite_master`` 里真实存在、且不带 ``sqlite_``
   内部前缀的表。SQL 里出现的表名来自数据库自身，不来自请求体。
2. **列名白名单**：改行时逐列去比 ``PRAGMA table_info`` 的结果，不在表里的
   直接拒绝。所有值都是参数化绑定，没有任何用户输入被拼进 SQL。
3. **保护列**：``users.password_hash`` 与 ``users.salt`` 不允许直接改——
   绕过哈希逻辑写进去的值只会让这个人**永远登不上**，而且从界面上看不出
   哪里坏了。要改密码请走重置密码接口。

审计
--------------------------------------------------------------------------
每一次写操作都落一行 ``admin_audit``。没有痕迹的运维入口就是个隐患：
数据被改坏了，得能回答"是谁、什么时候、把哪一行改成了什么"。
"""

from __future__ import annotations

import time
from datetime import datetime, time as dtime
from typing import Any, Optional, Sequence

from .db import Database
from .errors import DomainError
from .store import StoreBase

#: 单次最多返回的行数。直接操作数据库的界面是给人看的，不是给程序导出的。
MAX_ROWS = 200

#: 不允许直接改的列。理由见模块注释。
PROTECTED_COLUMNS: frozenset[tuple[str, str]] = frozenset({
    ("users", "password_hash"),
    ("users", "salt"),
})

#: 单次查询审计记录的条数
AUDIT_LIMIT = 100


class AdminError(DomainError):
    """可预期的管理操作错误（表不存在、列不存在、动了保护列）。"""

    default_code = "admin_error"


def _today_start() -> float:
    """今天 0 点（本地时区）的时间戳。"""
    now = datetime.now()
    return datetime.combine(now.date(), dtime.min).timestamp()


class AdminStore(StoreBase):
    """后台用的数据访问。**所有方法都假定调用方已经验过管理员身份。**"""

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__(db)

    # ── 总览 ────────────────────────────────────────────────────────

    def overview(self) -> dict[str, Any]:
        """库层面的统计。语料规模由路由层补上（那是内容层的事）。"""
        today = _today_start()
        with self._db.session() as conn:
            def count(sql: str, params: Sequence[Any] = ()) -> int:
                return int(conn.execute(sql, tuple(params)).fetchone()["n"])

            return {
                "users": count("SELECT COUNT(*) AS n FROM users"),
                "admins": count("SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"),
                "history": count("SELECT COUNT(*) AS n FROM history"),
                "history_today": count(
                    "SELECT COUNT(*) AS n FROM history WHERE created_ts >= ?", (today,)
                ),
                "traits": count("SELECT COUNT(*) AS n FROM traits"),
                "shelf_books": count("SELECT COUNT(*) AS n FROM user_books"),
                "shelf_books_today": count(
                    "SELECT COUNT(*) AS n FROM user_books WHERE created_ts >= ?", (today,)
                ),
                "pending_review": count(
                    "SELECT COUNT(*) AS n FROM user_books WHERE visibility = 'pending'"
                ),
                "public_contributions": count("SELECT COUNT(*) AS n FROM public_books"),
                "sessions": count("SELECT COUNT(*) AS n FROM sessions"),
                "db_bytes": self._db.size_bytes(),
                "tables": len(self._table_names(conn)),
            }

    # ── 直接操作数据库 ──────────────────────────────────────────────

    def list_tables(self) -> list[dict[str, Any]]:
        """所有可操作的表及行数。"""
        with self._db.session() as conn:
            names = self._table_names(conn)
            result = []
            for name in names:
                rows = int(
                    conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
                )
                result.append({"name": name, "rows": rows})
        return result

    def describe_table(self, table: str) -> list[dict[str, Any]]:
        """表结构。"""
        with self._db.session() as conn:
            self._require_table(conn, table)
            return [
                {
                    "name": str(col["name"]),
                    "type": str(col["type"] or ""),
                    "notnull": bool(col["notnull"]),
                    "pk": bool(col["pk"]),
                    "protected": (table, str(col["name"])) in PROTECTED_COLUMNS,
                }
                for col in self._columns(conn, table)
            ]

    def read_rows(
        self, table: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[int, list[dict[str, Any]]]:
        """分页读一张表。返回 ``(总行数, 当前页)``。

        每行带上 ``_rowid``：它是改/删时的定位依据。用 rowid 而不是主键，
        是因为有些表（如 ``meta``）的主键是 TEXT，而 ``public_books`` 的
        ``book_id`` 与自增 id 也不是一回事。
        """
        capped = max(1, min(int(limit), MAX_ROWS))
        with self._db.session() as conn:
            self._require_table(conn, table)
            total = int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            rows = conn.execute(
                f"SELECT rowid AS _rowid, * FROM {table} ORDER BY rowid LIMIT ? OFFSET ?",
                (capped, max(0, int(offset))),
            ).fetchall()
        return total, [dict(r) for r in rows]

    def update_row(self, table: str, rowid: int, values: dict[str, Any]) -> bool:
        """改一行。列名与值都过白名单 / 参数化。"""
        if not values:
            raise AdminError("没有要修改的列")
        with self._db.session() as conn:
            self._require_table(conn, table)
            columns = {str(c["name"]) for c in self._columns(conn, table)}
            clean: dict[str, Any] = {}
            for key, value in values.items():
                if key not in columns:
                    raise AdminError(f"表 {table} 没有列 {key}", "unknown_column")
                if (table, key) in PROTECTED_COLUMNS:
                    raise AdminError(
                        f"列 {key} 不允许直接修改，请走对应的功能接口", "protected_column"
                    )
                clean[key] = value
            # 列名来自 PRAGMA 的结果（不是请求体），值全部走占位符
            assignments = ", ".join(f"{name} = ?" for name in clean)
            cursor = conn.execute(
                f"UPDATE {table} SET {assignments} WHERE rowid = ?",
                tuple(clean.values()) + (int(rowid),),
            )
            return cursor.rowcount > 0

    def delete_row(self, table: str, rowid: int) -> bool:
        """删一行。"""
        with self._db.session() as conn:
            self._require_table(conn, table)
            cursor = conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (int(rowid),))
            return cursor.rowcount > 0

    def insert_row(self, table: str, values: dict[str, Any]) -> int:
        """插一行。主要用于后台手工补数据。

        ``users`` 表**不开放插入**：密码哈希与 salt 得由 :mod:`services.auth`
        算出来，绕过它写进去的账号登不上。要加人请走注册或重置密码接口。
        """
        if not values:
            raise AdminError("没有要写入的列")
        if table == "users":
            raise AdminError("用户请通过注册接口创建", "protected_table")
        with self._db.session() as conn:
            self._require_table(conn, table)
            columns = {str(c["name"]) for c in self._columns(conn, table)}
            clean: dict[str, Any] = {}
            for key, value in values.items():
                if key not in columns:
                    raise AdminError(f"表 {table} 没有列 {key}", "unknown_column")
                if (table, key) in PROTECTED_COLUMNS:
                    raise AdminError(
                        f"列 {key} 不允许直接写入，请走对应的功能接口", "protected_column"
                    )
                clean[key] = value
            names = ", ".join(clean)
            marks = ", ".join("?" for _ in clean)
            cursor = conn.execute(
                f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(clean.values())
            )
            return int(cursor.lastrowid or 0)

    # ── 审计 ────────────────────────────────────────────────────────

    def audit(
        self, *, user_id: Optional[int], action: str, target: str = "", detail: str = ""
    ) -> None:
        """记一条操作痕迹。**失败不抛**——审计不该把正在做的操作搞失败。"""
        try:
            with self._db.session() as conn:
                conn.execute(
                    "INSERT INTO admin_audit (user_id, action, target, detail, created_ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, action[:60], target[:200], detail[:500], time.time()),
                )
        except Exception:  # noqa: BLE001 — 审计失败不该把正在做的操作搞失败
            pass

    def recent_audit(self, limit: int = AUDIT_LIMIT) -> list[dict[str, Any]]:
        """最近的审计记录。

        **库不可用时让它抛出去（→ 503），不返回空列表。** 这里与上面那个写方法
        刻意不同：审计读的是一个**裸列表**，响应里没有地方写"我没读到"，返回 ``[]``
        就是在说"从来没操作过"——那是在运维入口上说假话，比报错糟得多。
        （这就是 ``errors.py`` 里那条"裸列表不能降级"的规则；全项目允许降级的只有
        「回响」与「画像」，因为它们能在同一条响应里用 ``available`` 说清缘由。）
        """
        capped = max(1, min(int(limit), AUDIT_LIMIT))
        with self._db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM admin_audit ORDER BY created_ts DESC, id DESC LIMIT ?",
                (capped,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 内部 ────────────────────────────────────────────────────────

    def _table_names(self, conn: Any) -> list[str]:
        """真实存在的表。排除 ``sqlite_`` 内部表（``sqlite_sequence`` 之类）。"""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(r["name"]) for r in rows]

    def _require_table(self, conn: Any, table: str) -> str:
        """校验表名。**这是所有拼 SQL 的前提**——过了这一关，表名才算可信。"""
        name = (table or "").strip()
        if not name or name not in self._table_names(conn):
            raise AdminError(f"没有这张表：{table}", "unknown_table")
        return name

    @staticmethod
    def _columns(conn: Any, table: str) -> list[Any]:
        return list(conn.execute(f"PRAGMA table_info({table})"))


# ── 全局单例 ────────────────────────────────────────────────────────────

_store: Optional[AdminStore] = None


def get_admin_store() -> AdminStore:
    global _store
    if _store is None:
        _store = AdminStore()
    return _store


def reset_admin_store(store: Optional[AdminStore] = None) -> None:
    global _store
    _store = store
