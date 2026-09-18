"""话题（会话）维度：把追问聚成一张卡片，而不是散成一长条列表。

这一层锁住的是存储规则：怎么归并、标题取哪一条、老记录怎么办。

时间戳一律相对"现在"取。用 100、200 这种绝对值的话，第一次写入触发的机会式
清理会顺手把它们当过期数据删掉（保留期是半个月），测试就会莫名其妙地空。
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from server.services.db import Database
from server.services.history import SOLO_PREFIX, HistoryStore

#: 所有测试时间戳的基准点
BASE_TS = time.time()


@pytest.fixture
def store(tmp_path):
    return HistoryStore(Database(tmp_path / "history.db"))


def add(store, question, *, answer="答", topic=None, offset=0.0):
    """存一条。``offset`` 是与基准点的秒差，用来排出先后。"""
    return store.save(
        question,
        answer,
        model="test-model",
        retrieved_count=1,
        conversation_id=topic,
        now=BASE_TS + offset,
    )


class TestTopicGrouping:
    def test_follow_ups_share_one_topic(self, store):
        add(store, "怎么坚持？", topic="t1", offset=0)
        add(store, "那具体呢？", topic="t1", offset=10)
        add(store, "还有别的吗？", topic="t1", offset=20)

        total, topics = store.list_topics()
        assert total == 1
        assert topics[0].question_count == 3

    def test_title_is_the_first_question(self, store):
        add(store, "怎么坚持？", topic="t1", offset=0)
        add(store, "那具体呢？", topic="t1", offset=10)

        _, topics = store.list_topics()
        assert topics[0].title == "怎么坚持？"
        assert topics[0].latest_question == "那具体呢？"

    def test_separate_topics_stay_separate(self, store):
        add(store, "话题甲", topic="t1", offset=0)
        add(store, "话题乙", topic="t2", offset=10)
        assert store.list_topics()[0] == 2

    def test_topics_are_ordered_by_latest_activity(self, store):
        """旧话题刚被追问过，就该排到前面——列表按"最近聊过"排才符合直觉。"""
        add(store, "老话题", topic="old", offset=0)
        add(store, "新话题", topic="new", offset=100)
        add(store, "老话题（又聊起）", topic="old", offset=200)

        _, topics = store.list_topics()
        assert [t.id for t in topics] == ["old", "new"]

    def test_records_without_a_topic_get_their_own(self, store):
        """升级前的老记录没有会话 id，各算一个话题——硬凑成一组等于编造关系。"""
        first = add(store, "旧问题一", offset=0)
        add(store, "旧问题二", offset=10)

        total, topics = store.list_topics()
        assert total == 2
        assert f"{SOLO_PREFIX}{first}" in [t.id for t in topics]

    def test_preview_uses_the_latest_answer(self, store):
        add(store, "问一", answer="答一", topic="t1", offset=0)
        add(store, "问二", answer="答二", topic="t1", offset=10)

        _, topics = store.list_topics()
        assert topics[0].latest_answer == "答二"

    def test_empty_store_has_no_topics(self, store):
        assert store.list_topics() == (0, [])


class TestTopicRecords:
    def test_records_are_chronological(self, store):
        """话题内要按时间正序——顺着读才是一段对话。"""
        add(store, "第一问", topic="t1", offset=200)
        add(store, "第二问", topic="t1", offset=0)
        add(store, "第三问", topic="t1", offset=100)

        total, records = store.list_by_topic("t1")
        assert total == 3
        assert [r.question for r in records] == ["第二问", "第三问", "第一问"]

    def test_only_that_topics_records_come_back(self, store):
        add(store, "属于 t1", topic="t1", offset=0)
        add(store, "属于 t2", topic="t2", offset=10)

        _, records = store.list_by_topic("t1")
        assert [r.question for r in records] == ["属于 t1"]

    def test_solo_id_returns_that_one_record(self, store):
        record_id = add(store, "孤零零的一条", offset=0)
        total, records = store.list_by_topic(f"{SOLO_PREFIX}{record_id}")
        assert total == 1
        assert records[0].question == "孤零零的一条"

    def test_record_carries_its_topic(self, store):
        add(store, "问", topic="t1", offset=0)
        _, records = store.list_by_topic("t1")
        assert records[0].conversation_id == "t1"

    def test_unrecognized_ids_fail_quietly(self, store):
        """认不出的 id 不该把接口带崩，按"没有这条"处理即可。"""
        assert store.list_by_topic("") == (0, [])
        assert store.list_by_topic(f"{SOLO_PREFIX}abc") == (0, [])
        assert store.delete_topic("") == 0
        assert store.delete_topic(f"{SOLO_PREFIX}abc") == 0


class TestDeleteTopic:
    def test_removes_every_record_of_that_topic(self, store):
        add(store, "一", topic="t1", offset=0)
        add(store, "二", topic="t1", offset=10)
        add(store, "别的", topic="t2", offset=20)

        assert store.delete_topic("t1") == 2
        total, topics = store.list_topics()
        assert total == 1
        assert topics[0].id == "t2"


class TestMigration:
    """升级时用户是把新包解压到旧目录上，库会接着用——不能假设他会删库重来。"""

    def _make_legacy_db(self, path) -> None:
        connection = sqlite3.connect(str(path))
        connection.executescript(
            "CREATE TABLE history ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  question TEXT NOT NULL,"
            "  answer TEXT NOT NULL,"
            "  model TEXT,"
            "  retrieved_count INTEGER NOT NULL DEFAULT 0,"
            "  created_ts REAL NOT NULL);"
        )
        connection.execute(
            "INSERT INTO history (question, answer, model, retrieved_count, created_ts) "
            "VALUES ('旧问题', '旧回答', NULL, 0, ?)",
            (BASE_TS,),
        )
        connection.commit()
        connection.close()

    def test_legacy_records_still_readable(self, tmp_path):
        path = tmp_path / "old.db"
        self._make_legacy_db(path)

        store = HistoryStore(Database(path))
        total, topics = store.list_topics()
        assert total == 1
        assert topics[0].title == "旧问题"

    def test_new_column_is_added_and_usable(self, tmp_path):
        """补完列之后，新记录能正常按话题归类。"""
        path = tmp_path / "old.db"
        self._make_legacy_db(path)

        store = HistoryStore(Database(path))
        store.save("新问题", "新回答", conversation_id="t1", now=BASE_TS + 10)

        assert store.list_topics()[0] == 2
        assert store.list_by_topic("t1")[1][0].question == "新问题"

    def test_migration_is_idempotent(self, tmp_path):
        """每次打开都会跑一遍补列，跑第二遍不能报错。"""
        path = tmp_path / "old.db"
        self._make_legacy_db(path)

        for _ in range(3):
            store = HistoryStore(Database(path))
            assert store.available is True
        assert store.list_topics()[0] == 1
