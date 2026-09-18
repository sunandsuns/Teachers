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

结构变更怎么办
--------------------------------------------------------------------------
建表语句全是 ``IF NOT EXISTS``，对**已经存在**的表不会补列。桌面版的升级方式
是"把新包解压到旧目录旁边"——库会接着用，不能假设用户会删库重来。所以除了
建表，还有一份 :data:`MIGRATIONS`：每次打开都看一眼列在不在，缺了就补。
当前规模不需要版本表，一张补列清单足够。
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
#: 缺的列由 :data:`MIGRATIONS` 补上。
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
    -- 同一个话题（一次会话里的连续追问）共用一个 id。升级前的老记录为 NULL，
    -- 显示时各算各的话题，不回填。
    conversation_id TEXT,
    -- Unix 时间戳（秒）。只存数值、显示时再格式化：清理与排序都要拿它做比较，
    -- 多存一份 ISO 字符串就多一个可能与之不一致的来源。
    created_ts      REAL    NOT NULL
);

-- 列表页永远按时间倒序取，且清理按时间范围删，这条索引两处都吃得上
CREATE INDEX IF NOT EXISTS idx_history_created ON history (created_ts DESC);

CREATE TABLE IF NOT EXISTS traits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 特征分类（性格/年龄/…）。界面上人形两侧的引线按它分组，是个封闭集合
    category    TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    -- 依据：用户说过的哪句话让模型这么判断。没有依据的特征不该存在
    evidence    TEXT    NOT NULL DEFAULT '',
    confidence  REAL    NOT NULL DEFAULT 0.5,
    created_ts  REAL    NOT NULL,
    updated_ts  REAL    NOT NULL
);

