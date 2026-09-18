"""知识库的正文解析：把深读笔记里的结构化段落变成图上的边。

纯函数模块——不读文件、不建索引、不认识 HTTP。所有输入都是字符串，
所有输出都是 dataclass。这样"链接是怎么被认出来的"可以单独验证，
不必先起一整套服务。

被解析的两类段落（都在「理解笔记」里，是写作时留下的固定格式）
--------------------------------------------------------------------------
1. ``## 四、八大主题归纳`` —— 一张三列表：主题 / 本书的判断 / 代表章句。
   它天然就是"书 → 主题"的边，而且边上还带着理由。

2. ``## 六、与项目内其他经典的交叉点`` —— 一组以 ``- **与《X》**：……``
   起头的条目。它天然就是"书 → 书"的边，冒号后那一整句就是边的说明。

第三节的小节号在不同书里不一样（道德经是"六"、菜根谭是"五"、
资治通鉴是"十一"），所以**按关键词定位、不按序号定位**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Mapping, Optional, Sequence

# ── 小节定位 ────────────────────────────────────────────────────────────

#: 「八大主题归纳」小节。只认标题里出现"八大主题"四个字。
_THEME_SECTION_RE = re.compile(r"^##\s+[^\n]*八大主题[^\n]*$", re.MULTILINE)

#: 「与项目内其他经典的交叉点」小节。标题前半部分各书都写"与项目内其他经典"，
#: 末尾统一是"交叉点"，取"交叉点"作锚点最稳。
_CROSS_SECTION_RE = re.compile(r"^##\s+[^\n]*交叉点[^\n]*$", re.MULTILINE)

#: 任意二级标题——用来界定一个小节的结束。
_ANY_H2_RE = re.compile(r"^##\s+", re.MULTILINE)


def extract_section(content: str, heading: re.Pattern[str]) -> Optional[str]:
    """取出某个二级标题下的正文（不含标题本身）；找不到返回 None。

    结束位置取"下一个二级标题"，因此小节内部的三级标题、引用块都原样保留。
    """
    match = heading.search(content)
    if match is None:
        return None
    body_start = match.end()
    next_heading = _ANY_H2_RE.search(content, body_start)
    body = content[body_start : next_heading.start() if next_heading else len(content)]
    return body.strip()


# ── 八大主题表 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ThemeRow:
    """书页上「八大主题归纳」里的一行。"""

    theme: str      # 主题名（应与 insight.data.VALID_THEMES 对得上）
    judgment: str   # 这本书在该主题下的判断
    quote: str      # 代表章句（含出处）


def _iter_table_rows(section: str) -> Iterator[list[str]]:
    """逐行吐出 Markdown 表格的单元格；非表格行与分隔行自动跳过。"""
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        # `| --- | --- |` 这类分隔行：所有单元格只由 - : 空格组成
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        yield cells


def parse_theme_table(content: str) -> list[ThemeRow]:
    """解析「八大主题归纳」表。

    没有该小节、或表头之外一行都没有时返回空列表——**不猜、不补默认值**：
    没写就是没写，图上就少这条边，比编一条假关系诚实。
    """
    section = extract_section(content, _THEME_SECTION_RE)
    if not section:
        return []

    rows: list[ThemeRow] = []
    for cells in _iter_table_rows(section):
        # 表头行的首格固定是"主题"
        if cells[0] == "主题":
            continue
        if len(cells) < 2 or not cells[0]:
            continue
        rows.append(
            ThemeRow(
                theme=cells[0],
                judgment=cells[1],
                quote=cells[2] if len(cells) > 2 else "",
            )
        )
    return rows


# ── 交叉点 ──────────────────────────────────────────────────────────────

#: ``- **与《道德经》**：孙子"先为不可胜"……``
#: 也兼容不带书名号的写法（笔记里确实存在，如 ``- **与王阳明心学**：``）。
_CROSS_ITEM_RE = re.compile(
    r"^[-*]\s+\*\*\s*与\s*(?:《(?P<quoted>[^》]+)》|(?P<bare>[^*：:]+?))\s*\*\*\s*[：:]\s*(?P<detail>.+)$",
    re.MULTILINE,
)

#: 新条目的开头。用来判断"下一行还是不是同一条"。
_BULLET_START_RE = re.compile(r"^\s*[-*]\s")

#: 小节内部的块级结构：标题、引用、表格、分隔线。它们永远不会是续写行。
_BLOCK_START_RE = re.compile(r"^\s*(#|>|\||-{3,}|\*{3,})")


@dataclass(frozen=True)
class CrossRef:
    """一条"本书参照了那本书"的记录。"""

    name: str    # 原文里写的对方名字（已去掉书名号）
    detail: str  # 冒号后的整句说明


def parse_cross_refs(content: str) -> list[CrossRef]:
    """解析「与项目内其他经典的交叉点」小节。

    只认 ``- **与X**：……`` 这一种写法。小节里若混入别的散句（例如"一句话收束"
    的引用块），自然不会被匹配——宁可漏，不可错配。

    条目换行续写（Markdown 里长句子被折成两行）会拼回一句：只要下一行不是
    新条目、不是空行、也不是块级结构，就认为它属于上一条。当前的语料全都是
    单行，加这条是为了将来往笔记里补内容时不会**静默丢掉半句话**。
    """
    section = extract_section(content, _CROSS_SECTION_RE)
    if not section:
        return []

    lines = section.splitlines()
    refs: list[CrossRef] = []
    index = 0
    while index < len(lines):
        match = _CROSS_ITEM_RE.match(lines[index])
        if match is None:
            index += 1
            continue

        parts = [match.group("detail")]
        cursor = index + 1
        while cursor < len(lines):
            nxt = lines[cursor]
            if not nxt.strip() or _BULLET_START_RE.match(nxt) or _BLOCK_START_RE.match(nxt):
                break
            parts.append(nxt.strip())
            cursor += 1

        name = (match.group("quoted") or match.group("bare") or "").strip()
        detail = " ".join(" ".join(parts).split())
        if name and detail:
            refs.append(CrossRef(name=name, detail=detail))
        index = cursor

    return refs


# ── 书名解析 ────────────────────────────────────────────────────────────

#: 笔记里出现的别称 → 注册表中的正式书名。
#: 只收"确实出现在语料里"的写法；不做模糊匹配，免得把《论语》认成《论语译注》。
BOOK_ALIASES: Mapping[str, str] = {
    "毛选": "毛泽东选集",
    "毛泽东选集": "毛泽东选集",
    "毛主席": "毛泽东选集",
    "通鉴": "资治通鉴",
    "老子": "道德经",
    "周易": "易经",
    "易": "易经",
    "王阳明": "王阳明心学",
    "阳明": "王阳明心学",
    "心学": "王阳明心学",
    "阳明心学": "王阳明心学",
    "孙子": "孙子兵法",
    "卡耐基": "人性的弱点",
    "孔子": "论语",
}

#: 匹配时忽略的修饰词。笔记里偶尔写"《论语》原典"这类，去掉更稳。
_NOISE_RE = re.compile(r"[\s　《》〈〉「」『』·、，,。.]")


def _normalize(name: str) -> str:
    """去掉书名号、空白与标点，便于比对。"""
    return _NOISE_RE.sub("", name or "")


class BookNameIndex:
    """书名 → book_id 的解析器。

    解析顺序（先精确、后包含）：
      1. 与正式书名完全相同
      2. 与别称表完全相同
      3. 正式书名被名字包含（取最长者，避免"易经"抢走"易经与易传"）
      4. 别称被名字包含（同样取最长者）

    全部落空返回 None——调用方据此把"认不出的引用"记进统计，
    而不是硬塞给某本书。
    """

    def __init__(self, titles: Mapping[str, str]) -> None:
        """:param titles: ``book_id -> 正式书名``。"""
        self._by_title: dict[str, str] = {}
        for book_id, title in titles.items():
            self._by_title.setdefault(_normalize(title), book_id)
        self._titles: tuple[str, ...] = tuple(
            sorted(self._by_title, key=len, reverse=True)
        )
        self._aliases: tuple[tuple[str, str], ...] = tuple(
            sorted(
                ((_normalize(alias), target) for alias, target in BOOK_ALIASES.items()),
                key=lambda pair: len(pair[0]),
                reverse=True,
            )
        )

    def resolve(self, name: str) -> Optional[str]:
        """把一处引用文本解析成 book_id；认不出返回 None。"""
        needle = _normalize(name)
        if not needle:
            return None

        if needle in self._by_title:
            return self._by_title[needle]

        for alias, target in self._aliases:
            if alias == needle:
                return self._by_title.get(_normalize(target))

        for title in self._titles:
            if title in needle:
                return self._by_title[title]

        for alias, target in self._aliases:
            if alias in needle:
                return self._by_title.get(_normalize(target))

        return None

    def titles(self) -> Sequence[str]:
        """本次索引里全部正式书名的规范化形式（调试用）。"""
        return self._titles


__all__ = [
    "BOOK_ALIASES",
    "BookNameIndex",
    "CrossRef",
    "ThemeRow",
    "extract_section",
    "parse_cross_refs",
    "parse_theme_table",
]
