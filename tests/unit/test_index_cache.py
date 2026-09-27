"""落盘索引缓存：往返一致性、指纹、失效边界，以及"坏掉也不能影响启动"。

最要紧的一条是 **往返逐位一致**。缓存不是"差不多就行"的东西：它一旦对不上，
检索结果就会错，而界面上**没有任何提示**——回答里引的段落与点开的原文对不上，
排查时第一个怀疑的绝不会是"缓存"。所以这里的比对是逐字段、连分数都不放过。

用一个只有一本书的假加载器测逻辑（真语料那份往返见文件末尾的
``TestRoundtripOnRealCorpus``）。
"""

import os

import pytest

from server import paths
from server.services import index_cache, retriever as retriever_module
from server.services.content_loader import Book, Chapter


# ── 最小可用的加载器 ────────────────────────────────────────────────────

DEFAULT_BODY = "天行健，君子以自强不息。潜龙勿用，时机未到不可轻举妄动。"
DEFAULT_SOURCE = "道可道，非常道。上善若水，水善利万物而不争。"


class _FakeLoader:
    """够 ``corpus_fingerprint`` 与 ``build_retriever_from_loader`` 用就行。

    刻意复用真的 ``Book`` / ``Chapter`` 数据类，而不是自己捏一个
    ``SimpleNamespace``：字段名一旦变了，这里会跟着报错，而不是悄悄少哈希一段。
    """

    def __init__(
        self,
        *,
        body: str = DEFAULT_BODY,
        source: str | None = DEFAULT_SOURCE,
        title: str = "测试书",
        book_id: str = "99",
    ) -> None:
        self._book = Book(
            book_id=book_id,
            title=title,
            author="佚名",
            category="测试",
            source_file="fake.txt" if source is not None else None,
            chapters=[Chapter(chapter_id="01", title="第一章", content=body, book_id=book_id)],
        )
        self._source = source

    def get_books(self) -> list[Book]:
        return [self._book]

    def get_source_text(self, book_id: str) -> str | None:
        return self._source if book_id == self._book.book_id else None


def _snapshot(retriever, query: str, top_k: int = 5):
    """检索结果的可比对快照。分数也进去——差一位就该被抓住。"""
    return [
        (r.book_id, r.chapter_id, r.content, r.score, r.kind, r.offset)
        for r in retriever.search(query, top_k)
    ]


@pytest.fixture
def cache_on(monkeypatch, tmp_path):
    """打开缓存，并把数据目录指到本用例自己的临时目录。

    ``isolate_history`` 本来就把 ``RSDS_DATA_DIR`` 指向 ``tmp_path`` 了，
    这里再指一个子目录只是为了让"缓存文件在哪"一目了然；
    真正要做的是把总开关打开（``conftest.py`` 默认关掉它）。
    """
    monkeypatch.setenv(index_cache.ENV_VAR, "1")
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "cache-data"))
    return index_cache.cache_file()


def _roundtrip(loader):
    """写一份、再读回来。返回 (原来的, 读回来的)。"""
    built = retriever_module.build_retriever_from_loader(loader)
    assert retriever_module.persist_to_cache(built, loader) is True
    restored = retriever_module.restore_from_cache(loader)
    assert restored is not None, "刚写下的缓存应该读得回来"
    return built, restored


# ── 指纹 ────────────────────────────────────────────────────────────────


