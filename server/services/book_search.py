"""联网书籍检索：OpenLibrary 客户端。

为什么是 OpenLibrary
--------------------------------------------------------------------------
免费、无需 API Key、不必注册。另外两家实测都不行：Google Books 有日配额
（2026-09-24 实测已被用尽，返回 429），豆瓣的 v2 API 需要付费 apikey，
网页版搜索对非浏览器请求直接 403。

一个必须知道的坑
--------------------------------------------------------------------------
``q=`` 参数有 **3 字符下限**——中文书名"活着""三体"只有两个字，会被直接
422 掉（报"Query too short"）。必须走 ``title=`` / ``author=`` 这两个专用
参数，它们没有这个限制。

只拿得到元信息
--------------------------------------------------------------------------
OpenLibrary 不提供全书正文。所以用户书架里的书只有元信息（书名、作者、
年份、封面、简介、主题）加上由模型生成的导读。这不是本模块的缺陷，是
数据源的边界——真要读全文，得去公共书架那边（``books/`` 下的 txt）。

失败即降级
--------------------------------------------------------------------------
与项目其他网络模块一致：不往上抛异常，把原因装进 :attr:`SearchOutcome.error`
交给调用方决定怎么说。检索不到书不该让"添加一本书"这个动作整个失败。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from . import netproxy

#: 检索端点
SEARCH_URL = "https://openlibrary.org/search.json"

#: 单本书的详情端点（``{key}`` 形如 ``/works/OL27448W``）
DETAIL_URL = "https://openlibrary.org{key}.json"

#: 封面图。``{cover}`` 是 OpenLibrary 的 cover id；``-M`` 是中图，
#: 列表里够用且省流量（``-L`` 动辄几百 KB）。
COVER_URL = "https://covers.openlibrary.org/b/id/{cover}-M.jpg"

#: 只取用得上的字段。默认返回体里有几十个字段（各种 id、版本信息），
#: 限定之后响应体小一个量级。
SEARCH_FIELDS = "title,author_name,first_publish_year,cover_i,key,subject"

#: 检索超时。比 LLM 的探活短——用户是在等一个列表，不是在等一份长回答。
TIMEOUT = 12.0

USER_AGENT = "renshengdaoshi/1.0 (personal reading list)"

#: 主题最多留几个。OpenLibrary 的 subject 列表动辄上百条，全存进库没意义。
MAX_SUBJECTS = 8

#: 简介截断长度。详情页的 description 可能上万字，存进库会把列表撑爆。
MAX_SUMMARY = 1200


class BookSearchError(RuntimeError):
    """检索失败。消息是给用户看的中文。"""


@dataclass(frozen=True)
class BookCandidate:
    """一本书的元信息。

    ``source_key`` 是来源方的书目标识（OpenLibrary 的 work id），用来去重与
    回查详情；拿不到时为空串。
    """

    title: str
    author: str = ""
    year: str = ""
    cover_url: str = ""
    source_key: str = ""
    source: str = "openlibrary"
    summary: str = ""
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchOutcome:
    """一次检索的结果。``error`` 非空时 ``results`` 必为空。"""

    results: tuple[BookCandidate, ...] = ()
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _get_json(url: str, opener: Optional[urllib.request.OpenerDirector] = None) -> Any:
    """发一次 GET 并解析 JSON。失败一律转成 :class:`BookSearchError`。"""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with (opener or netproxy.build_opener()).open(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            raise BookSearchError("检索词太短，请把书名或作者写全一些") from exc
        if exc.code == 429:
            raise BookSearchError("检索服务请求过于频繁，请稍后再试") from exc
        if exc.code == 404:
            raise BookSearchError("没有找到这本书的详情") from exc
        raise BookSearchError(f"检索服务返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BookSearchError(f"无法连接检索服务：{exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BookSearchError("检索结果不是合法 JSON") from exc
    except OSError as exc:
        raise BookSearchError(f"网络异常：{exc}") from exc


def _text(value: Any) -> str:
    """把可能是 None / 数字 / 字符串的字段统一成去空白的字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _describe(raw: Any) -> str:
    """提取简介。OpenLibrary 的 description 有两种形态：纯字符串，
    或 ``{"type": "/type/text", "value": "..."}``。"""
    if isinstance(raw, str):
        text = raw.strip()
    elif isinstance(raw, Mapping):
        text = _text(raw.get("value"))
    else:
        text = ""
    if len(text) > MAX_SUMMARY:
        # 在句号/换行处截断，别把一句话砍成两半
        cut = text[:MAX_SUMMARY]
        for mark in ("。", "\n", ". "):
            index = cut.rfind(mark)
            if index > MAX_SUMMARY // 2:
                cut = cut[: index + len(mark)]
                break
        text = cut.rstrip() + "…"
    return text


