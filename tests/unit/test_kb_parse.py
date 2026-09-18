"""知识库解析层的单元测试：验证"链接是怎么被认出来的"。

全部是纯字符串进、dataclass 出，不碰文件系统也不碰 HTTP。
这里要守住的底线是**宁可漏、不可错配**：认不出的引用必须返回 None，
而不是随手塞给某本名字沾边的书。
"""

import re

import pytest

from server.services.kb.parse import (
    BOOK_ALIASES,
    BookNameIndex,
    extract_section,
    parse_cross_refs,
    parse_theme_table,
)

TITLES = {
    "01": "易经",
    "05": "毛泽东选集",
    "06": "王阳明心学",
    "07": "孙子兵法",
    "08": "道德经",
    "09": "论语",
    "14": "资治通鉴",
}

#: 与服务层实际使用的定位方式一致：按关键词锚定标题，不看小节序号
THEME_HEADING = re.compile(r"^##\s+[^\n]*八大主题[^\n]*$", re.MULTILINE)
CROSS_HEADING = re.compile(r"^##\s+[^\n]*交叉点[^\n]*$", re.MULTILINE)


@pytest.fixture
def index() -> BookNameIndex:
    return BookNameIndex(TITLES)


# ── 小节定位 ────────────────────────────────────────────────────────────

class TestExtractSection:
    def test_returns_body_without_heading(self):
        content = "# 书\n\n## 一、甲\n\n正文甲\n\n## 二、乙\n\n正文乙\n"
        assert extract_section(content, re.compile(r"^##\s+[^\n]*甲[^\n]*$", re.MULTILINE)) == "正文甲"

    def test_missing_section_returns_none(self):
        assert extract_section("## 一、甲\n\n正文\n", CROSS_HEADING) is None

    def test_empty_body_returns_empty_string(self):
        content = "## 四、八大主题归纳\n\n## 五、别的\n\n正文\n"
        assert extract_section(content, THEME_HEADING) == ""

    def test_section_at_end_of_document(self):
        content = "## 四、八大主题归纳\n\n| 主题 | 判断 | 章句 |\n"
        body = extract_section(content, THEME_HEADING)
        assert "| 主题 | 判断 | 章句 |" in body

    def test_heading_wording_varies_but_keyword_anchors(self):
        """小节序号各书不同（四/五/九/十一），所以只按关键词定位。"""
        for heading in ("## 四、八大主题归纳", "## 五、八大主题归纳", "## 九、八大主题归纳"):
            content = f"{heading}\n\n行内容\n"
            assert extract_section(content, THEME_HEADING) == "行内容"


# ── 八大主题表 ──────────────────────────────────────────────────────────

THEME_TABLE = """## 四、八大主题归纳

| 主题 | 本书的判断 | 代表章句 |
| --- | --- | --- |
| 逆境 | 祸福相倚，低谷是转化的起点 | "祸兮福之所倚"（58）|
| 谋略 | 柔弱胜刚强，以退为进 | "反者道之动，弱者道之用"（40）|

---

## 五、常见误读辨析

- **与《易经》**：这是不该被主题表吃进去的一行。
"""


class TestParseThemeTable:
    def test_reads_all_three_columns(self):
        rows = parse_theme_table(THEME_TABLE)
        assert [r.theme for r in rows] == ["逆境", "谋略"]
        assert rows[0].judgment == "祸福相倚，低谷是转化的起点"
        assert rows[0].quote == '"祸兮福之所倚"（58）'

    def test_skips_header_and_separator(self):
        rows = parse_theme_table(THEME_TABLE)
        assert "主题" not in [r.theme for r in rows]

    def test_ignores_content_outside_section(self):
        """下一小节里的交叉点条目不该被当成表格行。"""
        rows = parse_theme_table(THEME_TABLE)
        assert all("易经" not in r.judgment for r in rows)

    def test_two_column_table_leaves_quote_empty(self):
        content = "## 四、八大主题归纳\n\n| 主题 | 判断 |\n| --- | --- |\n| 修心 | 致虚守静 |\n"
        rows = parse_theme_table(content)
        assert len(rows) == 1
        assert rows[0].quote == ""

    def test_no_section_returns_empty(self):
        assert parse_theme_table("## 一、别的\n\n正文\n") == []

    def test_header_only_returns_empty(self):
        content = "## 四、八大主题归纳\n\n| 主题 | 判断 | 章句 |\n| --- | --- | --- |\n"
        assert parse_theme_table(content) == []

    def test_blank_theme_cell_is_dropped(self):
        content = "## 四、八大主题归纳\n\n| 主题 | 判断 | 章句 |\n| --- | --- | --- |\n|  | 空主题 | x |\n| 恒心 | 重在持续 | y |\n"
        assert [r.theme for r in parse_theme_table(content)] == ["恒心"]