class TestFingerprint:
    def test_同一份语料指纹稳定(self):
        loader = _FakeLoader()
        first = index_cache.corpus_fingerprint(loader, retriever_module.INDEX_LOGIC)
        second = index_cache.corpus_fingerprint(loader, retriever_module.INDEX_LOGIC)
        assert first == second
        assert len(first) >= 32

    def test_正文改了指纹就变(self):
        # 关键在"字数不变也算改"——改错别字正是最容易被 size 判据放过的那种。
        base = index_cache.corpus_fingerprint(_FakeLoader(), retriever_module.INDEX_LOGIC)
        edited = index_cache.corpus_fingerprint(
            _FakeLoader(body=DEFAULT_BODY.replace("自强不息", "自强不惜")),
            retriever_module.INDEX_LOGIC,
        )
        assert base != edited

    def test_原典改了指纹就变(self):
        base = index_cache.corpus_fingerprint(_FakeLoader(), retriever_module.INDEX_LOGIC)
        edited = index_cache.corpus_fingerprint(
            _FakeLoader(source=DEFAULT_SOURCE + "多了一句。"), retriever_module.INDEX_LOGIC
        )
        assert base != edited

    def test_索引逻辑签名变了指纹就变(self):
        # 切段规则、停用词、分词器都不在语料里，只能靠这颗签名区分。
        loader = _FakeLoader()
        assert index_cache.corpus_fingerprint(loader, "retrieval-v1:jieba") != (
            index_cache.corpus_fingerprint(loader, "retrieval-v2:jieba")
        )

    def test_书换了指纹就变(self):
        base = index_cache.corpus_fingerprint(_FakeLoader(), retriever_module.INDEX_LOGIC)
        other = index_cache.corpus_fingerprint(
            _FakeLoader(title="另一本", book_id="98"), retriever_module.INDEX_LOGIC
        )
        assert base != other


# ── 往返 ────────────────────────────────────────────────────────────────


class TestRoundtrip:
    def test_检索结果逐位相同(self, cache_on):
        built, restored = _roundtrip(_FakeLoader())
        for query in ("自强不息 时机", "上善若水 不争", "道 天", "完全不搭边的问句"):
            assert _snapshot(restored, query) == _snapshot(built, query), query

    def test_索引规模与来源覆盖一并带回来(self, cache_on):
        built, restored = _roundtrip(_FakeLoader())
        assert len(restored.documents) == len(built.documents)
        assert restored.source_coverage == built.source_coverage

    def test_倒排表与模长是重建的(self, cache_on):
        """它们刻意不进缓存（六十万个浮点太占地方），所以读回来必须补建。"""
        built, restored = _roundtrip(_FakeLoader())
        assert restored._postings, "读回来必须重建倒排表，否则检索会全空"
        assert len(restored._doc_norms) == len(restored.documents)

    def test_读回来还能继续检索(self, cache_on):
        _, restored = _roundtrip(_FakeLoader())
        assert restored.search("自强不息", top_k=3)

    def test_读回来的词频是Counter而不是普通字典(self, cache_on):
        """JSON 里没有 Counter；转不回来，`df[term] += 1` 那条路就会静默失准。"""
        from collections import Counter

        _, restored = _roundtrip(_FakeLoader())
        assert isinstance(restored.df, Counter)
        assert all(isinstance(row, Counter) for row in restored.tf)


# ── 失效：任何一条对不上都当没有缓存 ────────────────────────────────────


