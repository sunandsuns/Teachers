"""联网书籍检索：多书源，按序试，谁先给出结果用谁。

为什么不再只挂 OpenLibrary
--------------------------------------------------------------------------
原来只有一个源，OpenLibrary。它在**国内直连不通**——2026-09-28 在用户本机实测：

    直连（不走代理）      URLError: timed out         12.0s
    走环境里的代理        502 Bad Gateway             10.0s
    DNS 解析            正常（128.242.245.189）

`docs` 里那句"国内连不上所以由浏览器直连兜底"其实一直在自欺：真正需要绕开的那张网
里，**浏览器同样出不去**，所以那条兜底从来没生效过，只是让用户在后端超时之后**再**
等 20 秒，然后收到一句"浏览器与服务器两条路都没通"。

同一台机器上实测三个源（搜索「昆虫记」）：

    书源          首字节    自带简介   封面能在页面里加载   结果数
    微信读书      0.20s     ✅        ✅                  20
    豆瓣          0.20s     ❌        ❌（防盗链）          2
    OpenLibrary   超时      —         —                   —

于是顺序定为 **微信读书 → 豆瓣 → OpenLibrary**。前两个在境内，正常时第一个就命中；
OpenLibrary 留在最后，给能出去的机器（比如在国外跑的桌面版）兜英文书。

关键词型书源必须过一道**相关性闸门**
--------------------------------------------------------------------------
微信读书与豆瓣都只有一个"整串关键词"参数，而且都是**模糊的全库检索**：实测搜
「zzqq 不存在的书 xyz」照样回 4 本不相干的书（《第一推动丛书》《不存在的骑士》
《不合理的快乐》）。不拦的话界面**永远说不出"没有找到这本书"**，用户会以为系统
坏了。而且这两个源对作者名做与运算时反而更差——搜「活着 余华」，第一条是
《余华长篇小说（兄弟、活着、许三观卖血记…）》这种合集，《我在岛屿读书》也混
进来；改成只拿书名当关键词、再把作者当**筛子**，第一条才回到《活着》本身。

所以这两个源走 :func:`_filter_keyword_hits`：先按书名相关性命中，再尽量按作者
收窄（作者一个都没命中就**不硬筛**，见那里的注释）。OpenLibrary 不走这道闸门
——它是 ``title=`` / ``author=`` 的结构化检索，本来就准，再闸一刀反而会误伤
副标题与译本名。

字段口径
--------------------------------------------------------------------------
- **豆瓣的封面一律丢掉**。它有防盗链：无 Referer 回 418、外域 Referer 回 403。
  取回来挂在页面上就是一张裂图，不如留空让前端走灰底占位。
- **微信读书的搜索响应自带 `intro`**，所以列表阶段就有简介，不必再打第二次请求。
  只有 OpenLibrary 仍需 :func:`fetch_detail` 单独取。微信读书与豆瓣也**都没有
  主题标签**，`subjects` 因此为空——这是数据源的边界，不编。
- 微信读书的 `publishTime` 实测恒为空，所以那个源给不出出版年。

失败即降级
--------------------------------------------------------------------------
与项目其他网络模块一致：不往上抛异常，把原因装进 :attr:`SearchOutcome.error`。
检索不到书不该让"添加一本书"这个动作整个失败。

一个必须知道的坑（沿用自 OpenLibrary）
--------------------------------------------------------------------------
那个源的 ``q=`` 参数有 **3 字符下限**——中文书名"活着""三体"只有两个字，会被
直接 422 掉（报 "Query too short"）。必须走 ``title=`` / ``author=`` 这两个专用
参数，它们没有这个限制。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from . import netproxy

#: 给国内站点用的浏览器 UA。微信读书与豆瓣都对非浏览器 UA 更凶（豆瓣的网页搜索
#: 对 curl 直接 403），实测带这个 UA 的 `subject_suggest` 稳定 200。
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

#: OpenLibrary 那边用项目自己的 UA——它不挑，且便于对方识别流量来源。
PROJECT_UA = "renshengdaoshi/1.0 (personal reading list)"

#: 所有书源加起来的时间上限。
#:
#: 光靠单源超时挡不住最坏情况：三个源各超时一次就是三十几秒，用户盯着转圈。
#: 有了总预算，断网时最坏也就等这么久。实测正常路径 0.2 秒就返回了。
TOTAL_BUDGET = 16.0

#: 主题最多留几个。OpenLibrary 的 subject 列表动辄上百条，全存进库没意义。
MAX_SUBJECTS = 8

#: 简介截断长度。详情页的 description 可能上万字，存进库会把列表撑爆。
MAX_SUMMARY = 1200

# ── 各源端点 ────────────────────────────────────────────────────────────────

WEREAD_URL = "https://weread.qq.com/web/search/global"
DOUBAN_SUGGEST_URL = "https://book.douban.com/j/subject_suggest"

#: 单本书的详情端点（``{key}`` 形如 ``/works/OL27448W``）
DETAIL_URL = "https://openlibrary.org{key}.json"
SEARCH_URL = "https://openlibrary.org/search.json"

#: 封面图。``{cover}`` 是 OpenLibrary 的 cover id；``-M`` 是中图，
#: 列表里够用且省流量（``-L`` 动辄几百 KB）。
COVER_URL = "https://covers.openlibrary.org/b/id/{cover}-M.jpg"

#: 只取用得上的字段。默认返回体里有几十个字段（各种 id、版本信息），
#: 限定之后响应体小一个量级。
SEARCH_FIELDS = "title,author_name,first_publish_year,cover_i,key,subject"


class BookSearchError(RuntimeError):
    """检索失败。消息是给用户看的中文。

    ``unavailable`` 说的是**这次压根没走到上游**——DNS、TCP、TLS 任何一层断了，
    而不是"上游答复了，只是没有这本书"。两种要分开：前者该提示"稍后重试"，
    后者该提示"换个说法"。

    （历史注：这个字段以前是给前端的"改用浏览器直连"分支用的。那条路已经删掉
    ——现役的书源都不发 CORS 头，浏览器直连不可能成功。现在它只影响措辞。）
    """

    def __init__(self, message: str, *, unavailable: bool = False) -> None:
        super().__init__(message)
        self.unavailable = unavailable


@dataclass(frozen=True)
class BookCandidate:
    """一本书的元信息。

    ``source_key`` 是来源方的书目标识（微信读书的 bookId、豆瓣的 subject id、
    OpenLibrary 的 work id），用来去重与回查详情；拿不到时为空串。

    ``source`` 说明它来自哪个源。跨源的同名书**不去重**（各自的 id 空间不同），
    但同一个源内部按 ``source_key`` 去重——同一本书的精装/平装/再版会各占一条。
    """

    title: str
    author: str = ""
    year: str = ""
    cover_url: str = ""
    source_key: str = ""
    source: str = ""
    summary: str = ""
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchOutcome:
    """一次检索的结果。``error`` 非空时 ``results`` 必为空。"""

    results: tuple[BookCandidate, ...] = ()
    error: str = ""
    #: 错误属于"没连上上游"。前端据此把措辞从"换个说法"切成"稍后重试"。
    unavailable: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


# ── 取数 ────────────────────────────────────────────────────────────────────


def _get_json(
    url: str,
    *,
    opener: Optional[urllib.request.OpenerDirector],
    timeout: float,
    user_agent: str,
) -> Any:
    """发一次 GET 并解析 JSON。失败一律转成 :class:`BookSearchError`。"""
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )
    try:
        with (opener or netproxy.build_opener()).open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            raise BookSearchError("检索词太短，请把书名或作者写全一些") from exc
        if exc.code == 429:
            raise BookSearchError("检索服务请求过于频繁，请稍后再试") from exc
        if exc.code == 404:
            raise BookSearchError("没有找到这本书的详情") from exc
        if exc.code in (502, 503, 504):
            # 网关/代理替上游回了话，上游本身没通——仍属"没走到上游"
            raise BookSearchError(
                f"检索服务暂时不可用（HTTP {exc.code}）", unavailable=True
            ) from exc
        raise BookSearchError(f"检索服务返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BookSearchError(
            f"无法连接检索服务：{exc.reason}", unavailable=True
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BookSearchError("检索结果不是合法 JSON") from exc
    except OSError as exc:
        raise BookSearchError(f"网络异常：{exc}", unavailable=True) from exc


def _text(value: Any) -> str:
    """把可能是 None / 数字 / 字符串的字段统一成去空白的字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _authors(value: Any) -> str:
    """作者字段可能是字符串，也可能是数组。取前两位（合著/译者列表可能很长）。"""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return "、".join(_text(a) for a in value[:2] if _text(a))
    return _text(value)


