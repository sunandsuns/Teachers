"""所有 Store 的共同底座。

为什么要有它
--------------------------------------------------------------------------
``Database`` 是惰性的：构造不碰磁盘，第一次用时才知道库能不能打开。于是
"这个库现在好不好用"要能被上层问到——路由层据此决定降级还是回 503。

问题是这句话以前被说了五遍：``AdminStore`` / ``AuthStore`` / ``HistoryStore``
/ ``ProfileStore`` / ``UserBookStore`` 各自把 ``Database`` 的三个属性转发一遍，
措辞还都一样（``str(self._db.path)`` 这种细节都一致）。转发本身无害，有害的是
**语义有了五个副本**：哪天 ``error`` 想加个前缀、``db_path`` 想脱敏，就得记得
改五处，而漏掉的那处不会报错，只会在某个界面上显示得不一样。

这里只做一件事——让"库好不好用"只有一种说法。业务逻辑一概不放：Store 之间
除了"共享一个库"之外没有别的共同点，基类一旦开始收业务，就又变成杂物间了。

关于 ``_lock``
--------------------------------------------------------------------------
不放基类。五个 Store 里只有 ``HistoryStore`` 需要它（保护"机会式清理"的检查
标志），其余四个一个字都没用到。给用不上的人发一把锁，正是"基类变成杂物间"
的起点。需要的子类自己建。
"""

from __future__ import annotations

from typing import Optional

from .db import Database

__all__ = ["StoreBase"]


class StoreBase:
    """持一个 :class:`Database`，并把它的健康状态原样透出去。

    子类构造时调 ``super().__init__(db)`` 即可；下面三个属性不用再写。

    注意这三个都是**属性**（``@property``）而不是方法，调用方写 ``store.available``。
    之所以跟 ``Database`` 保持一致：它们本来就是同一个值的两层壳，多一对括号
    只会让人怀疑"是不是每次调用都会重新探测"。
    """

    def __init__(self, db: Optional[Database] = None) -> None:
        #: 传 None 表示"用默认那个库"。不在这里建连接——``Database`` 自己是惰性的。
        self._db = db if db is not None else Database()

    @property
    def available(self) -> bool:
        return self._db.available

    @property
    def error(self) -> str:
        return self._db.error

    @property
    def db_path(self) -> str:
        return str(self._db.path)
