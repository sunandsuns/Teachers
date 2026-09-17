"""三种加载策略的行为测试。

用 `tmp_path` 构造"迷你仓库"，从而在不依赖真实语料的前提下验证：
- 策略分派是否正确（不存在的策略要报错，而不是静默返回空）
- 各策略的参数语义（notes / dir / src / entry / include_dirs）
- 目录扫描的排序、过滤与容错（坏文件不能炸掉整库加载）
"""

from pathlib import Path

import pytest

from server.services.content_loader import (
    BOOKS_DIRNAME,
    COLLECTION,
    MDBOOK,
    NOTES,
    NOTES_DIRNAME,
    BookSpec,
    ContentLoader,
)


@pytest.fixture()
def mini_repo(tmp_path: Path) -> Path:
    """最小可用的项目骨架：一个 notes 目录、一个 books 目录、两类子工程。"""
    (tmp_path / NOTES_DIRNAME).mkdir()
    (tmp_path / BOOKS_DIRNAME).mkdir()

    # ── NOTES 策略的目标 ──
    (tmp_path / NOTES_DIRNAME / "01-测试经.md").write_text(
        "# 测试经\n\n引言段落。\n\n## 第一义\n\n内容甲\n\n## 第二义\n\n内容乙\n",
        encoding="utf-8",
    )
    (tmp_path / BOOKS_DIRNAME / "测试经.txt").write_text("原典正文。" * 30, encoding="utf-8")

    # ── MDBOOK 策略的目标 ──
    src = tmp_path / "MiniBook" / "src"
    src.mkdir(parents=True)
    (src / "000-开篇.md").write_text("开篇正文", encoding="utf-8")
    (src / "001-次篇.md").write_text("次篇正文", encoding="utf-8")
    (src / "SUMMARY.md").write_text("- [开篇](000-开篇.md)", encoding="utf-8")
    (src / "README.md").write_text("不该被收录", encoding="utf-8")
    (src / "note.md").write_text("无编号文件", encoding="utf-8")

    # ── COLLECTION 策略的目标 ──
    # 用 ASCII 文件名，使"按文件名排序"这一约定可被稳定断言
    # （中文文件名按 Unicode 码点排序，顺序不直观）
    coll = tmp_path / "MiniColl"
    (coll / "诗词").mkdir(parents=True)
    (coll / "README.md").write_text("概览正文", encoding="utf-8")
    (coll / "诗词" / "p1.md").write_text("甲诗正文", encoding="utf-8")
    (coll / "诗词" / "p2.md").write_text("乙诗正文", encoding="utf-8")

    return tmp_path


def _load(repo: Path, spec: BookSpec) -> ContentLoader:
    loader = ContentLoader(root=repo, registry=(spec,))
    loader.load()
    return loader


class TestNotesStrategy:
    def test_splits_by_h2(self, mini_repo: Path):
        spec = BookSpec("01", "测试经", "某人", "哲学", NOTES, source="测试经.txt")
        loader = _load(mini_repo, spec)
        chapters = loader.get_chapters("01")
        # 导言(00) + 两章
        assert [c.chapter_id for c in chapters] == ["00", "01", "02"]
        assert chapters[0].title == "导言"
        assert chapters[1].title == "第一义"

    def test_resolves_notes_file_by_book_id(self, mini_repo: Path):
        spec = BookSpec("01", "测试经", "某人", "哲学", NOTES)
        book = _load(mini_repo, spec).get_book("01")
        assert book is not None
        assert Path(book.notes_file).name == "01-测试经.md"

    def test_explicit_notes_filename_wins(self, mini_repo: Path):
        spec = BookSpec("99", "别名书", "某人", "哲学", NOTES, notes="01-测试经.md")
        book = _load(mini_repo, spec).get_book("99")
        assert book is not None
        assert [c.chapter_id for c in book.chapters] == ["00", "01", "02"]

    def test_missing_notes_yields_no_chapters(self, mini_repo: Path):
        spec = BookSpec("42", "不存在的书", "某人", "哲学", NOTES)
        assert _load(mini_repo, spec).get_chapters("42") == []

    def test_source_text_resolved_from_books_dir(self, mini_repo: Path):
        spec = BookSpec("01", "测试经", "某人", "哲学", NOTES, source="测试经.txt")
        loader = _load(mini_repo, spec)
        assert loader.get_source_text("01") == "原典正文。" * 30

    def test_missing_source_returns_none(self, mini_repo: Path):
        spec = BookSpec("01", "测试经", "某人", "哲学", NOTES, source="查无此文件.txt")
        loader = _load(mini_repo, spec)
        assert loader.get_source_text("01") is None