def _truncate(raw: str) -> str:
    """把简介截到 :data:`MAX_SUMMARY`，并在句号/换行处收尾，别把一句话砍成两半。"""
    text = (raw or "").strip()
    if len(text) <= MAX_SUMMARY:
        return text
    cut = text[:MAX_SUMMARY]
    for mark in ("。", "\n", ". "):
        index = cut.rfind(mark)
        if index > MAX_SUMMARY // 2:
            return cut[: index + len(mark)].rstrip() + "…"
    return cut.rstrip() + "…"


def _take(candidates: Sequence[Optional[BookCandidate]], limit: int) -> tuple[BookCandidate, ...]:
    """丢掉空条目、按 ``source_key`` 去重、截到 ``limit`` 条。"""
    results: list[BookCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.source_key and candidate.source_key in seen:
            continue
        if candidate.source_key:
            seen.add(candidate.source_key)
        results.append(candidate)
        if len(results) >= limit:
            break
    return tuple(results)


#: 归一化时**去掉**的字符。只留中日韩汉字与英数：书名里的《》、空格、破折号、
#: 出版方加的「（全三册）」括号，都不该影响"这是不是同一本"。
_NOISE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def _normalize(text: str) -> str:
    """把书名/作者压成可比对的形状（小写、去标点与空白）。"""
    return _NOISE.sub("", (text or "").lower())


def _matches_query(candidate: BookCandidate, query: str) -> bool:
    """相关性闸门：书名**或作者**跟查询互相包含，即算命中。

    书名两个方向都要认——用户可能只打书名的一半（`人类简史` 对
    《人类简史：从动物到上帝》），也可能把副标题一起打进来（`三体全集（全三册）`
    对《三体》）。去掉空白之后，"人类 简史"这种带空格的输入也自然能对上。

    **作者也要认**：用户常把作者名敲进书名框（那里没有 placeholder 强制他分栏）。
    只看书名的话，搜「余华」会把《活着》《许三观卖血记》全判成不相关——而那正是
    他要找的。
    """
    needle = _normalize(query)
    if not needle:
        return True
    title = _normalize(candidate.title)
    author = _normalize(candidate.author)
    return needle in title or title in needle or needle in author


def _filter_keyword_hits(
    hits: Sequence[BookCandidate], title: str, author: str
) -> tuple[BookCandidate, ...]:
    """关键词型书源（微信读书 / 豆瓣）的公共后处理。

    先过相关性闸门，再**尽量**按作者收窄。作者一个都没命中时**不硬筛**：作者名的
    写法太杂（"余华" / "[法]法布尔" / "让-亨利·法布尔"），硬筛会把本该命中的书
    整批筛掉——而"筛没了"和"本来就没有"在界面上是同一种表现。
    """
    gated = [c for c in hits if _matches_query(c, title)]
    needle = _normalize(author)
    if needle:
        narrowed = [c for c in gated if needle in _normalize(c.author)]
        if narrowed:
            return tuple(narrowed)
    return tuple(gated)


# ── 微信读书 ────────────────────────────────────────────────────────────────


def _weread_candidate(info: Mapping[str, Any]) -> Optional[BookCandidate]:
    """``bookInfo`` → 候选。字段实测形态见模块 docstring。"""
    title = _text(info.get("title"))
    if not title:
        return None
    return BookCandidate(
        title=title,
        author=_authors(info.get("author")),
        # 搜索响应里的 publishTime 实测恒为空，取不到出版年
        year="",
        cover_url=_text(info.get("cover")),
        source_key=_text(info.get("bookId")),
        source="weread",
        summary=_truncate(_text(info.get("intro"))),
        subjects=(),
    )


def _search_weread(
    title: str, author: str, limit: int, *, opener, timeout: float
) -> SearchOutcome:
    """微信读书。

    **只拿书名当关键词**（没给书名才退而用作者）。把它和作者拼成一句一起搜是条
    看着合理、实测更差的路：那个接口是模糊全文检索，「活着 余华」会把《我在岛屿
    读书》《革命历史小说研究》这类不相干的书也算命中，而单纯搜「活着」第一条
    就是《活着》本身。作者改由 :func:`_filter_keyword_hits` 当筛子用。
    """
    keyword = title or author
    url = WEREAD_URL + "?" + urllib.parse.urlencode({"keyword": keyword})
    try:
        data = _get_json(url, opener=opener, timeout=timeout, user_agent=BROWSER_UA)
    except BookSearchError as exc:
        return SearchOutcome((), str(exc), unavailable=exc.unavailable)
    items = data.get("books") if isinstance(data, Mapping) else None
    if not isinstance(items, list):
        return SearchOutcome((), "检索结果格式异常")

    hits: list[BookCandidate] = []
    for item in items:
        info = item.get("bookInfo") if isinstance(item, Mapping) else None
        if not isinstance(info, Mapping):
            continue
        candidate = _weread_candidate(info)
        if candidate is not None:
            hits.append(candidate)
    # 先在**全部**命中里过滤再截断——反过来会让 limit 被不相干的书占满
    return SearchOutcome(_take(_filter_keyword_hits(hits, title, author), limit))


# ── 豆瓣 ────────────────────────────────────────────────────────────────────


def _douban_candidate(item: Mapping[str, Any]) -> Optional[BookCandidate]:
    """``subject_suggest`` 的一条 → 候选。

    这个端点是自动补全接口，书上字段很少：书名、作者、年份、封面，**没有简介**。
    封面还带防盗链，见模块 docstring——所以这里直接丢掉。
    """
    # 同一个接口也会混进影视/音乐（``type`` 为 ``m`` / ``music``），只收书
    kind = _text(item.get("type"))
    if kind and kind != "b":
        return None
    title = _text(item.get("title"))
    if not title:
        return None
    return BookCandidate(
        title=title,
        author=_authors(item.get("author_name")),
        year=_text(item.get("year")),
        cover_url="",
        source_key=_text(item.get("id")),
        source="douban",
        summary="",
        subjects=(),
    )


def _search_douban(
    title: str, author: str, limit: int, *, opener, timeout: float
) -> SearchOutcome:
    """豆瓣自动补全。只有整串关键词，规则与微信读书那条一致（见其 docstring）。"""
    keyword = title or author
    url = DOUBAN_SUGGEST_URL + "?" + urllib.parse.urlencode({"q": keyword})
    try:
        data = _get_json(url, opener=opener, timeout=timeout, user_agent=BROWSER_UA)
    except BookSearchError as exc:
        return SearchOutcome((), str(exc), unavailable=exc.unavailable)
    if not isinstance(data, list):
        return SearchOutcome((), "检索结果格式异常")

    hits = [
        _douban_candidate(item)
        for item in data
        if isinstance(item, Mapping)
    ]
    return SearchOutcome(_take(_filter_keyword_hits(
        [c for c in hits if c is not None], title, author), limit))


# ── OpenLibrary ─────────────────────────────────────────────────────────────


def _openlibrary_candidate(doc: Mapping[str, Any]) -> Optional[BookCandidate]:
    """把 OpenLibrary 的一条 doc 转成 :class:`BookCandidate`。"""
    title = _text(doc.get("title"))
    if not title:
        return None

    raw_key = _text(doc.get("key"))
    # "/works/OL27448W" → "OL27448W"
    source_key = raw_key.rsplit("/", 1)[-1] if raw_key else ""

    cover = doc.get("cover_i")
    cover_url = ""
    if isinstance(cover, int) and cover > 0:
        cover_url = COVER_URL.format(cover=cover)
    elif isinstance(cover, str) and cover.isdigit():
        cover_url = COVER_URL.format(cover=int(cover))

    raw_subjects = doc.get("subject")
    subjects: tuple[str, ...] = ()
    if isinstance(raw_subjects, Sequence) and not isinstance(raw_subjects, str):
        subjects = tuple(_text(s) for s in raw_subjects[:MAX_SUBJECTS] if _text(s))

    return BookCandidate(
        title=title,
        author=_authors(doc.get("author_name")),
        year=_text(doc.get("first_publish_year")),
        cover_url=cover_url,
        source_key=source_key,
        source="openlibrary",
        subjects=subjects,
    )


def _search_openlibrary(
    title: str, author: str, limit: int, *, opener, timeout: float
) -> SearchOutcome:
    """OpenLibrary。这个源有 ``title=`` / ``author=`` 两个独立参数。"""

    def run(params: Mapping[str, str]) -> SearchOutcome:
        query = {"limit": str(limit), "fields": SEARCH_FIELDS, **params}
        url = SEARCH_URL + "?" + urllib.parse.urlencode(query)
        try:
            data = _get_json(url, opener=opener, timeout=timeout, user_agent=PROJECT_UA)
        except BookSearchError as exc:
            return SearchOutcome((), str(exc), unavailable=exc.unavailable)
        docs = data.get("docs") if isinstance(data, Mapping) else None
        if not isinstance(docs, list):
            return SearchOutcome((), "检索结果格式异常")
        return SearchOutcome(_take([
            _openlibrary_candidate(d) if isinstance(d, Mapping) else None for d in docs
        ], limit))

    params = {}
    if title:
        params["title"] = title
    if author:
        params["author"] = author
    outcome = run(params)
    if outcome.results or not (title and author):
        return outcome
    return run({"title": title})


# ── 书源注册表 ──────────────────────────────────────────────────────────────

SearchFn = Callable[..., SearchOutcome]


@dataclass(frozen=True)
class BookSource:
    """一个书源。``timeout`` 是**单个请求**的上限，总上限见 :data:`TOTAL_BUDGET`。"""

    key: str
    label: str
    timeout: float
    search: SearchFn
    #: 境外源。只在境内那些都没答复时才值得一试——它多半只是白等一次超时。
    overseas: bool = False


#: 按序试。前两个在境内（0.2 秒级），OpenLibrary 留最后给能出去的机器兜英文书。
SOURCES: tuple[BookSource, ...] = (
    BookSource("weread", "微信读书", 8.0, _search_weread),
    BookSource("douban", "豆瓣", 8.0, _search_douban),
    BookSource("openlibrary", "OpenLibrary", 12.0, _search_openlibrary, overseas=True),
)

#: 键 → 源，给"这个 source_key 该用哪个源取详情"用。
SOURCES_BY_KEY = {source.key: source for source in SOURCES}

#: 哪些源**还需要**单独取详情。微信读书的简介在搜索响应里就给了，豆瓣压根没有；
#: 只有 OpenLibrary 要再打一次 ``/works/<id>.json``。
DETAIL_SOURCES = frozenset({"openlibrary"})


def search_books(
    title: str = "",
    author: str = "",
    *,
    limit: int = 6,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> SearchOutcome:
    """按书名 / 作者检索书籍，**按 :data:`SOURCES` 的顺序试，谁先给出结果用谁**。

    ``opener`` 只为测试注入，正常调用不必传。

    一个源都没给出结果时，回来的是"空结果 + 有 error"，不是异常。两种"空"要分清：

    - 只要有**任何一个源答复过**（哪怕答复是"我这里没有"），就如实返回"没有这本书"
      ——上游的沉默不等于书不存在，但上游明确说没有就是没有。
    - 所有源**都没走到上游**时，把**最优先那个源**的原因报出来（它最可能是用户
      真正想用的那个）。

    **境外源只在境内那些都没答复时才试**：`openlibrary` 在国内是必然超时的，
    前面已经有源明确答复过"没有"时还去撞它，只是把一次 0.2 秒的检索拖成 12 秒。
    """
    clean_title = (title or "").strip()
    clean_author = (author or "").strip()
    if not clean_title and not clean_author:
        return SearchOutcome((), "请至少填写书名或作者")

    started = time.monotonic()
    attempts: list[tuple[BookSource, SearchOutcome]] = []
    for source in SOURCES:
        if source.overseas and any(outcome.ok for _, outcome in attempts):
            break
        remaining = TOTAL_BUDGET - (time.monotonic() - started)
        if remaining <= 0.5:
            # 预算用光，别再开新连接——否则"试完所有源"就是三十几秒的白等
            attempts.append((source, SearchOutcome((), "检索超时", unavailable=True)))
            continue
        outcome = source.search(
            clean_title, clean_author, limit,
            opener=opener, timeout=min(source.timeout, remaining),
        )
        if outcome.results:
            return outcome
        attempts.append((source, outcome))

    if any(outcome.ok for _, outcome in attempts):
        return SearchOutcome(())
    first_source, first = attempts[0]
    return SearchOutcome(
        (),
        first.error or f"连不上{first_source.label}",
        unavailable=first.unavailable,
    )


def fetch_detail(
    source: str,
    source_key: str,
    *,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> Optional[BookCandidate]:
    """取一本书的详情（含简介与主题）。

    **只有 :data:`DETAIL_SOURCES` 里的源支持**——其余直接返回 ``None``，不白跑一趟
    网络。微信读书的简介在搜索响应里已经带上了，豆瓣不提供详情。

    在用户**选中**某个候选、真正要加进书架时才调。失败返回 ``None``：详情是
    锦上添花，拿不到也该能把书加进去。
    """
    key = (source_key or "").strip()
    if not key or (source or "").strip() not in DETAIL_SOURCES:
        return None

    path = key if key.startswith("/") else f"/works/{key}"
    try:
        data = _get_json(
            DETAIL_URL.format(key=path),
            opener=opener,
            timeout=SOURCES_BY_KEY["openlibrary"].timeout,
            user_agent=PROJECT_UA,
        )
    except BookSearchError:
        return None
    if not isinstance(data, Mapping):
        return None

    title = _text(data.get("title"))
    if not title:
        return None

    raw_subjects = data.get("subjects")
    subjects: tuple[str, ...] = ()
    if isinstance(raw_subjects, Sequence) and not isinstance(raw_subjects, str):
        subjects = tuple(_text(s) for s in raw_subjects[:MAX_SUBJECTS] if _text(s))

    return BookCandidate(
        title=title,
        author="",
        year="",
        source_key=key.rsplit("/", 1)[-1],
        source="openlibrary",
        summary=_truncate(_text(
            data.get("description").get("value")
            if isinstance(data.get("description"), Mapping)
            else data.get("description")
        )),
        subjects=subjects,
    )