def _to_candidate(doc: Mapping[str, Any]) -> Optional[BookCandidate]:
    """把 OpenLibrary 的一条 doc 转成 :class:`BookCandidate`。"""
    title = _text(doc.get("title"))
    if not title:
        return None

    raw_authors = doc.get("author_name")
    if isinstance(raw_authors, Sequence) and not isinstance(raw_authors, str):
        # 只留前两位：合著/译者列表可能很长，展示与检索都用不上
        author = "、".join(_text(a) for a in raw_authors[:2] if _text(a))
    else:
        author = _text(raw_authors)

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
        author=author,
        year=_text(doc.get("first_publish_year")),
        cover_url=cover_url,
        source_key=source_key,
        subjects=subjects,
    )


def _query(params: Mapping[str, str], limit: int, opener: Optional[urllib.request.OpenerDirector]) -> SearchOutcome:
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url, opener)
    except BookSearchError as exc:
        return SearchOutcome((), str(exc))

    docs = data.get("docs") if isinstance(data, Mapping) else None
    if not isinstance(docs, list):
        return SearchOutcome((), "检索结果格式异常")

    results: list[BookCandidate] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, Mapping):
            continue
        candidate = _to_candidate(doc)
        if candidate is None:
            continue
        # 同一本书的不同版本（精装/平装/再版）在 OpenLibrary 里可能各占一条，
        # work id 相同。按它去重，列表里才不会出现三行一模一样的书名
        if candidate.source_key and candidate.source_key in seen:
            continue
        if candidate.source_key:
            seen.add(candidate.source_key)
        results.append(candidate)
        if len(results) >= limit:
            break
    return SearchOutcome(tuple(results))


def search_books(
    title: str = "",
    author: str = "",
    *,
    limit: int = 6,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> SearchOutcome:
    """按书名 / 作者检索书籍。

    ``opener`` 只为测试注入，正常调用不必传。

    书名与作者同时给出却一条都没命中时，**退化为只用书名再搜一次**：
    OpenLibrary 的作者名格式很杂（"余华" / "Yu Hua" / "Hua Yu" / 生卒年拼串），
    拿它做 AND 过滤很容易把本该命中的书筛掉。
    """
    clean_title = (title or "").strip()
    clean_author = (author or "").strip()
    if not clean_title and not clean_author:
        return SearchOutcome((), "请至少填写书名或作者")

    params = {"limit": str(limit), "fields": SEARCH_FIELDS}
    if clean_title:
        params["title"] = clean_title
    if clean_author:
        params["author"] = clean_author

    outcome = _query(params, limit, opener)
    if outcome.results or not (clean_title and clean_author):
        return outcome

    return _query(
        {"limit": str(limit), "fields": SEARCH_FIELDS, "title": clean_title}, limit, opener
    )


def fetch_detail(source_key: str, *, opener: Optional[urllib.request.OpenerDirector] = None) -> Optional[BookCandidate]:
    """取一本书的详情（含简介与主题）。

    在用户**选中**某个候选、真正要加进书架时才调——列表阶段多打这几百毫秒
    不值得。失败返回 ``None``：详情是锦上添花，拿不到也该能把书加进去。
    """
    key = (source_key or "").strip()
    if not key:
        return None
    path = key if key.startswith("/") else f"/works/{key}"
    try:
        data = _get_json(DETAIL_URL.format(key=path), opener)
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
        summary=_describe(data.get("description")),
        subjects=subjects,
    )