class TestInvalidation:
    def test_指纹对不上(self, cache_on):
        _roundtrip(_FakeLoader())
        assert index_cache.read(cache_on, "对不上的指纹") is None

    def test_换了一本书就当没有缓存(self, cache_on):
        """换语料之后不该再用旧索引——这正是要防的"悄悄用错"。"""
        _roundtrip(_FakeLoader())
        assert retriever_module.restore_from_cache(_FakeLoader(body="完全不同的一段话。")) is None

    def test_载荷版本对不上(self, cache_on, monkeypatch):
        built = retriever_module.build_retriever_from_loader(_FakeLoader())
        assert index_cache.write(
            cache_on,
            {
                "version": index_cache.PAYLOAD_VERSION + 1,
                "fingerprint": index_cache.corpus_fingerprint(
                    _FakeLoader(), retriever_module.INDEX_LOGIC
                ),
                "documents": built.documents,
                "tf": built.tf,
                "df": built.df,
                "source_coverage": built.source_coverage,
            },
        )
        assert retriever_module.restore_from_cache(_FakeLoader()) is None

    def test_载荷缺字段当作没有缓存(self, cache_on):
        """手工造一份"版本和指纹都对、但内容不全"的文件——不能让它带着半截数据过关。"""
        assert index_cache.write(
            cache_on,
            {
                "version": index_cache.PAYLOAD_VERSION,
                "fingerprint": index_cache.corpus_fingerprint(
                    _FakeLoader(), retriever_module.INDEX_LOGIC
                ),
                "source_coverage": {"indexed": [], "skipped": []},
            },
        )
        assert retriever_module.restore_from_cache(_FakeLoader()) is None

    def test_文件不存在(self, cache_on):
        assert not cache_on.exists()
        assert retriever_module.restore_from_cache(_FakeLoader()) is None

    def test_文件被截断(self, cache_on):
        _roundtrip(_FakeLoader())
        raw = cache_on.read_bytes()
        cache_on.write_bytes(raw[: len(raw) // 2])
        assert retriever_module.restore_from_cache(_FakeLoader()) is None

    def test_文件是垃圾(self, cache_on):
        _roundtrip(_FakeLoader())
        cache_on.write_bytes(b"this is not gzip at all")
        assert retriever_module.restore_from_cache(_FakeLoader()) is None

    def test_文件是合法JSON但不是我们要的形状(self, cache_on):
        import gzip

        cache_on.write_bytes(gzip.compress(b"[1, 2, 3]"))
        assert retriever_module.restore_from_cache(_FakeLoader()) is None


# ── 健壮性：坏掉也不能把事情弄砸 ────────────────────────────────────────


class TestRobustness:
    def test_开关关掉后不读也不写(self, monkeypatch, tmp_path):
        monkeypatch.setenv(index_cache.ENV_VAR, "0")
        assert index_cache.enabled() is False
        target = tmp_path / "never.json.gz"
        assert index_cache.write(target, {"version": 1}) is False
        assert index_cache.read(target, "x") is None
        assert not target.exists()

    def test_目录不可写时写入返回False而不是抛异常(self, tmp_path, monkeypatch):
        monkeypatch.setenv(index_cache.ENV_VAR, "1")
        # 用一个不可能存在、也不可能建出来的路径（盘符不存在）
        impossible = tmp_path / "Z:" / "nope" / "index.json.gz"
        assert index_cache.write(impossible, {"version": 1}) is False

    def test_写入失败不留临时文件(self, tmp_path, monkeypatch):
        monkeypatch.setenv(index_cache.ENV_VAR, "1")
        impossible = tmp_path / "Z:" / "nope" / "index.json.gz"
        index_cache.write(impossible, {"version": 1})
        assert list(tmp_path.glob("*.tmp")) == []

    def test_没设环境变量时默认是启用(self, monkeypatch):
        monkeypatch.delenv(index_cache.ENV_VAR, raising=False)
        assert index_cache.enabled() is True

    def test_开关认常见的几个假值(self, monkeypatch):
        for value in ("0", "false", "False", "no", "off", " OFF "):
            monkeypatch.setenv(index_cache.ENV_VAR, value)
            assert index_cache.enabled() is False, value
        for value in ("1", "true", "yes", "on"):
            monkeypatch.setenv(index_cache.ENV_VAR, value)
            assert index_cache.enabled() is True, value


# ── 接进 ensure_retriever ───────────────────────────────────────────────


class TestEnsureRetrieverUsesCache:
    @pytest.fixture(autouse=True)
    def _clean_singleton(self):
        """``ensure_retriever`` 会把这份假索引装进**全局单例**，用完必须清掉。

        不清理的话，与 ``tests/integration`` 一起跑时后者的检索会全线召回为空
        （同一个坑见 ``test_retriever.py`` 顶部的说明）。
        """
        retriever_module.reset_retriever()
        yield
        retriever_module.reset_retriever()

    def test_第一次建完就落盘_第二次直接读回(self, cache_on):
        loader = _FakeLoader()

        first = retriever_module.ensure_retriever(loader)
        assert first.documents
        assert cache_on.is_file(), "建完应该把缓存写下来"

        retriever_module.reset_retriever()
        second = retriever_module.ensure_retriever(loader)
        assert second is not first, "第二次应该是从缓存恢复出来的另一份"
        assert _snapshot(second, "自强不息 时机") == _snapshot(first, "自强不息 时机")

    def test_语料变了就重建而不是拿旧的顶(self, cache_on):
        first = retriever_module.ensure_retriever(_FakeLoader())
        retriever_module.reset_retriever()

        changed = _FakeLoader(body="换了一整段完全不同的正文，一个字都不一样。")
        second = retriever_module.ensure_retriever(changed)
        assert second.documents
        assert _snapshot(second, "自强不息 时机") != _snapshot(first, "自强不息 时机")

    def test_缓存关掉时照样能建起来(self, tmp_path, monkeypatch):
        # 刻意不用 `cache_on`：它会把开关打开。这里单独摆一份环境。
        monkeypatch.setenv(index_cache.ENV_VAR, "0")
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "cache-data"))
        retriever = retriever_module.ensure_retriever(_FakeLoader())
        assert retriever.documents
        assert not index_cache.cache_file().exists()

    def test_单例已有索引时不碰缓存(self, cache_on):
        """幂等：已经建好了就直接返回，不必去读文件。"""
        first = retriever_module.ensure_retriever(_FakeLoader())
        assert retriever_module.ensure_retriever(_FakeLoader()) is first


