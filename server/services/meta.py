"""``meta`` 表的唯一入口。

为什么要有它
--------------------------------------------------------------------------
``meta`` 是张通用键值表（``key TEXT PRIMARY KEY, value TEXT NOT NULL``），
三处功能各自往里存东西：

- ``auth`` 存签名密钥（``secret``）
- ``history`` 存"上次清理是哪一刻"（``last_purge_ts``，值是时间戳）
- ``profile`` 存形象性别、最像你的是谁、上次归纳到哪一刻

于是那句 upsert——``INSERT ... ON CONFLICT(key) DO UPDATE SET value = excluded.value``
——被**逐字抄了三遍**（``auth.py`` / ``history.py`` / ``profile.py``）。三份抄本
本身不算灾难，真正的风险在于：它们是**同一个 schema 约束的三种表述**。哪天表结构
变了（比如加 ``updated_ts``、比如换成 ``REPLACE INTO``），改了两处漏一处，漏掉的
那处不会报错——只会在某个用户改画像时静默不生效。

统一在这里，SQL 只有一份。

只管裸读写
--------------------------------------------------------------------------
归属前缀（``u7:avatar`` 那种）不在这里做，它属于 ``profile`` 自己的业务规则——
匿名访客要读不带前缀的老键，这条规则只对画像成立。这里只认"给我一个键"。

值一律按 ``str`` 收发。``history`` 存的其实是浮点数，转换由它自己做（见
``history._read_meta``）：存进去时 ``repr(float)``、取出来时 ``float(...)``，
坏值返回 None。让本模块替它猜类型，就等于把"这个键存的是什么"这件事又分散到
两个文件里。
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

__all__ = ["META_UPSERT_SQL", "read_value", "write_value", "delete_values"]

#: 有则改、无则插。写成常量而不是三处内联，是为了它能被一致地引用/测试。
META_UPSERT_SQL = (
    "INSERT INTO meta (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)

META_SELECT_SQL = "SELECT value FROM meta WHERE key = ?"
META_DELETE_SQL = "DELETE FROM meta WHERE key = ?"


def read_value(connection: Any, key: str) -> Optional[str]:
    """取一个键的值，没有就返回 ``None``。

    不吞异常：调用方（各 Store）自己决定"库坏了算没有记录"还是"往上抛"。
    """
    row = connection.execute(META_SELECT_SQL, (key,)).fetchone()
    return None if row is None else str(row["value"])


def write_value(connection: Any, key: str, value: str) -> None:
    """写入或覆盖一个键。"""
    connection.execute(META_UPSERT_SQL, (key, value))


def delete_values(connection: Any, keys: Iterable[str]) -> None:
    """批量删除。空列表直接返回，不发 SQL。"""
    rows = [(key,) for key in keys]
    if not rows:
        return
    connection.executemany(META_DELETE_SQL, rows)
