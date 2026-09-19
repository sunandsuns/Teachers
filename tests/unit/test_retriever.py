"""retriever 单元测试：分词、索引、检索排序与降级。"""

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