class TestMdbookStrategy:
    @pytest.fixture()
    def loader(self, mini_repo: Path) -> ContentLoader:
        spec = BookSpec(
            "05", "迷你文集", "某人", "政治", MDBOOK, options={"dir": "MiniBook"}
        )
        return _load(mini_repo, spec)

    def test_numbers_come_from_filename_prefix(self, loader: ContentLoader):
        ids = [c.chapter_id for c in loader.get_chapters("05")]
        assert ids == ["000", "001", "note"]

    def test_titles_strip_the_number_prefix(self, loader: ContentLoader):
        titles = [c.title for c in loader.get_chapters("05")]
        assert titles == ["开篇", "次篇", "note"]

    def test_skips_index_and_readme_files(self, loader: ContentLoader):
        contents = "".join(c.content for c in loader.get_chapters("05"))
        assert "不该被收录" not in contents
        assert "SUMMARY" not in contents

    def test_custom_src_subdir(self, mini_repo: Path):
        spec = BookSpec("05", "迷你文集", "某人", "政治", MDBOOK, options={"dir": "MiniBook", "src": "src"})
        assert len(_load(mini_repo, spec).get_chapters("05")) == 3

    def test_missing_dir_yields_no_chapters(self, mini_repo: Path):
        spec = BookSpec("05", "空文集", "某人", "政治", MDBOOK, options={"dir": "NoSuchDir"})
        assert _load(mini_repo, spec).get_chapters("05") == []

    def test_dir_option_is_required(self, mini_repo: Path):
        spec = BookSpec("05", "无参文集", "某人", "政治", MDBOOK)
        assert _load(mini_repo, spec).get_chapters("05") == []


class TestCollectionStrategy:
    @pytest.fixture()
    def loader(self, mini_repo: Path) -> ContentLoader:
        spec = BookSpec(
            "06", "迷你资料集", "某人", "哲学", COLLECTION,
            options={
                "dir": "MiniColl",
                "entry": "README.md",
                "entry_title": "资料概览",
                "include_dirs": ("诗词",),
            },
        )
        return _load(mini_repo, spec)

    def test_entry_becomes_overview_chapter(self, loader: ContentLoader):
        first = loader.get_chapters("06")[0]
        assert first.chapter_id == "00"
        assert first.title == "资料概览"
        assert first.content == "概览正文"

    def test_included_dirs_are_appended_in_order(self, loader: ContentLoader):
        chapters = loader.get_chapters("06")
        assert [c.chapter_id for c in chapters] == ["00", "01", "02"]
        # 子目录内按文件名排序后依次追加
        assert [c.title for c in chapters[1:]] == ["p1", "p2"]
        assert [c.content for c in chapters[1:]] == ["甲诗正文", "乙诗正文"]

    def test_missing_entry_is_tolerated(self, mini_repo: Path):
        spec = BookSpec(
            "06", "迷你资料集", "某人", "哲学", COLLECTION,
            options={"dir": "MiniColl", "entry": "NOPE.md", "include_dirs": ("诗词",)},
        )
        chapters = _load(mini_repo, spec).get_chapters("06")
        # 首篇缺失时，仅收集子目录内容并重新从 00 编号
        assert [c.chapter_id for c in chapters] == ["00", "01"]


class TestRobustness:
    def test_unknown_loader_raises(self, mini_repo: Path):
        spec = BookSpec("01", "怪书", "某人", "哲学", loader="telepathy")
        with pytest.raises(ValueError, match="未知加载策略"):
            _load(mini_repo, spec)

    def test_undecodable_file_is_skipped(self, mini_repo: Path):
        """坏文件只影响自己，不能让整库加载失败。"""
        (mini_repo / NOTES_DIRNAME / "77-坏书.md").write_bytes(b"\xff\xfe\x00\x01")
        (mini_repo / NOTES_DIRNAME / "78-好书.md").write_text("## 正章\n\n正文", encoding="utf-8")

        loader = _load(
            mini_repo,
            BookSpec("77", "坏书", "x", "y", NOTES),
        )
        assert loader.get_chapters("77") == []

        loader_ok = _load(mini_repo, BookSpec("78", "好书", "x", "y", NOTES))
        assert len(loader_ok.get_chapters("78")) == 1

    def test_non_md_files_are_ignored(self, mini_repo: Path):
        (mini_repo / "MiniBook" / "src" / "junk.txt").write_text("不是 md", encoding="utf-8")
        spec = BookSpec("05", "迷你文集", "某人", "政治", MDBOOK, options={"dir": "MiniBook"})
        titles = [c.title for c in _load(mini_repo, spec).get_chapters("05")]
        assert "junk" not in titles


class TestLoaderLifecycle:
    def test_load_is_idempotent(self, mini_repo: Path):
        spec = BookSpec("01", "测试经", "某人", "哲学", NOTES)
        loader = _load(mini_repo, spec)
        before = len(loader.get_chapters("01"))
        loader.load()
        assert len(loader.get_chapters("01")) == before

    def test_lazy_load_on_first_access(self, mini_repo: Path):
        """未显式调用 load() 时，读取也应自动触发加载。"""
        loader = ContentLoader(root=mini_repo, registry=(BookSpec("01", "测试经", "某人", "哲学", NOTES),))
        assert len(loader.get_chapters("01")) == 3

    def test_unknown_book_returns_none_and_empty(self, mini_repo: Path):
        loader = ContentLoader(root=mini_repo, registry=())
        loader.load()
        assert loader.get_book("zz") is None
        assert loader.get_chapters("zz") == []
        assert loader.get_chapter("zz", "00") is None

    def test_get_all_text_joins_all_chapters(self, mini_repo: Path):
        loader = _load(mini_repo, BookSpec("01", "测试经", "某人", "哲学", NOTES))
        text = loader.get_all_text()
        assert "内容甲" in text and "内容乙" in text
