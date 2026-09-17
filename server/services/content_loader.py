"""内容加载器：把「书目注册表」翻译成内存中的书籍与章节。

设计原则（低耦合、可扩展）
--------------------------------------------------------------------------
1. **声明与行为分离**：`BookSpec` 只描述"这本书是什么"，不参与任何控制流
   判断；"怎么把它装进来"由独立的加载策略负责。
2. **策略分派，而非条件分支**：`load()` 只做一次 `loader -> 策略` 的查表，
   不存在 `if book_id == "05"` 这类与具体书目耦合的分支。
   新增一本书 = 在注册表里登记一行；新增一种来源形态 = 增加一个策略方法。
3. **可注入根目录**：`ContentLoader(root=...)` 允许用临时目录构造实例，
   使加载逻辑可以脱离真实仓库做单元测试。
4. **读取失败不炸**：单个文件读不出来只跳过该文件，不影响整库加载。

数据流
--------------------------------------------------------------------------
    BOOK_REGISTRY (BookSpec) --策略分派--> Chapter 列表 --> Book
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Union

from ..paths import BOOKS_DIRNAME, NOTES_DIRNAME, PROJECT_ROOT

# ── 常量：加载策略名与目录名 ────────────────────────────────────────────

NOTES = "notes"            # 从「理解笔记/」加载并按 `##` 拆分
MDBOOK = "mdbook"          # 从 mdbook 项目的 src/ 目录加载，一篇 md 一章
COLLECTION = "collection"  # 从若干目录收集 md 按序拼装

#: 策略参数值类型：单值，或有序多值
OptionValue = Union[str, tuple[str, ...]]

#: 扫描 md 目录时跳过这些文件名（是目录或配置，不是正文）
_SKIP_FILENAMES = frozenset({"SUMMARY.md", "目录.md", "README.md"})

#: 根目录与语料目录统一由 paths 模块解析——它同时处理源码态与打包态的差异。
#: 这里再转出一份，是为了让 `content_loader.PROJECT_ROOT` 这类历史引用继续可用。
BOOKS_DIR = PROJECT_ROOT / BOOKS_DIRNAME
NOTES_DIR = PROJECT_ROOT / NOTES_DIRNAME


# ── 数据模型 ────────────────────────────────────────────────────────────

@dataclass
class Chapter:
    """章节模型。"""

    chapter_id: str   # 章节标识（如 "001"、"01"）
    title: str        # 章节标题
    content: str      # 章节正文（Markdown）
    book_id: str      # 所属书 ID


@dataclass
class Book:
    """运行时的书籍模型：元信息 + 已加载的章节。"""

    book_id: str
    title: str
    author: str
    category: str
    notes_file: str = ""
    source_file: Optional[str] = None
    chapters: list[Chapter] = field(default_factory=list)


@dataclass(frozen=True)
class BookSpec:
    """一本书的静态元信息：只描述"是什么"，不描述"怎么装"。

    Attributes:
        loader:  加载策略名（NOTES / MDBOOK / COLLECTION）。
        source:  `books/` 下的原典文件名；None 表示暂无原典。
        notes:   `理解笔记/` 下的笔记文件名；None 表示按 ``<book_id>-*.md`` 自动匹配。
        options: 该策略所需的参数包，由策略自行解读（见各 ``_load_*`` 方法）。
    """

    book_id: str
    title: str
    author: str
    category: str
    loader: str = NOTES
    source: Optional[str] = None
    notes: Optional[str] = None
    options: Mapping[str, OptionValue] = field(default_factory=dict)

    def opt(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """读取单值参数。若实际声明的是多值，返回 None（避免静默的类型混淆）。"""
        value = self.options.get(key, default)
        if value is None or isinstance(value, str):
            return value
        return None

    def opt_list(self, key: str) -> tuple[str, ...]:
        """读取多值参数。单值会被包装成单元素元组。"""
        value = self.options.get(key)
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(value)


# ── 书目注册表 ──────────────────────────────────────────────────────────

BOOK_REGISTRY: tuple[BookSpec, ...] = (
    # 原典在 books/ 下，深读笔记在「理解笔记/」下
    BookSpec("01", "易经", "周文王/周公（传）", "哲学", NOTES, source="易经.txt"),
    BookSpec("02", "厚黑学", "李宗吾", "处世", NOTES, source="厚黑学.txt"),
    BookSpec("03", "奇门遁甲", "佚名", "术数", NOTES, source="奇门遁甲.txt"),
    BookSpec("04", "人性的弱点", "戴尔·卡耐基", "处世", NOTES, source="人性的弱点.txt"),
    # 毛选：mdbook 工程，src/ 下每篇 md 即一章
    BookSpec(
        "05", "毛泽东选集", "毛泽东", "政治", MDBOOK,
        options={"dir": "MaoZeDongAnthology", "src": "src"},
    ),
    # 王阳明：资料集，README 作概览章 + 指定子目录内的 md
    BookSpec(
        "06", "王阳明心学", "王守仁", "哲学", COLLECTION,
        options={
            "dir": "WangYangMing",
            "entry": "README.md",
            "entry_title": "王阳明心学概览",
            "include_dirs": ("05-阳明先生诗词",),
        },
    ),
    # 原典与深读笔记齐备
    BookSpec("07", "孙子兵法", "孙武", "兵学", NOTES, source="孙子兵法.txt"),
    BookSpec("08", "道德经", "老子", "哲学", NOTES, source="道德经.txt"),
    BookSpec("09", "论语", "孔子弟子辑录", "哲学", NOTES, source="论语.txt"),
    BookSpec("10", "菜根谭", "洪应明", "处世", NOTES, source="菜根谭.txt"),
    BookSpec("11", "鬼谷子", "鬼谷子", "纵横", NOTES, source="鬼谷子.txt"),
    BookSpec("12", "战国策", "刘向 编订", "纵横", NOTES, source="战国策.txt"),
    # 历史文献
    BookSpec("13", "史记", "司马迁", "历史文献", NOTES, source="史记.txt"),
    BookSpec("14", "资治通鉴", "司马光", "历史文献", NOTES, source="资治通鉴.txt"),
    BookSpec("15", "贞观政要", "吴兢", "历史文献", NOTES, source="贞观政要.txt"),
)


# ── 纯函数工具 ──────────────────────────────────────────────────────────

#: 编号化文件名，形如 "000-中国社会各阶级的分析.md"
_NUMBERED_FILENAME_RE = re.compile(r"^(\d{3})-(.+)\.md$")


def _read_text(path: Path) -> Optional[str]:
    """读取文本；失败时返回 None，不让单个坏文件中断整库加载。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _split_markdown_chapters(content: str, book_id: str) -> list[Chapter]:
    """将 Markdown 按二级标题（`##`）拆分为章节。

    首个 `##` 之前的内容（书名、引言等）作为 ``chapter_id="00"`` 的导言章。
    整篇没有 `##` 时，作为单章返回（``chapter_id="01"``，标题"全文"）。
    """
    parts = re.split(r"^##\s+", content, flags=re.MULTILINE)
    if len(parts) <= 1:
        return [Chapter(chapter_id="01", title="全文", content=content, book_id=book_id)]

    chapters: list[Chapter] = []
    if parts[0].strip():
        chapters.append(
            Chapter(chapter_id="00", title="导言", content=parts[0].strip(), book_id=book_id)
        )

    for index, part in enumerate(parts[1:], start=1):
        lines = part.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        chapters.append(
            Chapter(
                chapter_id=f"{index:02d}",
                title=title,
                content=f"## {title}\n\n{body}",
                book_id=book_id,
            )
        )
    return chapters


