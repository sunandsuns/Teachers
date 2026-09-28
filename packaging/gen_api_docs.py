"""生成中文接口文档（``docs/API.md``）。

为什么要多一份 Markdown
--------------------------------------------------------------------------
契约本来已经有两份：``openapi.json``（机器读）和跑起来之后的 ``/docs``
（Swagger UI，能点着试）。缺的是**能直接读、能进代码评审、能 grep** 的那一份：
把 66 个操作按模块铺开，每个都写清参数范围、响应字段、错误码。

这份文档由 ``app.openapi()`` 现取现生成，**不要手工改**——改了下次生成就没了。
要补说明就补到路由的 docstring 或 Pydantic 字段的 ``description`` 上，
那两处才是契约的一部分，改完两边一起变。

不引第三方文档生成器
--------------------------------------------------------------------------
路由的 docstring 与字段的 description 本来就都是中文、写得也细（这是这个项目
一直的做法），FastAPI 已经把它们原样放进了契约。这里要做的只是排版，外加把
``$ref`` 展开成字段表。多一个依赖换不来更多信息。

用法
--------------------------------------------------------------------------
    python packaging/gen_api_docs.py [输出路径]

不传路径时写到 ``docs/API.md``。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在导入 server.main **之前**设：是否挂载前端产物是**导入时**决定的。
# 仓库里存在 `web/dist` 时 `/` 归 SPA 回退接管，不存在时 `main.py` 才注册根路径
# 那个 API 索引——于是同一份代码，在"构建过前端"的机器上生成 58 条路径、在
# "刚 clone 还没构建"的机器上生成 59 条，而 **`docs/API.md` 是入库的**。
# 定住它，口径与 `tests/conftest.py` 完全一致（那份文档就是照着它写着"留开的口子"）。
os.environ["RSDS_SERVE_FRONTEND"] = "0"

from server.main import APP_VERSION, app  # noqa: E402

METHODS = ("get", "post", "put", "patch", "delete")

#: tag → 中文名。顺序就是文档里章节的顺序，按"用户从哪进来"排：
#: 先登录，再用功能，后台压在最后。
TAG_TITLES: dict[str, str] = {
    "auth": "账号与登录",
    "ask": "求教",
    "history": "回响（问答历史）",
    "profile": "画像",
    "shelf": "我的书架",
    "search": "寻章",
    "books": "原典书架",
    "knowledge base": "知识库",
    "insight": "感悟",
    "admin": "后台管理",
    "system": "系统",
}


# ── 排版小工具 ──────────────────────────────────────────────────────────────


def clean(text: str | None) -> str:
    """docstring ↔ Markdown 的一点换算。

    项目里的注释用 RST 风格的双反引号（``` ``x`` ```）与角色标记
    （``:mod:`a.b```），Markdown 里该是单反引号。不换的话，生成的文档满篇
    都是双反引号——读起来像没渲染的源码。
    """
    if not text:
        return ""
    text = re.sub(r":\w+:`([^`]+)`", r"`\1`", text)
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    return text.strip()


def cell(text: str | None) -> str:
    """表格单元格：换行压成空格、竖线转义。

    不转义竖线的话，描述里出现一个 ``|``（比如"private / pending"写成
    "a|b"）就会把这一行多切出一格，整张表从此错位。
    """
    return clean(text).replace("\n", " ").replace("|", "\\|").strip()


def anchor(text: str) -> str:
    """GitHub 的锚点规则：小写、去掉标点、空格变连字符。中文原样留着。"""
    return re.sub(r"[^\w \-]", "", text.lower()).replace(" ", "-")


def resolve(schema: Any, schemas: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """跟一层 ``$ref``，返回 ``(名字, 真正的 schema)``。

    **只跟一层**：把嵌套对象整个摊平会让每个接口的字段表长到没法读，
    而读者想看的往往只是"这个位置是什么类型"。
    """
    if isinstance(schema, dict) and "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        return name, schemas.get(name, {})
    return None, schema if isinstance(schema, dict) else {}


def type_name(schema: Any) -> str:
    """JSON Schema → 一行类型记法。"""
    if not isinstance(schema, dict):
        return "any"
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            # `Optional[str]` 在契约里是 `anyOf: [string, null]`，渲染成
            # `string | null` 比原样列出两种类型更好读。
            parts = list(dict.fromkeys(type_name(part) for part in schema[key]))
            return " | ".join(parts)
    if "enum" in schema:
        return " | ".join(f"`{value}`" for value in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        return type_name(schema.get("items", {})) + "[]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return f"object<string, {type_name(extra)}>"
        return "object"
    return str(kind) if kind else "any"


def field_table(schema: Any, schemas: dict[str, Any]) -> list[str]:
    """把一个对象的字段展开成表。没有 ``properties`` 就返回空。"""
    _, body = resolve(schema, schemas)
    props = body.get("properties")
    if not isinstance(props, dict) or not props:
        return []
    required = set(body.get("required") or ())
    rows = [
        "| 字段 | 类型 | 必填 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for name, sub in props.items():
        rows.append(
            f"| `{name}` | {type_name(sub)} | {'是' if name in required else ''} "
            f"| {cell(sub.get('description'))} |"
        )
    return rows


def param_table(params: list[dict[str, Any]]) -> list[str]:
    """查询 / 路径参数表。范围与默认值并进说明里——那是调用方最容易踩的两个。"""
    rows = [
        "| 参数 | 位置 | 类型 | 必填 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for param in params:
        schema = param.get("schema") or {}
        extras: list[str] = []
        low, high = schema.get("minimum"), schema.get("maximum")
        if low is not None or high is not None:
            extras.append(f"取值 {low if low is not None else ''}–{high if high is not None else ''}")
        if "default" in schema:
            extras.append(f"默认 {json.dumps(schema['default'], ensure_ascii=False)}")
        note = cell(schema.get("description") or param.get("description"))
        if extras:
            note = "；".join(extras + ([note] if note else []))
        rows.append(
            f"| `{param.get('name')}` | {param.get('in')} | {type_name(schema)} "
            f"| {'是' if param.get('required') else ''} | {note} |"
        )
    return rows


# ── 正文 ────────────────────────────────────────────────────────────────────


def header() -> str:
    return "\n".join([
        "# 人生导师 · 接口文档",
        "",
        f"> 应用版本 **{APP_VERSION}**。本文件由 `packaging/gen_api_docs.py` 从 "
        "`app.openapi()` 生成，**请勿手工编辑**。",
        "",
        "## 怎么用这份文档",
        "",
        "跑起来之后还有一个能点着试的版本：`python run.py` → "
        "<http://127.0.0.1:8000/docs>（Swagger UI）。要机器可读的整份契约，跑 "
        "`python packaging/export_openapi.py` 导出 `openapi.json`。",
        "",
        "### 认证",
        "",
        "**除 `/api/auth/*` 与 `/api/health` 之外，每一个接口都要求登录。**"
        "登录之前连书架和原典都读不到——门禁在路由表上，不在页面上。",
        "",
        "令牌有两条通道，按顺序取：",
        "",
        "1. `rsds_session` **cookie**（浏览器里的正常情况，httpOnly）",
        "2. `Authorization: Bearer <token>`（脚本、桌面客户端）",
        "",
        "### 错误怎么回",
        "",
        "所有出错响应共用一个形状：",
        "",
        "```json",
        '{"detail": {"code": "bad_credentials", "message": "邮箱或密码不正确"}}',
        "```",
        "",
        "`code` 给机器读（按它分支，别去比中文文案——文案会随语言变），"
        "`message` 给人读（可以直接展示）。状态码的含义：",
        "",
        "| 状态码 | 含义 |",
        "| --- | --- |",
        "| `400` | 业务规则不通过，`code` 说明是哪一条 |",
        "| `401` | 未登录或会话已过期 |",
        "| `403` | 已登录但权限不足（后台那组需要管理员） |",
        "| `404` | 目标不存在 |",
        "| `422` | 请求体没通过校验（字段类型、长度、取值） |",
        "| `503` | 数据库不可用，稍后重试 |",
        "",
        "### 降级与\"宁可不降级\"",
        "",
        "这个应用把\"上游挂了\"和\"确实没有\"分得很开，各处的处理**并不一致，是刻意的**：",
        "",
        "- **回响 / 画像 / 书架列表**这类页面能自己说清楚状态，于是上游或库不可用时",
        "  仍返回 `200`，并在响应里带一个 `available: false` 与 `error`——页面据此说",
        "  \"暂时读不到\"，而不是显示成\"你什么都没有\"。",
        "- **后台那组**反过来：宁可 `503`。给管理员看一份空用户列表，他会以为数据没了，",
        "  那比报错危险得多。",
        "",
        "### 分页",
        "",
        "列表接口用 `limit` / `offset`，响应里带 `total`（总条数，与当前页无关）。"
        "上限见各接口的参数表——超了会被夹到上限，不会报错。",
        "",
    ])


def collect(spec: dict[str, Any]) -> list[tuple[str, list[tuple[str, str, dict[str, Any]]]]]:
    """按 tag 归拢操作，顺序按 ``TAG_TITLES``（没列进去的 tag 排在最后）。"""
    buckets: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            tags = operation.get("tags") or ["(other)"]
            buckets.setdefault(tags[0], []).append((method, path, operation))

    order = list(TAG_TITLES)
    ordered = [(tag, buckets.pop(tag)) for tag in order if tag in buckets]
    ordered.extend((tag, ops) for tag, ops in sorted(buckets.items()))
    return ordered


def toc(groups: list[tuple[str, list[Any]]]) -> str:
    lines = ["## 目录", ""]
    for tag, items in groups:
        title = TAG_TITLES.get(tag, tag)
        lines.append(f"- [{title}](#{anchor(title)}) · {len(items)} 个接口")
    lines.append("- [附录：数据模型](#附录数据模型)")
    lines.append("")
    return "\n".join(lines)


def operation_block(method: str, path: str, op: dict[str, Any], schemas: dict[str, Any]) -> str:
    lines = [f"### `{method.upper()}` `{path}`", ""]

    description = clean(op.get("description"))
    if description:
        lines += [description, ""]

    params = [p for p in (op.get("parameters") or []) if p.get("in") != "header"]
    if params:
        lines += ["**参数**", ""] + param_table(params) + [""]

    body_schema = (
        ((op.get("requestBody") or {}).get("content") or {})
        .get("application/json", {})
        .get("schema")
    )
    if body_schema:
        table = field_table(body_schema, schemas)
        if table:
            lines += ["**请求体** `application/json`", ""] + table + [""]

    responses = op.get("responses") or {}
    # 200 排最前，其余按状态码升序——"成功长什么样"是读接口时第一个要找的。
    for code in sorted(responses, key=lambda c: (c != "200", c)):
        response = responses[code] or {}
        text = clean(response.get("description"))
        if text == "Successful Response":
            text = "成功"
        lines += [f"**响应 `{code}`** {text}", ""]
        schema = ((response.get("content") or {}).get("application/json") or {}).get("schema")
        if not schema:
            continue
        name, _ = resolve(schema, schemas)
        if name == "ErrorBody":
            lines += ["错误体，格式见上面的「错误怎么回」。", ""]
            continue
        if name == "HTTPValidationError":
            # FastAPI 自动挂上来的。它那份 schema 描述的是 pydantic 的报错结构
            # 本身，铺成表只会把"这个接口要什么"埋掉。
            lines += [
                "请求体没通过校验：`detail` 里是逐字段的错误（`loc` / `msg` / `type`）。",
                "",
            ]
            continue
        table = field_table(schema, schemas)
        if table:
            lines += table + [""]

    return "\n".join(lines).rstrip() + "\n"


def appendix(schemas: dict[str, Any]) -> str:
    lines = [
        "## 附录：数据模型",
        "",
        "每个接口下面的字段表已经列了用到的模型；这里是全量清单，便于对照。",
        "",
    ]
    for name in sorted(schemas):
        body = schemas[name]
        lines += [f"### `{name}`", ""]
        description = clean(body.get("description"))
        if description:
            lines += [description, ""]
        table = field_table({"$ref": f"#/components/schemas/{name}"}, schemas)
        lines += (table + [""]) if table else ["（无字段，或不是对象。）", ""]
    return "\n".join(lines)


def build(spec: dict[str, Any]) -> str:
    schemas = (spec.get("components") or {}).get("schemas") or {}
    groups = collect(spec)
    parts = [header(), toc(groups)]
    for tag, items in groups:
        parts.append(f"## {TAG_TITLES.get(tag, tag)}\n")
        for method, path, operation in items:
            parts.append(operation_block(method, path, operation, schemas))
    parts.append(appendix(schemas))
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else ROOT / "docs" / "API.md"
    spec = app.openapi()
    text = build(spec)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(target)
    print(f"  {text.count(chr(10)) + 1} 行 / {len(spec.get('paths', {}))} 条路径")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
