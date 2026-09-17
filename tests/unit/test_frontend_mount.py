"""前端同源托管的接入契约。

这套用例刻意**不复用** `tests/conftest.py` 的 `client` 夹具：那里把
``RSDS_SERVE_FRONTEND`` 置为 0，全局 app 根本不挂前端产物，SPA 回退这条路径
在整套测试里零覆盖。`/api/health` 被回退路由截胡返回 HTML 这个 bug，
正是这样漏过去的——所以这里自己按真实顺序装配一个最小 app 来验证。
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from server.web_ui import mount_frontend  # noqa: E402


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """最小前端产物：index.html + assets/ + 一个根目录真实文件。"""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return root


@pytest.fixture
def mounted(dist: Path) -> TestClient:
    """照真实顺序装配：先注册接口，再挂前端。"""
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/books")
    async def books():
        return []

    mount_frontend(app, dist)
    return TestClient(app)


def test_fallback_does_not_swallow_registered_api_routes(mounted: TestClient):
    """核心回归：回退路由必须在所有接口注册**之后**再加。

    反过来写的话 /api/health 会返回 index.html，接口静默失效。
    """
    resp = mounted.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].startswith("application/json")

    assert mounted.get("/api/books").json() == []


def test_unknown_api_path_is_404_not_index_html(mounted: TestClient):
    """拼错的接口要干净地 404。回退成 HTML 会让前端只报一句 JSON 解析错误。"""
    resp = mounted.get("/api/nope")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


def test_deep_link_falls_back_to_index(mounted: TestClient):
    """刷新 /books/01 这类前端深链必须回退到 index.html，否则一按 F5 就 404。"""
    resp = mounted.get("/books/01")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_root_serves_index(mounted: TestClient):
    resp = mounted.get("/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_real_file_wins_over_fallback(mounted: TestClient):
    """dist 里的真实文件优先于回退。"""
    assert "<svg/>" in mounted.get("/favicon.svg").text


def test_assets_mounted(mounted: TestClient):
    resp = mounted.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_traversal_cannot_read_outside_dist(mounted: TestClient, dist: Path):
    """回退分支收到穿越路径时，不能读出 dist 之外的文件。"""
    secret = dist.parent / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")

    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2Fsecret.txt"):
        resp = mounted.get(path)
        assert "TOPSECRET" not in resp.text, f"{path} 读到了 dist 之外的文件"