# ── 加载器 ──────────────────────────────────────────────────────────────

class ContentLoader:
    """内容加载器：持有书目注册表，产出 `Book` 视图。

    `load()` 幂等，重复调用不会重复累积数据。
    """

    def __init__(
        self,
        root: Optional[Union[str, Path]] = None,
        registry: Sequence[BookSpec] = BOOK_REGISTRY,
    ) -> None:
        self._root = Path(root) if root is not None else PROJECT_ROOT
        self._notes_dir = self._root / NOTES_DIRNAME
        self._books_dir = self._root / BOOKS_DIRNAME
        self._registry = tuple(registry)
        self._loaders: dict[str, Callable[[BookSpec], list[Chapter]]] = {
            NOTES: self._load_notes,
            MDBOOK: self._load_mdbook,
            COLLECTION: self._load_collection,
        }
        self.books: dict[str, Book] = {}
        self._loaded = False
        #: 原典全文缓存。大书（如《资治通鉴》约 3MB）分页读取时
        #: 若每次重读磁盘会浪费大量 IO，这里按需缓存一次。
        self._source_cache: dict[str, Optional[str]] = {}

    # ── 加载策略 ────────────────────────────────────────────────────
    # 每个策略只关心一种来源形态，签名统一为 BookSpec -> list[Chapter]。

    def _load_notes(self, spec: BookSpec) -> list[Chapter]:
        """策略 NOTES：从「理解笔记/」加载一份 md 并按 `##` 切章。

        参数：``notes``（显式文件名；省略时按 ``<book_id>-*.md`` 自动匹配）。
        """
        path = self._resolve_notes_path(spec)
        if path is None:
            return []
        content = _read_text(path)
        return [] if content is None else _split_markdown_chapters(content, spec.book_id)

    def _load_mdbook(self, spec: BookSpec) -> list[Chapter]:
        """策略 MDBOOK：从 mdbook 工程的 src 目录加载，每篇 md 一章。

        参数：``dir``（工程目录名，必填）、``src``（源码子目录，默认 "src"）。
        章节 id 取文件名前缀的三位编号。
        """
        book_dir = spec.opt("dir")
        if not book_dir:
            return []
        src_dir = self._root / book_dir / (spec.opt("src") or "src")
        return self._collect_md_chapters(spec, src_dir, numbered=True)

    def _load_collection(self, spec: BookSpec) -> list[Chapter]:
        """策略 COLLECTION：从指定目录收集 md，按声明顺序拼装成章节序列。

        参数：
            ``dir``          —— 根目录名（必填）
            ``entry``        —— 首篇文件名，作为概览章（可选）
            ``entry_title``  —— 首篇的展示标题（可选，默认取文件名）
            ``include_dirs`` —— 需要额外收录 md 的子目录（可选，有序）
        """
        base_dir = spec.opt("dir")
        if not base_dir:
            return []

        book_dir = self._root / base_dir
        chapters: list[Chapter] = []

        entry = spec.opt("entry")
        if entry:
            text = _read_text(book_dir / entry)
            if text is not None:
                chapters.append(
                    Chapter(
                        chapter_id="00",
                        title=spec.opt("entry_title") or Path(entry).stem,
                        content=text,
                        book_id=spec.book_id,
                    )
                )

        for subdir in spec.opt_list("include_dirs"):
            chapters.extend(self._collect_md_chapters(spec, book_dir / subdir, numbered=False))

        # 重新编号，保证章节号与声明顺序一致
        return [
            Chapter(
                chapter_id=f"{index:02d}",
                title=chapter.title,
                content=chapter.content,
                book_id=chapter.book_id,
            )
            for index, chapter in enumerate(chapters)
        ]

    def _collect_md_chapters(self, spec: BookSpec, directory: Path, *, numbered: bool) -> list[Chapter]:
        """扫描目录下的 md 文件并转成章节（按文件名排序）。

        `numbered=True` 时解析 ``NNN-标题.md`` 取编号与标题；
        否则直接用文件名（无后缀）作为编号与标题。
        """
        if not directory.is_dir():
            return []

        chapters: list[Chapter] = []
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix != ".md" or path.name in _SKIP_FILENAMES:
                continue
            content = _read_text(path)
            if content is None:
                continue

            match = _NUMBERED_FILENAME_RE.match(path.name) if numbered else None
            chapter_id = match.group(1) if match else path.stem
            title = match.group(2) if match else path.stem

            chapters.append(
                Chapter(chapter_id=chapter_id, title=title, content=content, book_id=spec.book_id)
            )
        return chapters

    # ── 路径解析 ────────────────────────────────────────────────────

    def _resolve_notes_path(self, spec: BookSpec) -> Optional[Path]:
        """定位某本书的深读笔记文件。"""
        if spec.notes:
            path = self._notes_dir / spec.notes
            return path if path.is_file() else None

        if not self._notes_dir.is_dir():
            return None
        for path in sorted(self._notes_dir.iterdir()):
            if path.name.startswith(f"{spec.book_id}-") and path.suffix == ".md":
                return path
        return None

    def _resolve_source_path(self, spec: BookSpec) -> Optional[Path]:
        """定位某本书的原典文本（仅在 `books/` 下查找）。"""
        if not spec.source:
            return None
        path = self._books_dir / spec.source
        return path if path.is_file() else None

    # ── 对外 API ────────────────────────────────────────────────────

    def load(self) -> None:
        """加载全部书目与章节（幂等）。"""
        if self._loaded:
            return

        for spec in self._registry:
            loader = self._loaders.get(spec.loader)
            if loader is None:
                raise ValueError(f"未知加载策略 {spec.loader!r}（书目 {spec.book_id}）")

            source_path = self._resolve_source_path(spec)
            notes_path = self._resolve_notes_path(spec)
            self.books[spec.book_id] = Book(
                book_id=spec.book_id,
                title=spec.title,
                author=spec.author,
                category=spec.category,
                notes_file=str(notes_path) if notes_path else "",
                source_file=str(source_path) if source_path else None,
                chapters=loader(spec),
            )

        self._loaded = True

    def get_books(self) -> list[Book]:
        """获取全部书目。"""
        self._ensure_loaded()
        return list(self.books.values())

    def get_book(self, book_id: str) -> Optional[Book]:
        """获取某本书。"""
        self._ensure_loaded()
        return self.books.get(book_id)

    def get_chapters(self, book_id: str) -> list[Chapter]:
        """获取某书的章节列表。"""
        book = self.get_book(book_id)
        return book.chapters if book else []

    def get_chapter(self, book_id: str, chapter_id: str) -> Optional[Chapter]:
        """获取某章节。"""
        return next(
            (ch for ch in self.get_chapters(book_id) if ch.chapter_id == chapter_id),
            None,
        )

    def get_all_text(self) -> str:
        """全部章节正文拼接（供检索层建索引）。"""
        self._ensure_loaded()
        return "\n\n".join(
            chapter.content for book in self.books.values() for chapter in book.chapters
        )

    def get_source_text(self, book_id: str) -> Optional[str]:
        """获取某书的原典全文；无原典或读取失败时返回 None。

        结果按书缓存——原典是只读的，且大书分页读取时重复读盘代价很高。
        """
        book = self.get_book(book_id)
        if book is None or not book.source_file:
            return None
        if book_id not in self._source_cache:
            self._source_cache[book_id] = _read_text(Path(book.source_file))
        return self._source_cache[book_id]

    def get_source_length(self, book_id: str) -> int:
        """原典字符数；无原典时为 0（避免把全文取出来只为量长度）。"""
        text = self.get_source_text(book_id)
        return len(text) if text else 0

    def categories(self) -> list[str]:
        """全部书目分类（按注册顺序去重）。"""
        seen: dict[str, None] = {}
        for spec in self._registry:
            seen.setdefault(spec.category, None)
        return list(seen)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()


# ── 全局单例 ────────────────────────────────────────────────────────────

_loader: Optional[ContentLoader] = None


def get_loader() -> ContentLoader:
    """获取全局内容加载器单例。"""
    global _loader
    if _loader is None:
        _loader = ContentLoader()
        _loader.load()
    return _loader


def reset_loader() -> None:
    """丢弃全局单例（测试与热重载用）。"""
    global _loader
    _loader = None


__all__ = [
    "BOOK_REGISTRY",
    "Book",
    "BookSpec",
    "Chapter",
    "ContentLoader",
    "NOTES",
    "MDBOOK",
    "COLLECTION",
    "PROJECT_ROOT",
    "get_loader",
    "reset_loader",
]