-- 按类别取用、按把握排序，这条索引吃得上
CREATE INDEX IF NOT EXISTS idx_traits_category ON traits (category, confidence DESC);
"""

#: 依赖后加列的语句，**必须等 :data:`MIGRATIONS` 跑完再执行**。
#:
#: 老库里还没有 ``conversation_id`` 这一列，先建这个索引会直接报
#: ``no such column``——而建库一旦失败，整个历史记录功能就不可用了，
#: 升级用户打开「回响」只会看到一片空白。这条差点被漏掉。
POST_MIGRATION_DDL = """
CREATE INDEX IF NOT EXISTS idx_history_conversation ON history (conversation_id, created_ts);
"""

#: 后加的列。``(表名, 列名, 补列语句)``。
#: ``ALTER TABLE ADD COLUMN`` 只对**已有**的旧库需要，新建的库在 :data:`SCHEMA`
#: 里就有这些列了。
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("history", "conversation_id", "ALTER TABLE history ADD COLUMN conversation_id TEXT"),
)


class DatabaseUnavailable(RuntimeError):
    """数据库不可用（建不出来 / 打不开 / 磁盘满）。

    由 :meth:`Database.session` 抛出，业务层捕获后按"这次没有数据库"处理。
    """


class Database:
    """一个 SQLite 库文件的句柄。

    **惰性**：构造时不碰磁盘，第一次真正用到才建目录、建库、建表。
    测试里往环境里塞一个临时路径即可，不必关心清理时机。

    **连接是复用的**——这一点比看上去要紧
    --------------------------------------------------------------------------
    在本机（Windows）实测：对这个库每做一次"新建连接 → 查一条 → 关掉"，
    稳定要 **70ms**，连 ``SELECT 1`` 也不例外；而把同一个文件换成非 WAL 的
    日志模式，同样的操作只要 **0.5ms**。差的不是查询，是 SQLite 打开一个 WAL
    库时要重建 ``-wal`` / ``-shm`` 这两份共享内存文件的开销：最后一个连接
    关闭时它们被删掉，下一次打开又得从头来过。

    ``session()`` 原先正是"一次操作一条连接"，于是碰库的接口都背上了这个
    固定成本——``/api/profile`` 一次请求要做七次操作，实测 471ms（端到端
    644ms）。改成全程只留一条连接后，同样的七次操作降到 **0.1ms**。

    代价是操作被**串行化**（一把 ``RLock`` 一直守到退出 ``with`` 块）。桌面版
    单用户、语句都是微秒级，这个代价可以忽略；换来的是不再有连接间的写冲突，
    ``database is locked`` 这类问题从源头上消失。
    **但别在 ``session()`` 里做慢活**（调模型、读大文件、发网络请求）——
    那会把别的请求一起堵在门外。现有调用点都是纯 SQL，改代码时请守住这条。

    **线程安全**：FastAPI 会把同步接口丢进线程池，同一个存储会被多个线程用到。
    连接以 ``check_same_thread=False`` 打开，但访问一律在锁内，所以仍然安全。
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else resolve_data_dir() / DB_FILENAME
        #: 用 RLock：``session()`` 持着它，而它内部会调 ``_prepare()``，
        #: 后者也要这把锁。普通 Lock 在这里会当场死锁。
        self._lock = threading.RLock()
        #: None = 还没试过；True/False = 试过的结论（失败不重试，避免每次请求都
        #: 白等一次磁盘超时）
        self._ready: Optional[bool] = None
        self._error = ""
        #: 那条被复用的连接。None 表示还没建，或刚被废弃
        self._conn: Optional[sqlite3.Connection] = None

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

    # ── 连接 ────────────────────────────────────────────────────────────

    def _connection(self) -> sqlite3.Connection:
        """取那条被复用的连接，没有就建一条。**调用方必须已持有 ``_lock``。**

        ``check_same_thread=False``：FastAPI 把同步接口丢进线程池，这条连接
        会在不同线程上被用到。安全性由调用方的那把锁保证，不是靠 SQLite。
        """
        if self._conn is None:
            self._conn = self.connect(check_same_thread=False)
        return self._conn

    def _discard(self) -> None:
        """把当前那条连接丢掉（关掉并置空）。调用方必须已持有 ``_lock``。

        用在"连接坏了"的场合：用户把库文件删了或挪走、盘符掉了。下一次访问
        会自然重建，不必人工干预。
        """
        connection, self._conn = self._conn, None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def connect(self, *, check_same_thread: bool = True) -> sqlite3.Connection:
        """建一条新连接（调用方负责关闭）。

        这是**唯一**开连接的地方：复用连接与独立连接都从这里出去，所以
        "库打不开"只有这一个失败点，注入故障（测试里 patch 掉它）也只需盯住这里。

        ``check_same_thread=True`` 是 sqlite3 的默认值，也是"另开一条独立连接"
        该有的样子。复用连接那一条传 False——它必然跨线程被用到，安全性由
        :data:`Database._lock` 保证，见类注释。
        """
        connection = sqlite3.connect(
            str(self._path), timeout=5.0, check_same_thread=check_same_thread
        )
        connection.row_factory = sqlite3.Row
        return connection

    # ── 建库 ────────────────────────────────────────────────────────────

    def _prepare(self) -> bool:
        """建目录 → 建库 → 建表 → 补列。幂等，失败只记原因、不抛。"""
        with self._lock:
            if self._ready is not None:
                return self._ready
            self._ready = False
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                connection = self._connection()
                # WAL 让"读列表"与"写一条"不互相阻塞。失败不算致命
                # （某些网络盘不支持），因此单独兜住。
                try:
                    connection.execute("PRAGMA journal_mode = WAL")
                except sqlite3.Error:
                    pass
                connection.executescript(SCHEMA)
                self._migrate(connection)
                connection.executescript(POST_MIGRATION_DDL)
                connection.commit()
            except (sqlite3.Error, OSError) as exc:
                self._error = "%s: %s" % (type(exc).__name__, exc)
                self._discard()
                return False
            self._ready = True
            self._error = ""
            return True

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """给旧库补上新加的列。

        每次打开都查一遍 ``PRAGMA table_info``：代价是一次极轻的查询，换来的是
        "用户把新包解压到旧目录上、库照样能用"。
        """
        for table, column, statement in MIGRATIONS:
            existing = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                connection.execute(statement)

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """一次事务性操作：正常提交、出错回滚、连接**留着重用**。

        库不可用时抛 :class:`DatabaseUnavailable`——这是本模块**唯一**外抛的
        异常，语义明确（"没有数据库可用"），不是"操作失败"。

        回滚这里刻意兜的是 ``BaseException`` 而不是 ``sqlite3.Error``：连接
        复用之后，"异常没回滚"的后果比以前严重得多——留下的未提交事务会一直
        攥着写锁，之后每一次写都会失败。调用方抛什么（哪怕是自己代码里的
        ``TypeError``）都得先回滚干净再往外传。
        """
        with self._lock:
            if not self._prepare():
                raise DatabaseUnavailable(self._error)
            connection = self._connection()
            try:
                yield connection
            except BaseException as exc:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
                # 连接本身坏了（被外部关掉、文件没了）：丢掉它，
                # 下一次访问会自动重建。这一次按失败处理——业务层本就不抛异常。
                if isinstance(exc, sqlite3.ProgrammingError):
                    self._discard()
                raise
            connection.commit()

    def close(self) -> None:
        """关掉这条连接，并把状态复位成"还没准备过"。

        进程退出、以及测试里换数据目录时用；运行时不必调用。
        复位之后下次访问会重新走一遍建库（幂等），所以关掉再打开是安全的。
        """
        with self._lock:
            self._discard()
            self._ready = None

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
