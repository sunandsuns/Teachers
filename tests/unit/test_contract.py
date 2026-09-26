"""接口契约的守卫。

这些断言不测业务，测的是**契约有没有漏**：漏了响应模型、漏了错误码、或者改了
``server/schemas/`` 却忘了重新生成前端类型。这类疏漏不会让任何业务测试变红，
只会让接口文档悄悄烂掉、让前端拿着过期的形状干活。

守卫的都是已经踩过的坑：

- ``/api/admin/db/tables/{table}`` 的响应在文档里曾是一个空对象——调用方无从
  知道后台到底给出了什么。
- ``GET /api/admin/users`` 曾在库不可用时 500（静态检查抓不到，只能靠"每个接口
  都要声明错误码"这类约定提醒）。
- ``search.SearchResponse`` 与 ``shelf.SearchResponse`` 曾同名，FastAPI 只好把
  其中一个导出成 ``server__schemas__shelf__SearchResponse``。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Iterator

import pytest

from server.main import app

ROOT = Path(__file__).resolve().parents[2]

#: 对外开放的两个入口，本来就不该有错误码声明
OPEN_ENDPOINTS = {"/", "/api/health"}

METHODS = ("get", "post", "put", "patch", "delete")

#: 声明了其中之一，就算"这组接口的错误码交代过了"
ERROR_CODES = {400, 401, 403, 404, 409, 503}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


def operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """产出 ``(方法 路径, 路径, 操作对象)``。"""
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method in METHODS:
                yield f"{method.upper()} {path}", path, operation


def success_content(operation: dict[str, Any]) -> bool:
    """这个操作有没有一个带响应体的成功状态码。

    不写死 200：新建类接口回的是 201（``POST /api/auth/register`` 之类），
    它们同样要交代返回什么形状。
    """
    for code, response in operation.get("responses", {}).items():
        if code.startswith("2") and response.get("content"):
            return True
    return False


def test_every_operation_declares_a_response_model(spec: dict[str, Any]) -> None:
    """每个接口都要说清自己返回什么形状。"""
    missing = [
        name
        for name, path, operation in operations(spec)
        if path not in OPEN_ENDPOINTS and not success_content(operation)
    ]
    assert not missing, f"这些接口的成功响应没写响应模型：{missing}"


def test_protected_operations_declare_error_codes(spec: dict[str, Any]) -> None:
    """要登录的接口都要声明可能回哪些错误码。"""
    missing = [
        name
        for name, path, operation in operations(spec)
        if path not in OPEN_ENDPOINTS
        and not ERROR_CODES & {int(code) for code in operation.get("responses", {}) if code.isdigit()}
    ]
    assert not missing, f"这些接口没声明任何错误码：{missing}"


def test_every_tag_is_documented(spec: dict[str, Any]) -> None:
    """用到的分组都必须在 ``openapi_tags`` 里有说明，否则 /docs 上是一串光秃秃的英文。"""
    declared = {tag["name"] for tag in spec.get("tags", [])}
    used: set[str] = set()
    for _, _, operation in operations(spec):
        used |= set(operation.get("tags", []))
    assert used <= declared, f"这些分组没在 openapi_tags 里说明：{sorted(used - declared)}"


def test_no_schema_name_collision(spec: dict[str, Any]) -> None:
    """两个 schema 不许重名。

    重名时 FastAPI 会加模块前缀把其中一个改名（``server__schemas__shelf__X``），
    对读文档的人是纯噪音，对生成的客户端是莫名其妙的名字。
    """
    names = list(spec.get("components", {}).get("schemas", {}))
    polluted = [n for n in names if "__" in n]
    assert not polluted, f"有 schema 因重名被加了前缀：{polluted}"


def test_contract_titles_are_unique(spec: dict[str, Any]) -> None:
    """契约上的显示名（``title``）也不能撞——生成前端类型时按它命名。"""
    schemas = spec.get("components", {}).get("schemas", {})
    titles: dict[str, list[str]] = {}
    for key, schema in schemas.items():
        titles.setdefault(schema.get("title", key), []).append(key)
    dup = {t: keys for t, keys in titles.items() if len(keys) > 1}
    assert not dup, f"两个 schema 用了同一个契约名：{dup}"


def test_frontend_types_are_generated_from_current_contract(spec: dict[str, Any]) -> None:
    """``web/src/api/types.gen.ts`` 必须与当前契约一致。

    这是防"改了后端忘了重新生成"。跑 ``npm run gen:api``（或
    ``python packaging/gen_web_types.py``）即可修好。
    """
    path = ROOT / "packaging" / "gen_web_types.py"
    module_spec = importlib.util.spec_from_file_location("_gen_web_types", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    expected = module.generate(spec)
    target = ROOT / "web" / "src" / "api" / "types.gen.ts"
    actual = target.read_text(encoding="utf-8")
    assert actual == expected, (
        "types.gen.ts 与当前契约不一致：改了 server/schemas/ 之后要重新生成"
        "（在 web/ 下跑 `npm run gen:api`）"
    )


# ── 错误面 ──────────────────────────────────────────────────────────────
#
# 契约不只是"有哪些字段、有哪些码"，还包括**出错时回什么形状**。下面四条把
# 错误面钉住：形状统一、库故障按"能不能说清缘由"分两种答复。
#
# 这一节全是已经踩过的坑：错误体曾有三种形状（前端为此写了三段分支去猜）、
# 历史那组声明了永远不会发生的 503（它的响应体里带着 available，库坏了回 200）、
# 后台审计读接口用空列表冒充"从来没操作过"。

#: 库坏了降级成 ``200 + available:false`` 的两组——判据是响应体里**有地方写**
#: ``available``，而不是"这组碰不碰库"。裸列表不行（见 errors.py）。
DEGRADING_PREFIXES = ("/api/history", "/api/profile")


def _broken_db(tmp_path: Path):
    """一个打不开的库。

    路径指向一个**目录**：``sqlite3.connect`` 会以 "unable to open database file"
    失败，于是 ``available`` 为假。比去改文件权限可靠——那在 Windows 上还要应付
    ACL，慢且脆。
    """
    from server.services.db import Database

    return Database(tmp_path)


def test_error_body_is_uniform(client, anon_client) -> None:
    """所有出错响应都是 ``{"detail": {"code", "message"}}``，没有第二种形状。

    四种来源各取一个：未登录（401）、找不到（404）、业务规则不过（400）、
    参数校验失败（422）。**422 也收编**——它原先是 ``[{loc, msg}]`` 数组，
    等于把"自己挑一条"这件事推给每个调用方。
    """
    probes = [
        ("未登录", anon_client.get("/api/history"), "unauthorized"),
        # 路由自己声明了更具体的码时就用它（book_not_found 而不是通用的 not_found）
        ("找不到", client.get("/api/books/nope"), "book_not_found"),
        ("业务规则", client.get("/api/shelf", params={"status": "nope"}), None),
        ("参数校验", client.get("/api/search"), "validation"),
    ]
    for label, response, expected_code in probes:
        body = response.json()
        assert isinstance(body, dict) and set(body) == {"detail"}, (
            f"{label}：顶层应该是且只是 detail，实际是 {body!r}"
        )
        detail = body["detail"]
        assert isinstance(detail, dict), f"{label}：detail 应该是对象，实际是 {detail!r}"
        assert set(detail) == {"code", "message"}, f"{label}：detail 的键不对 {detail!r}"
        assert isinstance(detail["code"], str) and detail["code"], (
            f"{label}：code 不能为空——前端按它分支，不去比文案"
        )
        assert isinstance(detail["message"], str) and detail["message"], (
            f"{label}：message 不能为空，它是要显示给用户的那句话"
        )
        if expected_code is not None:
            assert detail["code"] == expected_code, f"{label}：code 应是 {expected_code}"


def test_degrading_groups_do_not_declare_503(spec: dict[str, Any]) -> None:
    """会降级成 200 的接口不许声明 503。

    ``/api/history`` 与 ``/api/profile`` 的响应体里带着 ``available``，库坏了
    回 200 + ``available:false`` + ``error``。真声明了 503，生成的客户端就会带
    一条永远走不到的分支，读文档的人也会以为"库坏了这页就打不开"。
    """
    wrong = [
        name
        for name, path, operation in operations(spec)
        if path.startswith(DEGRADING_PREFIXES)
        and 503 in {int(code) for code in operation.get("responses", {}) if code.isdigit()}
    ]
    assert not wrong, f"这些接口会降级成 200，却声明了 503：{wrong}"


def test_db_failure_degrades_with_a_reason(client, tmp_path, monkeypatch) -> None:
    """库坏了「回响」回 200，并且在响应体里说清为什么。

    光看状态码不够——降级的**全部意义**是"把读不到与真的没有分开"，所以必须
    同时有 ``available:false`` 与非空的 ``error``。只断言 200 会让"空库"
    与"库坏了"两种情况在测试里长得一模一样。
    """
    from server.services import history as history_module
    from server.services.history import HistoryStore

    monkeypatch.setattr(history_module, "_store", HistoryStore(db=_broken_db(tmp_path)))

    listing = client.get("/api/history")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["available"] is False
    assert body["error"], "既然不可用，就得说清原因"
    assert body["items"] == []

    for path in ("/api/history/status", "/api/history/topics"):
        assert client.get(path).status_code == 200, f"{path} 应当降级而不是报错"


def test_db_failure_returns_503_where_it_cannot_degrade(client, tmp_path, monkeypatch) -> None:
    """不能降级的接口（响应是裸列表/聚合对象）库坏了回 503 加 ``db_unavailable``。

    后台总览是这种：它回的是一个聚合对象，没有地方写"我没读到"，所以只能报错。
    库坏了它以前会 500（未捕获的异常），现在是 503 + 一句稳定的文案。
    """
    from server.services import admin as admin_module
    from server.services.admin import AdminStore

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@test.local", "password": "admin-test-pw"},
    )
    assert login.status_code == 200, login.text
    admin_module.reset_admin_store(AdminStore(db=_broken_db(tmp_path)))

    for path in ("/api/admin/overview", "/api/admin/audit"):
        response = client.get(path)
        assert response.status_code == 503, f"{path} 应当 503，实际 {response.status_code}"
        assert response.json()["detail"]["code"] == "db_unavailable"
