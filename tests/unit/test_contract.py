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