# ── 真语料上的往返 ──────────────────────────────────────────────────────

#: 这组断言用的查询。刻意覆盖"长问句""短语""几乎查不到"三类。
_PROBES = (
    "我最近很焦虑，晚上睡不着",
    "如何面对失败和挫折",
    "怎样跟人相处才不吃亏",
    "无为而无不为",
)


@pytest.fixture(scope="session")
def real_roundtrip(loader, tmp_path_factory):
    """在真语料上做一次「写 → 读」，把两边的结果都留下给用例比对。

    约 9 秒，但只此一次（单是建索引就要 7 秒多）。用假加载器测不出规模上的问题，
    而"8534 个检索单元、8.4MB 载荷"与"一个检索单元、几 KB"毕竟是两回事——
    这条要保的是**真语料上也逐位相同**。

    这里直接操作环境变量而不是用 ``monkeypatch``：``monkeypatch`` 是 function 级
    夹具，配不上 session 级的东西。**用完立刻还原**（在 ``yield`` 之前），别让
    后面几十个用例在"数据目录指向一个 session 临时目录"的状态下跑——那会让它们
    的库都落进同一个地方，互相看见对方写的数据。
    """
    saved = {name: os.environ.get(name) for name in (paths.DATA_DIR_ENV_VAR, index_cache.ENV_VAR)}
    try:
        os.environ[paths.DATA_DIR_ENV_VAR] = str(tmp_path_factory.mktemp("index-cache"))
        os.environ[index_cache.ENV_VAR] = "1"
        built = retriever_module.build_retriever_from_loader(loader)
        before = [_snapshot(built, q) for q in _PROBES]
        written = retriever_module.persist_to_cache(built, loader)
        restored = retriever_module.restore_from_cache(loader)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    yield built, restored, before, written


class TestRoundtripOnRealCorpus:
    def test_写成功(self, real_roundtrip):
        _, _, _, written = real_roundtrip
        assert written is True

    def test_读得回来(self, real_roundtrip):
        _, restored, _, _ = real_roundtrip
        assert restored is not None

    def test_规模一致(self, real_roundtrip):
        built, restored, _, _ = real_roundtrip
        assert len(restored.documents) == len(built.documents)
        # 存的是全量语料，规模掉了就说明写/读截断了
        assert len(built.documents) > 1000

    def test_真语料上检索结果也逐位相同(self, real_roundtrip):
        _, restored, before, _ = real_roundtrip
        for query, want in zip(_PROBES, before):
            assert _snapshot(restored, query) == want, query

    def test_原典入索引的情况一致(self, real_roundtrip):
        built, restored, _, _ = real_roundtrip
        assert restored.source_coverage == built.source_coverage
        assert built.source_coverage["indexed"], "真语料里应该有原典入了索引"