# ── 交叉点 ──────────────────────────────────────────────────────────────

CROSS = """## 六、与项目内其他经典的交叉点

- **与《易经》**：易经"物极必反"与老子"反者道之动"是同一洞察的两种表达。
- **与王阳明心学**：路径不同（减 vs 改），方向一致（去妄）。
- **与《孙子兵法》**：先求不败，再求胜。

---

> **一句话收束**：读这本书最该带走的一句是"既以为人己愈有"。
"""


class TestParseCrossRefs:
    def test_reads_quoted_and_bare_forms(self):
        refs = parse_cross_refs(CROSS)
        assert [r.name for r in refs] == ["易经", "王阳明心学", "孙子兵法"]

    def test_keeps_detail_text(self):
        refs = parse_cross_refs(CROSS)
        assert refs[0].detail.startswith("易经")
        assert "同一洞察" in refs[0].detail

    def test_ignores_quote_block_after_section(self):
        """收束的引用块不是交叉点条目，不能被当成一条边。"""
        refs = parse_cross_refs(CROSS)
        assert all("一句话收束" not in r.detail for r in refs)

    def test_no_section_returns_empty(self):
        assert parse_cross_refs("## 一、别的\n\n- **与《易经》**：不该被读到。\n") == []

    def test_plain_bullet_without_bold_is_ignored(self):
        content = "## 六、与项目内其他经典的交叉点\n\n- 与《易经》有关。\n"
        assert parse_cross_refs(content) == []

    def test_multiline_detail_is_collapsed_to_one_line(self):
        content = "## 六、与项目内其他经典的交叉点\n\n- **与《易经》**：第一行\n  第二行接续。\n"
        refs = parse_cross_refs(content)
        assert refs[0].detail == "第一行 第二行接续。"


# ── 书名解析 ────────────────────────────────────────────────────────────

class TestBookNameIndex:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("道德经", "08"),
            ("易经", "01"),
            ("论语", "09"),
            ("孙子兵法", "07"),
            ("毛泽东选集", "05"),
            ("王阳明心学", "06"),
        ],
    )
    def test_exact_title(self, index, name, expected):
        assert index.resolve(name) == expected

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("毛选", "05"),
            ("毛主席", "05"),
            ("通鉴", "14"),
            ("老子", "08"),
            ("周易", "01"),
            ("王阳明", "06"),
            ("阳明心学", "06"),
            ("孙子", "07"),
        ],
    )
    def test_alias(self, index, alias, expected):
        assert index.resolve(alias) == expected

    def test_exact_title_wins_over_alias(self, index):
        """「王阳明心学」既撞别名「王阳明」又是正式书名，必须取正式书名那条。"""
        assert index.resolve("王阳明心学") == "06"

    def test_strips_book_marks_and_punctuation(self, index):
        assert index.resolve("《道德经》") == "08"
        assert index.resolve(" 《 道德经 》 ") == "08"

    def test_containment_resolves_longer_phrase(self, index):
        assert index.resolve("孙子兵法与三十六计") == "07"

    def test_unknown_name_returns_none(self, index):
        assert index.resolve("山海经") is None
        assert index.resolve("") is None
        assert index.resolve("   ") is None

    def test_longest_alias_wins(self, index):
        """「阳明心学」与「心学」都能指王阳明，取更具体的那个，结果一致。"""
        assert index.resolve("阳明心学的功夫论") == "06"

    def test_alias_table_only_maps_to_known_titles(self):
        """别名表若指向了不存在的正式书名，那就是一处静默失效——这里把它钉住。"""
        known_titles = set(BOOK_ALIASES.values())
        registry_titles = {
            "易经", "厚黑学", "奇门遁甲", "人性的弱点", "毛泽东选集",
            "王阳明心学", "孙子兵法", "道德经", "论语", "菜根谭",
            "鬼谷子", "战国策", "史记", "资治通鉴", "贞观政要",
        }
        assert known_titles <= registry_titles
