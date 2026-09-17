"""SQLite 存储层：定位库文件、建库建表、开连接。

为什么是 SQLite
--------------------------------------------------------------------------
桌面版要"下载下来就能用"，不能要求对方先装一个数据库服务。SQLite 是标准库
自带的（``import sqlite3`` 即可），单文件、零配置、零进程，双击 exe 的那一刻
库就已经建好了——这正是「用户下载应用可以直接创建数据库」的实现方式：
不用安装、不用初始化脚本，第一次用到时自己把文件与表建出来。

为什么把存储与业务拆开
--------------------------------------------------------------------------
建库、连接、失败处理是"怎么存"；保存什么、保留多久是"存什么"。前者以后可能
换（换 Postgres、加缓存），后者是产品规则。混在一起的话，改存储就得动业务。

失败即降级的约定
--------------------------------------------------------------------------
数据库可能建不出来（程序目录只读、磁盘满、杀软拦截）。那种情况下**不能让
整个应用跟着挂**：书架、寻章、求教都不依赖数据库，历史记录只是附加功能。
所以本模块一律不抛异常给上层，而是把失败记在 :attr:`Database.error` 里，
由业务层决定"这一次没有历史记录"该怎么办。
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from ..paths import resolve_data_dir

#: 数据库文件名。刻意用 ASCII：用户未必会去翻它，但排查问题时
#: 命令行工具（以及各种 sqlite 客户端）对非 ASCII 路径并不都友好。
DB_FILENAME = "history.db"

#: 建表语句。全部 ``IF NOT EXISTS``，因此每次打开都执行一遍即可完成"迁移"，
#: 不需要额外的版本表——当前只有一个初始版本，等真的需要改结构时再引入。
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question        TEXT    NOT NULL,
    answer          TEXT    NOT NULL,
    -- 实际产出回答的模型名；NULL 表示这次是本地检索降级，没走模型
    model           TEXT,
    retrieved_count INTEGER NOT NULL DEFAULT 0,
    -- Unix 时间戳（秒）。只存数值、显示时再格式化：清理与排序都要拿它做比较，
    -- 多存一份 ISO 字符串就多一个可能与之不一致的来源。
    created_ts      REAL    NOT NULL
);

-- 列表页永远按时间倒序取，且清理按时间范围删，这条索引两处都吃得上
CREATE INDEX IF NOT EXISTS idx_history_created ON history (created_ts DESC);
"""


class DatabaseUnavailable(RuntimeError):
    """数据库不可用（建不出来 / 打不开 / 磁盘满）。

    由 :meth:`Database.session` 抛出，业务层捕获后按"这次没有数据库"处理。
    """


class Database:
    """一个 SQLite 库文件的句柄。

    **惰性**：构造时不碰磁盘，第一次真正用到才建目录、建库、建表。
    测试里往环境里塞一个临时路径即可，不必关心清理时机。

    **线程安全**：FastAPI 会把同步接口丢进线程池，同一个存储会被多个线程
    同时用到。这里用一把锁守住"初始化"，连接则一次操作一个（不共享 sqlite
    连接对象——它默认不允许跨线程使用，共享反而要处处小心）。桌面版单用户，
    这点开销可以忽略。
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else resolve_data_dir() / DB_FILENAME
        self._lock = threading.Lock()
        #: None = 还没试过；True/False = 试过的结论（失败不重试，避免每次请求都
        #: 白等一次磁盘超时）
        self._ready: Optional[bool] = None
        self._error = ""

    # ── 状态 ────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """库文件的完整路径（未必存在——见 :attr:`available`）。"""
        return self._path

    @property
    def available(self) -> bool:
        """库是否真的可用。首次访问会触发建库。"""
        self._prepare()
        return bool(self._ready)

    @property
    def error(self) -> str:
        """不可用的原因（可用时为空串）。直接给人看，所以是中文之外的
        技术描述 + 原始异常，便于对照排查。"""
        return self._error

    # ── 建库 ────────────────────────────────────────────────────────────

    def _prepare(self) -> bool:
        """建目录 → 建库 → 建表。幂等，失败只记原因、不抛。"""
        with self._lock:
            if self._ready is not None:
                return self._ready
            self._ready = False
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                connection = self.connect()
                try:
                    # WAL 让"读列表"与"写一条"不互相阻塞。失败不算致命
                    # （某些网络盘不支持），因此单独兜住。
                    try:
                        connection.execute("PRAGMA journal_mode = WAL")
                    except sqlite3.Error:
                        pass
                    connection.executescript(SCHEMA)
                    connection.commit()
                finally:
                    connection.close()
            except (sqlite3.Error, OSError) as exc:
                self._error = "%s: %s" % (type(exc).__name__, exc)
                return False
            self._ready = True
            self._error = ""
            return True

    def connect(self) -> sqlite3.Connection:
        """开一个连接（调用方负责关闭）。**不检查可用性**，供 :meth:`_prepare`
        自己使用——否则就递归了。"""
        connection = sqlite3.connect(str(self._path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """一次事务性操作：正常提交、出错回滚、最后必然关闭。

        库不可用时抛 :class:`DatabaseUnavailable`——这是本模块**唯一**外抛的
        异常，语义明确（"没有数据库可用"），不是"操作失败"。
        """
        if not self._prepare():
            raise DatabaseUnavailable(self._error)
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

    def size_bytes(self) -> int:
        """库占用的字节数。WAL 模式下数据可能还在 ``-wal`` 侧文件里，
        三个文件一起算才不会报出"0 字节"这种假象。"""
        total = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self._path) + suffix)
            try:
                total += candidate.stat().st_size
            except OSError:
                continue
        return total
