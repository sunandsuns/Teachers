"""个人书架：加书、列表、改状态、删除、申请公开、用户隔离、多书源检索。

联网检索与详情一律喂固定数据——测试绝不真的去打线上书源。
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from server.routers import shelf as shelf_router
from server.services import book_search
from server.services.book_search import BookCandidate, SearchOutcome

PASSWORD = "goodpass123"
ALICE = "alice@example.com"
BOB = "bob@example.com"

BOOK = BookCandidate(
    title="活着",
    author="余华",
    year="2012",
    cover_url="https://covers.openlibrary.org/b/id/11973290-M.jpg",
    source_key="OL25129388W",
    source="openlibrary",
    summary="一个人和他命运之间的友情。",
    subjects=("Fiction", "China"),
)


def sign_in(client, email):
    """注册并返回该用户的 Authorization 头。

    用 header 而不是 cookie：一个 TestClient 只有一个 cookie jar，测用户隔离时
    两个身份会互相覆盖。
    """
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    token = client.cookies.get("rsds_session")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def offline(monkeypatch):
    """把联网检索与详情换成固定数据。"""
    monkeypatch.setattr(
        book_search, "search_books", lambda title="", author="", **kw: SearchOutcome((BOOK,))
    )
    monkeypatch.setattr(book_search, "fetch_detail", lambda source, key, **kw: None)


def add(client, headers, **overrides):
    payload = {
        "title": BOOK.title,
        "author": BOOK.author,
        "year": BOOK.year,
        "cover_url": BOOK.cover_url,
        "source_key": BOOK.source_key,
        "source": BOOK.source,
        "summary": BOOK.summary,
        "subjects": list(BOOK.subjects),
    }
    payload.update(overrides)
    return client.post("/api/shelf/books", json=payload, headers=headers)


class TestAuthRequired:
    """书架是私人功能，未登录一律 401。"""

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/shelf"),
        ("post", "/api/shelf/search"),
        ("get", "/api/shelf/books/1"),
        ("delete", "/api/shelf/books/1"),
        ("post", "/api/shelf/books/1/submit"),
    ])
    def test_requires_login(self, anon_client, method, path):
        # 用**不带身份**的客户端。默认那个 `client` 是已登录的，拿它来断言 401
        # 只会得到"一个登录用户也能看到自己的书架"——什么也没证明。
        # 只有 post 需要 body；get/delete 不接受 json 参数
        kwargs = {"json": {}} if method == "post" else {}
        resp = getattr(anon_client, method)(path, **kwargs)
        assert resp.status_code == 401


class TestSearch:
    def test_search_returns_candidates(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = client.post("/api/shelf/search", json={"title": "活着", "author": "余华"},
                           headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == ""
        assert len(body["results"]) == 1
        assert body["results"][0]["title"] == "活着"
        assert body["results"][0]["source_key"] == "OL25129388W"

    def test_search_surfaces_upstream_error(self, client, monkeypatch):
        """上游查不到时把原因带给前端，而不是假装"没有结果"。"""
        headers = sign_in(client, ALICE)
        monkeypatch.setattr(
            book_search, "search_books",
            lambda title="", author="", **kw: SearchOutcome((), "检索服务请求过于频繁，请稍后再试"),
        )
        body = client.post("/api/shelf/search", json={"title": "活着"}, headers=headers).json()
        assert body["results"] == []
        assert "频繁" in body["error"]

    def test_unreachable_upstream_is_flagged(self, client, monkeypatch):
        """后端**没走到上游**时要打上 `unavailable`，前端据此改走浏览器直连。

        在线版容器在境内、没有出海代理，到 openlibrary.org 的 TLS 会被直接掐断。
        那种失败不该让"找一本书"整个死掉——浏览器用的是访客自己的网络，而且
        OpenLibrary 的接口放开了 CORS，那条路还通。
        """
        headers = sign_in(client, ALICE)
        monkeypatch.setattr(
            book_search, "search_books",
            lambda title="", author="", **kw: SearchOutcome(
                (), "无法连接检索服务：TLS/SSL connection has been closed (EOF)",
                unavailable=True),
        )
        body = client.post("/api/shelf/search", json={"title": "活着"}, headers=headers).json()
        assert body["results"] == []
        assert body["unavailable"] is True

    def test_business_error_is_not_flagged_unavailable(self, client, monkeypatch):
        """上游答复了（限流、词太短）就不该打这个标记——换个路子重试没有意义。"""
        headers = sign_in(client, ALICE)
        monkeypatch.setattr(
            book_search, "search_books",
            lambda title="", author="", **kw: SearchOutcome((), "检索词太短，请把书名或作者写全一些"),
        )
        body = client.post("/api/shelf/search", json={"title": "活"}, headers=headers).json()
        assert body["unavailable"] is False


class TestUnavailableDetection:
    """`book_search` 自己怎么分辨"没连上上游"与"上游说没有"。

    这一层是给用户措辞的判据：判粗了（把限流也算上）会说成"连不上"；判漏了，
    真断网时又会说成"没有这本书"，让人去改书名而不是重试。
    """

    class _Fail:
        """替身 opener：`open()` 直接抛指定异常。"""

        def __init__(self, exc):
            self.exc = exc

        def open(self, *_args, **_kwargs):
            raise self.exc

    def test_connection_error_is_unavailable(self):
        opener = self._Fail(urllib.error.URLError("TLS/SSL connection has been closed (EOF)"))
        outcome = book_search.search_books("活着", opener=opener)
        assert outcome.unavailable is True
        assert "无法连接检索服务" in outcome.error

    def test_socket_error_is_unavailable(self):
        outcome = book_search.search_books(
            "活着", opener=self._Fail(OSError("network is unreachable")))
        assert outcome.unavailable is True

    def test_gateway_error_is_unavailable(self):
        """502/503/504 是网关替上游回的话，上游本身没通。"""
        opener = self._Fail(
            urllib.error.HTTPError("https://openlibrary.org", 503, "Service Unavailable", {}, None))
        outcome = book_search.search_books("活着", opener=opener)
        assert outcome.unavailable is True

    def test_not_found_is_not_unavailable(self):
        opener = self._Fail(
            urllib.error.HTTPError("https://openlibrary.org", 404, "Not Found", {}, None))
        outcome = book_search.search_books("活着", opener=opener)
        assert outcome.unavailable is False

    def test_rate_limit_is_not_unavailable(self):
        opener = self._Fail(
            urllib.error.HTTPError("https://openlibrary.org", 429, "Too Many Requests", {}, None))
        outcome = book_search.search_books("活着", opener=opener)
        assert outcome.unavailable is False
        assert "频繁" in outcome.error


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class _Routes:
    """按 URL 里的片段返回假响应的 opener。

    比"把整个 opener 换成抛异常的桩"更接近真实：一次检索会**依次问好几个源**，
    得能分别给它们不同的答复。没配到片段的 URL 一律抛网络错——这样"这事只该在那
    种情况下才发生"的判据才立得住（比如"不该去问境外那个源"）。
    """

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.hits: list[str] = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.hits.append(url)
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResponse(json.dumps(payload).encode("utf-8"))
        raise urllib.error.URLError("测试没给这个地址配应答：%s" % url)

    def hit(self, fragment: str) -> bool:
        return any(fragment in url for url in self.hits)


class TestBookSources:
    """多书源：按序试、谁先给出结果用谁、字段怎么映射、什么时候不再往下试。

    全部离线——假 opener 喂固定响应，一次真网络都不打。
    """

    WEREAD_HIT = {
        "books": [
            {
                "bookInfo": {
                    "bookId": "834464",
                    "title": "活着",
                    "author": "余华",
                    "cover": "https://cdn.weread.qq.com/cover/x.jpg",
                    "intro": "  一个人和他命运之间的友情。  ",
                }
            }
        ]
    }

    DOUBAN_HIT = [
        {
            "title": "活着",
            "author_name": "余华",
            "year": "2012",
            "pic": "https://img3.doubanio.com/x.jpg",
            "type": "b",
            "id": "4913064",
        }
    ]

    OPENLIBRARY_HIT = {
        "docs": [
            {
                "title": "Sapiens",
                "author_name": ["Yuval Noah Harari"],
                "first_publish_year": 2011,
                "key": "/works/OL17075760W",
                "cover_i": 8231856,
                "subject": ["History", "Civilization"],
            }
        ]
    }

    def test_weread_fields_are_mapped(self):
        routes = _Routes({"weread.qq.com": self.WEREAD_HIT})
        out = book_search.search_books("活着", opener=routes)

        assert out.ok and len(out.results) == 1
        book = out.results[0]
        assert (book.title, book.author, book.source_key) == ("活着", "余华", "834464")
        assert book.source == "weread"
        assert book.cover_url == "https://cdn.weread.qq.com/cover/x.jpg"
        # 首尾空白被剪掉——直接存进去会让卡片上多出一段莫名的缩进
        assert book.summary == "一个人和他命运之间的友情。"
        # **第一个源命中就不该再问第二个**，否则每次检索都白打一轮请求
        assert not routes.hit("douban.com")

    def test_irrelevant_hits_are_filtered_out(self):
        """微信读书是模糊全文检索，**永不返回空**。

        实测搜「zzqq 不存在的书 xyz」它照样回《第一推动丛书》《不存在的骑士》。
        不拦的话界面上**永远不可能**出现"没有找到这本书"，用户会以为系统坏了。
        """
        routes = _Routes({
            "weread.qq.com": {"books": [{"bookInfo": {"bookId": "1", "title": "第一推动丛书"}}]},
            "douban.com": [],
        })
        out = book_search.search_books("zzqq 不存在的书 xyz", opener=routes)

        assert out.ok, out.error
        assert out.results == ()

    def test_title_gate_also_accepts_an_author_match(self):
        """用户常把作者名敲进书名框——闸门只看书名会把他的书全判成不相关。"""
        routes = _Routes({"weread.qq.com": {"books": [
            {"bookInfo": {"bookId": "1", "title": "活着", "author": "余华"}},
            {"bookInfo": {"bookId": "2", "title": "无关的书", "author": "某人"}},
        ]}})
        out = book_search.search_books("余华", opener=routes)

        assert [c.title for c in out.results] == ["活着"]

    def test_domestic_sources_answer_means_skip_the_overseas_one(self):
        """境内源答复过之后就**不再**去撞境外那个。

        OpenLibrary 在国内是必然超时；前面已经有源明确答复过"我这儿没有"时还去
        撞它，只是把一次 0.2 秒的检索拖成十几秒。
        """
        routes = _Routes({
            "weread.qq.com": {"books": [{"bookInfo": {"bookId": "1", "title": "不相干的书"}}]},
            "douban.com": self.DOUBAN_HIT,
        })
        out = book_search.search_books("活着", opener=routes)

        assert [c.source for c in out.results] == ["douban"]
        assert not routes.hit("openlibrary.org")

    def test_douban_cover_is_dropped_but_year_kept(self):
        """豆瓣封面有防盗链（无 Referer 回 418、外域 Referer 回 403），取回来是裂图。"""
        routes = _Routes({
            "weread.qq.com": urllib.error.URLError("connection refused"),
            "douban.com": self.DOUBAN_HIT,
        })
        out = book_search.search_books("活着", opener=routes)

        assert out.results[0].source == "douban"
        assert out.results[0].cover_url == ""
        assert out.results[0].year == "2012"

    def test_douban_movies_and_music_are_skipped(self):
        """同一个补全接口也混影视/音乐，`type` 不是 `b` 的一律不收。"""
        routes = _Routes({
            "weread.qq.com": urllib.error.URLError("nope"),
            "douban.com": [dict(self.DOUBAN_HIT[0], type="m", title="活着（电影）")],
        })
        out = book_search.search_books("活着", opener=routes)

        assert out.results == ()

    def test_overseas_source_is_used_when_domestic_ones_all_fail(self):
        """境内两条都没答复时才轮到 OpenLibrary——给能出去的机器兜英文书。"""
        routes = _Routes({
            "weread.qq.com": urllib.error.URLError("unreachable"),
            "douban.com": urllib.error.URLError("unreachable"),
            "openlibrary.org/search.json": self.OPENLIBRARY_HIT,
        })
        out = book_search.search_books("Sapiens", opener=routes)

        assert [c.source for c in out.results] == ["openlibrary"]
        book = out.results[0]
        assert (book.year, book.source_key) == ("2011", "OL17075760W")
        assert book.subjects == ("History", "Civilization")

    def test_all_sources_down_flags_unavailable_and_reports_the_first(self):
        routes = _Routes({
            "weread.qq.com": urllib.error.URLError("timed out"),
            "douban.com": urllib.error.URLError("timed out"),
            "openlibrary.org": urllib.error.URLError("timed out"),
        })
        out = book_search.search_books("活着", opener=routes)

        assert out.results == ()
        assert out.unavailable is True
        assert "无法连接检索服务" in out.error

    def test_fetch_detail_only_serves_openlibrary(self):
        """别的源直接返回 None，**一次网络都不发**。

        微信读书的简介在检索响应里就带上了，豆瓣不提供详情——拿它们的 id 去拼
        `/works/…` 只会换来一次超时，把"加入书架"这个动作拖慢十几秒。
        """
        routes = _Routes({})
        assert book_search.fetch_detail("weread", "834464", opener=routes) is None
        assert book_search.fetch_detail("douban", "4913064", opener=routes) is None
        # 空 source（老客户端不发这个字段）同样不猜、不请求
        assert book_search.fetch_detail("", "OL1W", opener=routes) is None
        assert routes.hits == []


class TestAddBook:
    def test_add_and_list(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers)
        assert resp.status_code == 201
        book = resp.json()
        assert book["title"] == "活着"
        assert book["author"] == "余华"
        assert book["status"] == "wish"
        assert book["visibility"] == "private"
        assert book["has_guide"] is False  # 模型未配置，导读留空

        listing = client.get("/api/shelf", headers=headers).json()
        assert listing["total"] == 1
        assert listing["counts"]["wish"] == 1
        assert listing["books"][0]["id"] == book["id"]

    def test_duplicate_is_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        assert add(client, headers).status_code == 201
        resp = add(client, headers)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "duplicate"

    def test_same_book_from_different_users_is_fine(self, client, offline):
        """同一本书两个人各加一份，互不影响。"""
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        assert add(client, alice).status_code == 201
        assert add(client, bob).status_code == 201

    def test_empty_title_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers, title="   ")
        assert resp.status_code == 400

    def test_bad_status_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        resp = add(client, headers, status="whatever")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "bad_status"

    def test_books_without_source_key_do_not_collide(self, client, offline):
        """没有来源标识的书（手工录入）不该因为"key 都是空串"而互相顶掉。"""
        headers = sign_in(client, ALICE)
        assert add(client, headers, title="甲书", source_key="").status_code == 201
        assert add(client, headers, title="乙书", source_key="").status_code == 201
        assert client.get("/api/shelf", headers=headers).json()["total"] == 2

    def test_guide_is_filled_in_the_background(self, client, offline, monkeypatch):
        """模型可用时，后台任务把导读补上。"""
        monkeypatch.setattr(
            shelf_router, "generate_guide", lambda c: ("## 这本书在讲什么\n\n一个普通人的一生。", "test-model")
        )
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]

        fresh = client.get(f"/api/shelf/books/{book_id}", headers=headers).json()
        assert fresh["has_guide"] is True
        assert "普通人的一生" in fresh["guide"]

    def test_guide_failure_does_not_break_add(self, client, offline, monkeypatch):
        """导读生成炸了也不该让加书失败——书已经在架上了。"""
        def boom(candidate):
            raise RuntimeError("模型炸了")

        monkeypatch.setattr(shelf_router, "generate_guide", boom)
        headers = sign_in(client, ALICE)
        resp = add(client, headers)
        assert resp.status_code == 201
        assert resp.json()["has_guide"] is False


class TestListAndUpdate:
    def test_filter_by_status(self, client, offline):
        headers = sign_in(client, ALICE)
        add(client, headers, source_key="A1", title="甲")
        add(client, headers, source_key="A2", title="乙", status="done")

        assert client.get("/api/shelf?status=done", headers=headers).json()["total"] == 1
        assert client.get("/api/shelf?status=wish", headers=headers).json()["total"] == 1
        assert client.get("/api/shelf", headers=headers).json()["total"] == 2

    def test_bad_status_filter_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        assert client.get("/api/shelf?status=nope", headers=headers).status_code == 400

    def test_update_status(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"status": "reading"},
                            headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "reading"
        assert client.get("/api/shelf", headers=headers).json()["counts"]["reading"] == 1

    def test_update_title_and_author(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}",
                            json={"title": "活着（修订版）", "author": "余华 著"}, headers=headers)
        assert resp.json()["title"] == "活着（修订版）"
        assert resp.json()["author"] == "余华 著"

    def test_empty_title_on_update_rejected(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"title": "  "}, headers=headers)
        assert resp.status_code == 400

    def test_delete(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        assert client.delete(f"/api/shelf/books/{book_id}", headers=headers).status_code == 200
        assert client.get("/api/shelf", headers=headers).json()["total"] == 0

    def test_missing_book_is_404(self, client, offline):
        headers = sign_in(client, ALICE)
        assert client.delete("/api/shelf/books/99999", headers=headers).status_code == 404
        assert client.get("/api/shelf/books/99999", headers=headers).status_code == 404


class TestReviewFlow:
    def test_submit_and_cancel(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]

        resp = client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "pending"

        resp = client.post(f"/api/shelf/books/{book_id}/cancel", headers=headers)
        assert resp.json()["visibility"] == "private"

    def test_submit_is_idempotent(self, client, offline):
        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert client.post(
            f"/api/shelf/books/{book_id}/submit", headers=headers
        ).json()["visibility"] == "pending"

    def test_rejected_book_can_apply_again(self, client, offline):
        """驳回不是终局——用户应当有机会改好了再来。"""
        from server.services.user_books import get_user_book_store

        headers = sign_in(client, ALICE)
        book_id = add(client, headers).json()["id"]
        get_user_book_store().review(book_id, approve=False, note="内容太薄")

        assert client.get(f"/api/shelf/books/{book_id}", headers=headers).json()[
            "visibility"] == "rejected"
        resp = client.post(f"/api/shelf/books/{book_id}/submit", headers=headers)
        assert resp.json()["visibility"] == "pending"
        assert resp.json()["review_note"] == ""


class TestIsolation:
    """用户之间的边界。"""

    def test_cannot_see_other_users_books(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        add(client, alice)
        assert client.get("/api/shelf", headers=alice).json()["total"] == 1
        assert client.get("/api/shelf", headers=bob).json()["total"] == 0

    def test_cannot_read_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.get(f"/api/shelf/books/{book_id}", headers=bob).status_code == 404

    def test_cannot_update_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        resp = client.patch(f"/api/shelf/books/{book_id}", json={"status": "done"},
                            headers=bob)
        assert resp.status_code == 404
        # 原主人的数据没被动过
        assert client.get(f"/api/shelf/books/{book_id}", headers=alice).json()["status"] == "wish"

    def test_cannot_delete_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.delete(f"/api/shelf/books/{book_id}", headers=bob).status_code == 404
        assert client.get("/api/shelf", headers=alice).json()["total"] == 1

    def test_cannot_submit_other_users_book(self, client, offline):
        alice, bob = sign_in(client, ALICE), sign_in(client, BOB)
        book_id = add(client, alice).json()["id"]
        assert client.post(
            f"/api/shelf/books/{book_id}/submit", headers=bob
        ).status_code == 404
