"""retriever 单元测试：分词、索引、检索排序与降级。"""

from server.services import retriever as retriever_module
from server.services.retriever import TFIDFRetriever, _tokenize


def build_small_retriever() -> TFIDFRetriever:
    r = TFIDFRetriever()
    r.add_document("01", "易经", "01", "乾卦", "天行健，君子以自强不息。潜龙勿用，时机未到不可轻举妄动。")
    r.add_document("02", "厚黑学", "01", "缘起", "脸皮要厚而无形，心子要黑而无色。曹操心黑，刘备脸皮厚。")
    r.add_document("08", "道德经", "01", "第一章", "道可道，非常道。上善若水，水善利万物而不争。柔弱胜刚强。")
    r.build_index()
    return r


class TestTokenize:
    def test_returns_multichar_tokens(self):
        tokens = _tokenize("天行健君子以自强不息")
        assert all(len(t) >= 2 for t in tokens)
        assert len(tokens) > 0

    def test_empty_string(self):
        assert _tokenize("") == []


class TestTFIDFRetriever:
    def test_search_finds_relevant_doc(self):
        r = build_small_retriever()
        results = r.search("自强不息 时机", top_k=3)
        assert results
        assert results[0].book_id == "01"

    def test_search_ranks_by_relevance(self):
        r = build_small_retriever()
        results = r.search("上善若水 不争", top_k=3)
        assert results
        assert results[0].book_id == "08"

    def test_source_field_format(self):
        r = build_small_retriever()
        results = r.search("自强不息", top_k=1)
        assert results
        assert results[0].source.startswith("《")
        assert "·" in results[0].source

    def test_scores_sorted_desc(self):
        r = build_small_retriever()
        results = r.search("心黑 脸皮厚", top_k=3)
        scores = [x.score for x in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limit(self):
        r = build_small_retriever()
        assert len(r.search("道", top_k=2)) <= 2

    def test_no_match_returns_empty(self):
        r = build_small_retriever()
        assert r.search("量子计算机显卡", top_k=3) == []

    def test_short_paragraphs_skipped(self):
        r = TFIDFRetriever()
        r.add_document("01", "书", "01", "章", "短")
        r.build_index()
        assert r.documents == []

    def test_empty_index_returns_empty(self):
        r = TFIDFRetriever()
        r.build_index()
        assert r.search("任何词", top_k=3) == []


class TestTableOfContents:
    """目录页整段都是篇目名，引不出任何句子，不该进索引。"""

    def test_toc_page_is_dropped(self):
        r = TFIDFRetriever()
        r.add_document(
            "15", "贞观政要", "10", "卷十",
            "议征伐第三十五 　　议安边第三十六 　　卷十 　　论行幸第三十七 "
            "　　论畋猎第三十八 　　论灾祥第三十九 　　论慎终第四十",
        )
        r.build_index()
        assert r.documents == []

    def test_passage_citing_many_chapters_is_kept(self):
        """正文里连着引用好几个章节不算目录——去掉标记后还剩一大段。"""
        r = TFIDFRetriever()
        r.add_document(
            "08", "道德经", "01", "深解",
            "第九章讲功遂身退，第十三章讲宠辱若惊，第三十三章讲自知者明，"
            "第六十四章讲千里之行始于足下，第六十六章讲善下不争，"
            "这几章合起来是老子对“退”的完整论证：退不是放弃，而是换一种方式领先。",
        )
        r.build_index()
        assert len(r.documents) == 1


class TestSearchConsistency:
    """检索内层循环改过一轮（平行列表替代生成器 + dict.get）。

    目标是快，**前提是结果一个都不能变**——同分时的先后顺序也一样。
    所以这里把"分数降序、同分按下标升序"钉死，改动若打破它会立刻红。
    """

    def test_ties_break_by_document_order(self):
        """两篇内容完全相同的文档得分必然相同，此时必须按加入顺序返回。"""
        r = TFIDFRetriever()
        body = "上善若水，水善利万物而不争，处众人之所恶，故几于道。"
        r.add_document("01", "甲书", "01", "章", body)
        r.add_document("02", "乙书", "01", "章", body)
        r.build_index()
        results = r.search("上善若水不争", top_k=2)
        assert len(results) == 2
        assert results[0].score == results[1].score
        assert [x.book_id for x in results] == ["01", "02"]

    def test_book_weight_scales_score(self):
        """``book_weights`` 只影响分数，不该影响"能不能召回"。"""
        r = build_small_retriever()
        plain = r.search("上善若水", top_k=3)
        weighted = r.search("上善若水", top_k=3, book_weights={"08": 0.5})
        assert [x.book_id for x in plain] == [x.book_id for x in weighted]
        assert weighted[0].score < plain[0].score

    def test_result_count_never_exceeds_top_k(self):
        """优化后只构造 top_k 条结果，别在截断这一步写错边界。"""
        r = build_small_retriever()
        for k in (1, 2, 3):
            assert len(r.search("道 水 心 厚", top_k=k)) <= k


class TestIndexProgress:
    """建索引进度：给启动画面的，不能反过来影响构建结果。"""

    def test_progress_starts_at_zero(self):
        retriever_module._report_progress(0.0, "准备中")
        snap = retriever_module.index_progress()
        assert snap["ratio"] == 0.0

    def test_ratio_is_clamped(self):
        """越界值要被夹回 [0, 1]——进度条宽度直接拿它乘 100，越界会画出格。"""
        retriever_module._report_progress(3.5, "过了")
        assert retriever_module.index_progress()["ratio"] == 1.0
        retriever_module._report_progress(-2.0, "负了")
        assert retriever_module.index_progress()["ratio"] == 0.0

    def test_progress_does_not_break_build(self):
        """构建流程照常产出索引——加了进度上报不该改变任何构建语义。"""
        loader = _StubLoader()
        retriever_module.reset_retriever()
        built = retriever_module.build_retriever_from_loader(loader)
        assert built.documents
        snap = retriever_module.index_progress()
        assert snap["ratio"] == 1.0
        assert snap["stage"] == "就绪"


class _StubChapter:
    def __init__(self, chapter_id, title, content):
        self.chapter_id = chapter_id
        self.title = title
        self.content = content


class _StubBook:
    """最小的书对象：构建流程只用到这几个字段。"""

    def __init__(self, book_id, title, chapters, source_file=None):
        self.book_id = book_id
        self.title = title
        self.chapters = chapters
        self.source_file = source_file


class _StubLoader:
    def __init__(self):
        self._books = [
            _StubBook("08", "道德经", [
                _StubChapter("01", "第一章", "道可道非常道，名可名非常名。无名天地之始，有名万物之母。"),
            ]),
            _StubBook("09", "论语", [
                _StubChapter("01", "学而", "学而时习之，不亦说乎。有朋自远方来，不亦乐乎。"),
            ]),
        ]

    def get_books(self):
        return list(self._books)

    def get_source_text(self, book_id):
        return None
