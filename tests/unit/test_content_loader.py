"""content_loader 单元测试：加载、章节拆分、特殊书目处理。"""

from server.services.content_loader import (
    BOOK_REGISTRY,
    ContentLoader,
    _split_markdown_chapters,
    get_loader,
)


class TestSplitMarkdownChapters:
    def test_no_heading_returns_single_chapter(self):
        chapters = _split_markdown_chapters("没有标题的普通文本段落。", "99")
        assert len(chapters) == 1
        assert chapters[0].title == "全文"
        assert chapters[0].chapter_id == "01"

    def test_splits_on_h2(self):
        content = "# 书名\n\n引言\n\n## 第一章 甲\n\n内容A\n\n## 第二章 乙\n\n内容B"
        chapters = _split_markdown_chapters(content, "99")
        # 导言(00) + 两章
        assert [c.chapter_id for c in chapters] == ["00", "01", "02"]
        assert chapters[0].title == "导言"
        assert chapters[1].title == "第一章 甲"
        assert "内容A" in chapters[1].content
        assert chapters[2].title == "第二章 乙"

    def test_chapters_carry_book_id(self):
        chapters = _split_markdown_chapters("## A\n\nx", "07")
        assert all(c.book_id == "07" for c in chapters)


class TestContentLoader:
    def test_loads_registry_books(self):
        loader = ContentLoader()
        loader.load()
        assert set(loader.books.keys()) == {spec.book_id for spec in BOOK_REGISTRY}
        assert len(loader.books) == len(BOOK_REGISTRY)

    def test_mao_book_has_many_chapters(self):
        loader = ContentLoader()
        loader.load()
        # 毛选 src/ 下有 231 篇（去掉索引文件）
        mao = loader.get_book("05")
        assert mao is not None
        assert len(mao.chapters) >= 200

    def test_mao_chapter_ids_sorted_numeric(self):
        loader = ContentLoader()
        loader.load()
        chapters = loader.get_chapters("05")
        ids = [c.chapter_id for c in chapters]
        assert ids == sorted(ids)

    def test_wang_book_loaded(self):
        loader = ContentLoader()
        loader.load()
        wang = loader.get_book("06")
        assert wang is not None
        assert len(wang.chapters) >= 1
        assert wang.chapters[0].title == "王阳明心学概览"

    def test_get_chapter_roundtrip(self):
        loader = ContentLoader()
        loader.load()
        chapters = loader.get_chapters("01")
        first = chapters[0]
        got = loader.get_chapter("01", first.chapter_id)
        assert got is not None
        assert got.title == first.title

    def test_get_chapter_unknown_returns_none(self):
        loader = ContentLoader()
        loader.load()
        assert loader.get_chapter("01", "not-exist") is None
        assert loader.get_chapter("99", "01") is None

    def test_source_text_available_for_txt_books(self):
        """声明了 source 的书目，原典必须真的读得出来；未声明的必须为 None。"""
        loader = ContentLoader()
        loader.load()
        for spec in BOOK_REGISTRY:
            book = loader.get_book(spec.book_id)
            text = loader.get_source_text(spec.book_id)
            if spec.source is not None and book.source_file is not None:
                assert text, f"{spec.title} 应有原典文本"
            else:
                assert text is None, f"{spec.title} 未声明原典，应返回 None"

    def test_get_all_text_contains_known_content(self):
        loader = ContentLoader()
        loader.load()
        text = loader.get_all_text()
        assert "厚黑" in text  # 厚黑学笔记

    def test_load_is_idempotent(self):
        loader = ContentLoader()
        loader.load()
        n = len(loader.books)
        loader.load()
        assert len(loader.books) == n

    def test_get_loader_returns_singleton(self):
        assert get_loader() is get_loader()
