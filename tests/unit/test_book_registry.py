"""书目注册表的数据一致性测试。

这一层测试的价值：**把"注册表声明"与"仓库实际内容"对齐**。
重构前 07—12 号书在注册表里存在、但在 books/ 与理解笔记/ 下都为空，
前端只能显示"暂无内容"——这类"声明与事实漂移"正是本文件要拦住的问题。
"""

import dataclasses
from pathlib import Path

import pytest

from server.services.content_loader import (
    BOOK_REGISTRY,
    NOTES,
    PROJECT_ROOT,
    BookSpec,
    ContentLoader,
)


@pytest.fixture(scope="module")
def loader():
    """本模块专用的加载器（module 级，避免重复读盘）。"""
    instance = ContentLoader()
    instance.load()
    return instance


class TestRegistryShape:
    def test_book_ids_are_unique(self):
        ids = [spec.book_id for spec in BOOK_REGISTRY]
        assert len(ids) == len(set(ids)), "book_id 必须唯一"

    def test_book_ids_are_two_digit_numeric(self):
        for spec in BOOK_REGISTRY:
            assert spec.book_id.isdigit() and len(spec.book_id) == 2, spec.book_id

    def test_core_metadata_is_filled(self):
        for spec in BOOK_REGISTRY:
            assert spec.title.strip(), spec.book_id
            assert spec.author.strip(), spec.book_id
            assert spec.category.strip(), spec.book_id

    def test_specs_are_immutable(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            BOOK_REGISTRY[0].title = "改名"  # type: ignore[misc]


class TestRegistryMatchesRepository:
    """注册表不得声明仓库里不存在的东西。"""

    def test_every_book_actually_has_chapters(self, loader):
        """每本书都必须真的能读到章节，不能只是登记在册。"""
        empty = [spec.title for spec in BOOK_REGISTRY if not loader.get_chapters(spec.book_id)]
        assert empty == [], f"以下书目已注册但无任何内容：{empty}"

    def test_declared_source_files_exist(self):
        """声明了 source 的书目，books/ 下必须真有这个文件。"""
        books_dir = PROJECT_ROOT / "books"
        missing = [
            spec.source
            for spec in BOOK_REGISTRY
            if spec.source is not None and not (books_dir / spec.source).is_file()
        ]
        assert missing == [], f"以下原典声明了但文件不存在：{missing}"

    def test_notes_strategy_books_resolve_a_notes_file(self, loader):
        """NOTES 策略的书目，其笔记文件必须被成功定位。"""
        for spec in BOOK_REGISTRY:
            if spec.loader != NOTES:
                continue
            book = loader.get_book(spec.book_id)
            assert book is not None
            assert book.notes_file, f"{spec.title} 未定位到笔记文件"
            assert Path(book.notes_file).is_file()

    def test_filled_books_have_readable_source(self, loader):
        """07–15 这批补齐的书，原典必须**真的读得出来**，而不只是文件存在。

        文件存在但内容为空、或编码损坏，是"看起来补上了其实没补"的典型陷阱。
        """
        for book_id in (f"{i:02d}" for i in range(7, 16)):
            book = loader.get_book(book_id)
            assert book is not None, book_id
            assert book.source_file, f"{book.title} 未登记原典"
            text = loader.get_source_text(book_id)
            assert text and len(text) > 1000, f"{book.title} 原典过短或读取失败"

    def test_source_length_matches_text(self, loader):
        for spec in BOOK_REGISTRY:
            text = loader.get_source_text(spec.book_id)
            expected = len(text) if text else 0
            assert loader.get_source_length(spec.book_id) == expected

    def test_every_book_spec_has_known_loader(self):
        from server.services.content_loader import COLLECTION, MDBOOK

        known = {NOTES, MDBOOK, COLLECTION}
        assert {spec.loader for spec in BOOK_REGISTRY} <= known


class TestCategories:
    def test_categories_are_deduplicated_in_order(self, loader):
        categories = loader.categories()
        assert len(categories) == len(set(categories))

    def test_history_category_present(self, loader):
        assert "历史文献" in loader.categories()

    def test_history_category_has_multiple_books(self, loader):
        history = [b for b in loader.get_books() if b.category == "历史文献"]
        assert len(history) >= 3


class TestBookSpecOptions:
    def test_opt_returns_single_value(self):
        spec = BookSpec("99", "t", "a", "c", options={"dir": "X", "src": "src"})
        assert spec.opt("dir") == "X"
        assert spec.opt("src") == "src"

    def test_opt_returns_default_when_absent(self):
        spec = BookSpec("99", "t", "a", "c")
        assert spec.opt("dir") is None
        assert spec.opt("src", "fallback") == "fallback"

    def test_opt_refuses_multi_value(self):
        """声明成多值的参数用 opt() 读会得到 None，避免静默的类型混淆。"""
        spec = BookSpec("99", "t", "a", "c", options={"dirs": ("a", "b")})
        assert spec.opt("dirs") is None

    def test_opt_list_wraps_single_value(self):
        spec = BookSpec("99", "t", "a", "c", options={"dirs": "only"})
        assert spec.opt_list("dirs") == ("only",)

    def test_opt_list_reads_tuple(self):
        spec = BookSpec("99", "t", "a", "c", options={"dirs": ("a", "b")})
        assert spec.opt_list("dirs") == ("a", "b")

    def test_opt_list_absent_returns_empty(self):
        assert BookSpec("99", "t", "a", "c").opt_list("dirs") == ()
