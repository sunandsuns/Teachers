"""历史记录存储层的单元测试。

为什么单独测这一层
--------------------------------------------------------------------------
这里覆盖的都是"不出声就坏事"的规则：

- 数据库**自动创建**——用户下载应用后不该再做任何初始化；
- 保留期外的记录会被删掉——否则库只涨不消；
- 清理**每半个月才做一次**——做多了是白写磁盘，一次都不做库就废了；
- 数据库坏掉时**全部方法都不能抛异常**——历史记录是附加功能，
  它坏了不能把书架和求教一起拖下水。

最后一类是重点：``DatabaseUnavailable`` 只在存储层内部流转，
对业务层而言"没有数据库"表现为"这次没记上 / 列表为空"。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from server.services.db import Database, DatabaseUnavailable
from server.services.history import (
    DEFAULT_RETENTION_DAYS,
    HistoryStore,
    retention_days,
)

DAY = 86400.0
#: 一个远离当下、但足够大的基准时间，避免用例受"现在几点"影响
T0 = 1_000 * DAY


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "data" / "history.db")


@pytest.fixture
def store(db) -> HistoryStore:
    return HistoryStore(db)


def reopen(db: Database) -> HistoryStore:
    """模拟"关掉应用、过些日子再打开"：新的存储实例、同一个库文件。

    必须换实例：节流状态是**进程内**的（``_purge_checked``），
    复用同一个实例测不出"重新打开时才清理"这件事。
    """
    return HistoryStore(db)


def seed(db: Database, question: str, *, age_days: float, now: float = T0) -> int:
    """按指定年龄写一条记录。

    刻意不走 ``store.save()``：它会顺手做一次机会式清理并重置"上次清理时间"，
    而这一组用例恰恰要自己掌控清理的时机。这里只借 ``Database`` 的公开接口。
    """
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO history (question, answer, model, retrieved_count, created_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (question, "答案", None, 0, now - age_days * DAY),
        )
        return int(cursor.lastrowid)


def questions(store: HistoryStore) -> list[str]:
    return [record.question for record in store.list()[1]]


class TestDatabaseBootstrap:
    def test_creates_file_and_tables_on_demand(self, db):
        """自动建库：用户拿到应用即可用，不需要任何初始化步骤。"""
        assert db.available is True
        assert db.path.is_file()
        with db.session() as connection:
            names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert {"history", "meta"} <= names

    def test_missing_parent_dirs_are_created(self, tmp_path):
        """data/ 目录本身也不存在——一并建出来。"""
        assert Database(tmp_path / "deep" / "nested" / "history.db").available is True

    def test_unwritable_location_degrades_instead_of_raising(self, tmp_path, monkeypatch):
        """库建不出来时只记原因，不抛异常。"""

        def broken(self, **kwargs):
            # 替身要认下 connect 的全部签名（它多了一个 check_same_thread），
            # 否则抛出来的是 TypeError，不是我们要验的那种"库打不开"
            raise sqlite3.OperationalError("attempt to write a readonly database")

        monkeypatch.setattr(Database, "connect", broken)
        db = Database(tmp_path / "history.db")

        assert db.available is False
        assert "readonly" in db.error
        with pytest.raises(DatabaseUnavailable):
            with db.session():
                pass

    def test_error_is_remembered_and_not_retried(self, tmp_path, monkeypatch):
        """失败结论要缓存：否则每次请求都要白等一次磁盘超时。"""
        calls = []

        def broken(self, **kwargs):
            calls.append(1)
            raise sqlite3.OperationalError("坏了")

        monkeypatch.setattr(Database, "connect", broken)
        db = Database(tmp_path / "history.db")

        for _ in range(3):
            assert db.available is False
        assert len(calls) == 1

    def test_size_counts_wal_sidecar(self, db):
        """WAL 模式下数据可能还在 -wal 里，只算主文件会报出 0 字节。"""
        seed(db, "问题", age_days=0)

        assert db.size_bytes() > 0


class TestConnectionReuse:
    """连接复用（``Database.session`` 全程只留一条连接）。

    为什么要专门守这几条
    --------------------------------------------------------------------------
    在本机实测过：每做一次"新建连接 → 查一条 → 关掉"，稳定要 70ms——那是
    SQLite 在 Windows 上重建 WAL 共享内存文件的代价，不是查询本身。改成复用
    之后同样的七次操作从 471ms 掉到 0.1ms。

    但"连接不关"同时带来两个新的失败方式，它们都不会自己出声：
    未提交的事务会**一直攥着写锁**，之后每一次写都失败；连接被外部干掉之后
    不会自动恢复。所以这里逐条钉住。
    """

    def test_sessions_share_one_connection(self, db):
        """复用是这套改动的全部意义所在：两次 session 必须是同一条连接。"""
        with db.session() as first:
            pass
        with db.session() as second:
            pass

        assert first is second

    def test_a_failed_transaction_rolls_back_and_leaves_it_usable(self, db):
        """调用方自己抛异常时也要回滚干净。

        这比以前要紧得多：连接不关之后，漏掉的回滚会留下一个开着的事务，
        写锁被一直攥着，之后的写全部失败——而且看起来像"库突然坏了"。
        所以 ``session`` 兜的是 ``BaseException``，不只是 ``sqlite3.Error``。
        """
        with pytest.raises(ValueError):
            with db.session() as connection:
                connection.execute(
                    "INSERT INTO history (question, answer, retrieved_count, created_ts) "
                    "VALUES ('这条不该留下', '答案', 0, 0)"
                )
                raise ValueError("调用方自己炸了")

        with db.session() as connection:
            left = connection.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"]
        assert left == 0, "未提交的插入必须被回滚"

        # 还能继续写：没有留下攥着写锁的事务
        seed(db, "之后写的", age_days=0)
        assert questions(HistoryStore(db)) == ["之后写的"]

    def test_close_then_use_again(self, db):
        """``close()`` 只关连接、不留后遗症：下次访问自己重新打开。"""
        seed(db, "关之前", age_days=0)

        db.close()

        assert db.available is True
        with db.session() as connection:
            assert connection.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"] == 1

    def test_a_killed_connection_recovers_on_the_next_call(self, db):
        """连接被外部干掉（文件被删/盘符掉了）时，下一次访问要能自己长回来。

        坏连接只会让**那一次**失败——存储层的每个方法本就不抛异常，
        所以用户看到的是"这次没记上"，而不是应用崩掉。
        """
        store = HistoryStore(db)
        assert store.save("第一句", "答案") is not None

        db._conn.close()  # 白盒：模拟连接在背后被关掉

        assert store.save("第二句", "答案") is None, "坏掉的那一次应当安静地失败"
        assert store.save("第三句", "答案") is not None, "下一次应当已经自愈"

    def test_threads_writing_at_once_lose_nothing(self, db):
        """复用连接是被一把锁守着跨线程用的——并发写不能丢、也不能报 locked。"""
        import threading

        store = HistoryStore(db)
        errors: list[BaseException] = []

        def writer(tag: str) -> None:
            try:
                for index in range(5):
                    if store.save(f"{tag}-{index}", "答案") is None:
                        errors.append(RuntimeError("写入返回了 None"))
            except BaseException as exc:  # noqa: BLE001 — 线程里的异常要带回主线程断言
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(f"t{k}",)) for k in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert store.list()[0] == 20


class TestCountSince:
    """「还有多少条提问没归纳过」——「画像」页据此决定要不要自动归纳一次。

    这条规则原先住在服务层：先把最近 40 条整条读出来，再在 Python 里数时间戳。
    为得到一个整数搬运几十 KB 的回答正文，实在不划算，于是挪进了 SQL。
    规则本身没变，所以这里守住的仍是原来那几条边界。
    """

    def test_never_extracted_counts_everything(self, db):
        seed(db, "第一句", age_days=0)
        seed(db, "第二句", age_days=0)

        assert HistoryStore(db).count_since(0.0) == 2

    def test_only_newer_than_the_stamp(self, db):
        seed(db, "老的", age_days=1)
        seed(db, "新的", age_days=0)

        # > 而不是 >=：归纳恰好与某条提问落在同一秒时，那条已经被看过了
        assert HistoryStore(db).count_since(T0 - 0.5 * DAY) == 1

    def test_nothing_new(self, db):
        seed(db, "老的", age_days=5)

        assert HistoryStore(db).count_since(T0) == 0

    def test_no_records(self, db):
        assert HistoryStore(db).count_since(0.0) == 0

    def test_window_caps_how_far_back_it_looks(self, db):
        """窗口外的老记录再多也不改变结论——单次归纳只吃得下这么多素材。"""
        for index in range(5):
            seed(db, f"第{index}句", age_days=0)

        assert HistoryStore(db).count_since(0.0, window=3) == 3


class TestRetentionConfig:
    def test_default_is_half_a_month(self, monkeypatch):
        monkeypatch.delenv("RSDS_HISTORY_RETENTION_DAYS", raising=False)

        assert retention_days() == DEFAULT_RETENTION_DAYS == 15.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("RSDS_HISTORY_RETENTION_DAYS", "3")

        assert retention_days() == 3.0

    @pytest.mark.parametrize("value", ["", "abc", "-1"])
    def test_bad_values_fall_back(self, monkeypatch, value):
        """写错配置不该让保留策略变成"全都删掉"。"""
        monkeypatch.setenv("RSDS_HISTORY_RETENTION_DAYS", value)

        assert retention_days() == DEFAULT_RETENTION_DAYS

    def test_zero_means_keep_nothing(self, monkeypatch):
        monkeypatch.setenv("RSDS_HISTORY_RETENTION_DAYS", "0")

        assert retention_days() == 0.0


class TestSaveAndList:
    def test_save_returns_id_and_lists_newest_first(self, store):
        assert store.save("问题一", "答案一", model="m", retrieved_count=3) == 1
        assert store.save("问题二", "答案二") == 2

        total, records = store.list()

        assert total == 2
        assert [r.question for r in records] == ["问题二", "问题一"]
        assert records[0].model is None and records[0].llm_used is False
        assert records[1].llm_used is True and records[1].retrieved_count == 3

    def test_created_at_is_parseable(self, store):
        store.save("问题", "答案")
        record = store.list()[1][0]

        # 前端拿它 new Date(...)，解析结果必须和存的时间戳对得上
        assert abs(datetime.fromisoformat(record.created_at).timestamp() - record.created_ts) < 1

    def test_pagination(self, store):
        for index in range(5):
            store.save("问题%d" % index, "答案")

        total, page = store.list(limit=2, offset=2)

        assert total == 5
        assert [r.question for r in page] == ["问题2", "问题1"]

    def test_limit_is_capped(self, store):
        """前端传个巨大的 limit 也不该把整库读进内存。"""
        store.save("问题", "答案")

        total, page = store.list(limit=10_000)

        assert total == 1 and len(page) == 1

    def test_get_and_delete(self, store):
        record_id = store.save("问题", "答案")

        assert store.get(record_id).question == "问题"
        assert store.delete(record_id) is True
        assert store.get(record_id) is None
        assert store.delete(record_id) is False

    def test_clear(self, store):
        for index in range(3):
            store.save("问题%d" % index, "答案")

        assert store.clear() == 3
        assert store.list()[0] == 0

    def test_question_and_answer_survive_round_trip(self, store):
        """换行、引号、Markdown 都得原样存回来——回答本身是 Markdown 长文。"""
        text = "第一行\n第二行「引号」'单引号'\n- 列表"
        store.save(text, text)

        record = store.list()[1][0]

        assert record.question == text and record.answer == text


class TestAutomaticCleanup:
    """保留策略：只留最近半个月，每半个月清理一次。"""

    def test_first_use_establishes_the_cadence(self, store):
        """用一次就先把基线记下来，之后的清理按它往后推半个月。"""
        store.save("问题", "答案")

        assert store.status(now=T0)["last_purge_at"] is not None

    def test_expired_records_are_removed_when_due(self, store, db):
        seed(db, "昨天的", age_days=1)
        seed(db, "上个月的", age_days=20)

        assert store.purge(now=T0) == 1
        assert questions(store) == ["昨天的"]

    def test_cleanup_is_throttled_within_the_window(self, store, db):
        """半个月内重复调用不该反复删——那只是白写磁盘。"""
        store.purge(now=T0)
        seed(db, "上个月的", age_days=20, now=T0)

        assert store.purge(now=T0 + 1 * DAY) == 0        # 才过一天
        assert store.purge(now=T0 + 14 * DAY) == 0       # 还差一天
        assert store.purge(now=T0 + 15 * DAY) == 1       # 到点了

    def test_cleanup_runs_again_when_reopened_later(self, store, db):
        store.purge(now=T0)
        seed(db, "上个月的", age_days=20, now=T0)

        assert reopen(db).purge(now=T0 + 20 * DAY) == 1

    def test_force_skips_throttle_but_keeps_retention(self, store, db):
        """force 只是"不等了"，仍然只删过期的那部分，不是清空。"""
        store.purge(now=T0)
        seed(db, "昨天的", age_days=1, now=T0)
        seed(db, "上个月的", age_days=20, now=T0)

        assert store.purge(now=T0, force=True) == 1
        assert questions(store) == ["昨天的"]

    def test_status_reports_purge_schedule(self, store):
        status = store.status(now=T0)

        assert status["retention_days"] == DEFAULT_RETENTION_DAYS
        assert status["next_purge_at"] is not None
        assert status["available"] is True

    def test_status_triggers_cleanup(self, store, db):
        """界面打开「回响」页时会问一次状态，清理就挂在这个时机上。"""
        store.purge(now=T0)
        seed(db, "上个月的", age_days=20, now=T0)

        status = reopen(db).status(now=T0 + 20 * DAY)

        assert status["total"] == 0
        assert status["last_purge_at"] is not None


class TestUnavailableDatabase:
    """数据库坏掉时，存储层的每个方法都必须"安静地失败"。"""

    @pytest.fixture
    def broken(self, tmp_path, monkeypatch) -> HistoryStore:
        def explode(self, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(Database, "connect", explode)
        return HistoryStore(Database(tmp_path / "history.db"))

    def test_status_explains_why(self, broken):
        status = broken.status()

        assert status["available"] is False
        assert "disk I/O error" in status["error"]
        assert status["total"] == 0

    def test_reads_return_empty(self, broken):
        assert broken.list() == (0, [])
        assert broken.get(1) is None

    def test_writes_report_failure_without_raising(self, broken):
        assert broken.save("问题", "答案") is None
        assert broken.delete(1) is False
        assert broken.clear() == 0
        assert broken.purge(force=True) == 0
        assert broken.delete_many(ids=[1], topics=["t1"]) == 0

    def test_path_is_still_reported(self, broken, tmp_path):
        """不可用时也要说得清"本打算写在哪"，否则没法排查。"""
        assert broken.db_path == str(Path(tmp_path / "history.db"))


def test_store_picks_up_data_dir_from_env(tmp_path, monkeypatch):
    """数据目录由环境变量决定——打包态落在 exe 旁边，测试落在临时目录。"""
    monkeypatch.setenv("RSDS_DATA_DIR", str(tmp_path / "custom"))
    store = HistoryStore()

    assert store.db_path == str(Path(tmp_path / "custom" / "history.db"))
    assert store.available is True
    assert Path(store.db_path).is_file()


def test_singleton_is_shared():
    """同一进程里只应有一份存储：各建各的会各自持连接、各自判可用性。"""
    from server.services import history as module

    module.reset_history_store()
    try:
        assert module.get_history_store() is module.get_history_store()
        module.reset_history_store()
        assert module.get_history_store() is not None
    finally:
        module.reset_history_store()
