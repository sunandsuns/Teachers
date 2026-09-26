"""从后端 OpenAPI 生成前端类型（``web/src/api/types.gen.ts``）。

为什么要有它
--------------------------------------------------------------------------
``web/src/api/types.ts`` 原本是手抄的：585 行、57 个类型。手抄的代价不是
"多打一遍字"，而是**它会和契约分头演化，而且没人能发现**。实测：其中 49 个
类型是后端 schema 的逐字段副本（相似度 1.00、零差异），只是 26 个名字不一样——
同一个形状说了两遍，两边从此可以各自漂移。

现在形状由这里生成，前端不再抄。

一个关键规则：**"有默认值" ≠ "前端可以省"**
--------------------------------------------------------------------------
Pydantic 里 ``figure: FigureInfo = Field(default_factory=FigureInfo)`` 会让
``figure`` 不进 ``required``，但**响应里它永远在**（值可能是空壳对象）。若机械地
按 ``required`` 生成 ``figure?: FigureInfo``，前端那行 ``data.figure.needs_refresh``
立刻变成"可能 undefined"，白报一堆错。

所以判据是**真能否为 null**：

- 类型里含 ``null`` → ``name: T | null``（**必填**：字段总在，值可能是 null）
- 请求体里不在 ``required`` → ``name?: T``（客户端确实可以不传）
- 其余 → 必填

契约名与 Python 类名
--------------------------------------------------------------------------
有些 Python 类带 ``Out`` / ``In`` / ``Model`` / ``Response`` 后缀——那是为了与
``server/services/`` 里同名的领域对象区分（``schemas.ShelfBookOut`` vs
``services.ShelfBook``），属于**后端内部**的区分。接口的消费者没理由知道这事，
所以契约上用的是干净名字，由 ``model_config`` 里的 ``title`` 决定，本脚本读它。

用法
--------------------------------------------------------------------------
    python packaging/gen_web_types.py

输出 ``web/src/api/types.gen.ts``，**不要手改**——要改接口请改 ``server/schemas/``。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.main import app  # noqa: E402

OUT = ROOT / "web" / "src" / "api" / "types.gen.ts"

#: FastAPI 自带的错误模型，不是我们的契约
SKIP = {"HTTPValidationError", "ValidationError"}

#: 「没有前端产物」时才会出现在契约里的东西：``/`` 退化成 API 索引。
#:
#: 有 ``web/dist`` 时同一个路径被 SPA 回退接管，``RootResponse`` 压根不在契约里
#: ——于是同一份源码在两台机器上会生成出不同的前端类型。生成必须稳定，所以一律
#: 按**发布形态**（有 dist）算：前端本来就跑在发布形态里，开发态走 Vite 的 :5173，
#: 根本不经过这个 ``/``。
DEV_ONLY = {"RootResponse"}

#: OpenAPI 的标量类型 → TS
PRIMITIVES = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}

HEADER = """/**
 * 后端接口的数据形状。
 *
 * **本文件由 `python packaging/gen_web_types.py` 自动生成，不要手改。**
 * 要改接口就改 `server/schemas/`，然后重新生成（`npm run gen:api`）。
 *
 * 这里除了从 OpenAPI 直接来的模型，还有生成器补的两块（见生成脚本里的
 * `ENUMS` / `FIELD_TYPES` / `EXTRA_TYPES`）：后端把一些值域写在字段的
 * description 里、类型只写 `str`，前端要能穷尽检查，所以在契约层补上。
 *
 * 纯前端的概念（`SearchKind` 之类）不在这里，在 `./types`。
 */"""

#: 后端 schema 把值域写在 description 里、类型只写 ``str``；前端要能穷尽检查
#: （``switch (node.kind)``），所以在这里补成字面量类型。
#:
#: **为什么不直接把后端改成 ``Literal[...]``**：这些字段有的值来自数据库里的
#: 历史数据（``user_books.status`` 之类），老库里可能存着今天已经不允许的值。
#: 一改成 Literal，response 校验就会在读老数据时失败，把接口变成 500。放在
#: 契约层收窄，最坏也只是"类型说窄了"，不会让请求失败。
ENUMS: dict[str, list[str]] = {
    "Avatar": ["male", "female"],
    "ChatMessageRole": ["system", "user", "assistant"],
    "KbEdgeKind": ["theme", "cross", "part"],
    "KbLinkDirection": ["out", "in"],
    "KbNodeKind": ["book", "theme", "chapter"],
    "SearchResultKind": ["notes", "source", "shelf"],
    "ShelfStatus": ["wish", "reading", "done"],
    "ShelfVisibility": ["private", "pending", "public", "rejected"],
}

#: (契约模型名, 字段名) -> 用哪个类型。模型与字段都必须真实存在，见 ``validate``。
FIELD_TYPES: dict[tuple[str, str], str] = {
    ("ChatMessage", "role"): "ChatMessageRole",
    ("KbEdge", "kind"): "KbEdgeKind",
    ("KbLink", "direction"): "KbLinkDirection",
    ("KbLink", "kind"): "KbEdgeKind",
    ("KbNode", "kind"): "KbNodeKind",
    ("KbNode", "meta"): "KbNodeMeta",
    ("ProfileResponse", "avatar"): "Avatar",
    ("ReviewRow", "visibility"): "ShelfVisibility",
    ("SearchResultItem", "kind"): "SearchResultKind",
    ("ShelfBook", "status"): "ShelfStatus",
    ("ShelfBook", "visibility"): "ShelfVisibility",
}

#: 后端用 ``dict[str, Any]`` 表达、但结构其实固定的东西。**这一块的来源在后端
#: 服务层而不是 schema 里**，所以只能手工维护——它是生成器的输入，不是输出。
EXTRA_TYPES: dict[str, str] = {
    "KbNodeMeta": """\
/** 节点上的附属信息。**按 kind 取用**：书的字段与主题的字段不重叠。
 *
 * 后端把它声明成 `dict[str, Any]`（同一张图里有三类节点，meta 各装各的），
 * 这里写成可选字段集，前端才不用先断言再取键。
 */
export interface KbNodeMeta {
  book_id?: string
  book_title?: string
  chapter_id?: string
  theme?: string
  author?: string
  category?: string
  chapter_count?: number
  has_source?: boolean
}""",
}


def collect_refs(node: Any, acc: set[str] | None = None) -> set[str]:
    """递归收集 ``$ref`` 指向的 schema 名。"""
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            acc.add(ref.rsplit("/", 1)[-1])
        for value in node.values():
            collect_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            collect_refs(value, acc)
    return acc


def request_schema_names(spec: dict) -> set[str]:
    """出现在请求体位置的 schema（含从它引出去的传递闭包）。

    只有这些才允许生成 ``name?: T``——客户端构造请求时可以真的不传。
    响应模型里"不在 required"只意味着"有字段默认值"，值照样会出现。
    """
    schemas = spec.get("components", {}).get("schemas", {})
    seeds: set[str] = set()
    for item in spec.get("paths", {}).values():
        for method, operation in item.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            seeds |= collect_refs(operation.get("requestBody", {}))
    out: set[str] = set()
    stack = list(seeds)
    while stack:
        name = stack.pop()
        if name in out or name not in schemas:
            continue
        out.add(name)
        stack.extend(collect_refs(schemas[name]))
    return out


def split_nullable(node: dict) -> tuple[dict, bool]:
    """剥掉 ``null`` 分支，返回 (剩下的类型, 是否可为 null)。

    Pydantic v2 把 ``Optional[X]`` 写成 ``anyOf: [X, {type: null}]``。
    """
    for key in ("anyOf", "oneOf"):
        branches = node.get(key)
        if not branches:
            continue
        rest = [b for b in branches if not (b.get("type") == "null" and len(b) == 1)]
        nullable = len(rest) != len(branches)
        if len(rest) == 1:
            return rest[0], nullable
        if not rest:
            return {"type": "null"}, True
        return {key: rest}, nullable
    declared = node.get("type")
    if isinstance(declared, list):
        rest = [t for t in declared if t != "null"]
        nullable = "null" in declared
        if len(rest) == 1:
            return {**node, "type": rest[0]}, nullable
        return {**node, "type": rest}, nullable
    return node, False


def needs_parens(ts: str) -> bool:
    """数组的元素类型要不要加括号：只有**顶层**是 union 才要。

    ``Record<string, unknown>`` 不用（``Record<string, unknown>[]`` 是合法的），
    ``A | B`` 要（否则 ``A | B[]`` 的含义是 ``A | (B[])``）。
    """
    depth = 0
    for ch in ts:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        elif ch == "|" and depth == 0:
            return True
    return False


class Renderer:
    def __init__(self, spec: dict) -> None:
        self.schemas: dict[str, dict] = spec.get("components", {}).get("schemas", {})
        #: Python 类名 -> 契约名（``title`` 可能与类名不同，见模块 docstring）
        self.names = {k: (v.get("title") or k) for k, v in self.schemas.items()}
        self.requests = request_schema_names(spec)

    # ── 类型 ────────────────────────────────────────────────────────────

    def ref_name(self, ref: str) -> str:
        key = ref.rsplit("/", 1)[-1]
        return self.names.get(key, key)

    def type_of(self, node: dict, indent: int = 0) -> str:
        if "$ref" in node:
            return self.ref_name(node["$ref"])
        inner, nullable = split_nullable(node)
        base = self._base_type(inner, indent)
        if not nullable:
            return base
        if "|" in base and not base.startswith("("):
            base = f"({base})"
        return f"{base} | null"

    def _base_type(self, node: dict, indent: int) -> str:
        if "$ref" in node:
            return self.ref_name(node["$ref"])

        enum = node.get("enum")
        if isinstance(enum, list) and enum and all(isinstance(v, str) for v in enum):
            return " | ".join(f"'{v}'" for v in enum)

        declared = node.get("type")
        if isinstance(declared, list):
            parts = [PRIMITIVES.get(t, "unknown") for t in declared]
            return " | ".join(dict.fromkeys(parts))

        if declared == "array":
            item = self.type_of(node.get("items", {}), indent)
            if needs_parens(item):
                item = f"({item})"
            return f"{item}[]"

        if declared == "object" or "properties" in node:
            properties = node.get("properties")
            if not properties:
                extra = node.get("additionalProperties")
                if isinstance(extra, dict):
                    return f"Record<string, {self.type_of(extra, indent + 1)}>"
                return "Record<string, unknown>"
            return self._inline_object(node, indent)

        if declared in PRIMITIVES:
            return PRIMITIVES[declared]

        for key in ("anyOf", "oneOf"):
            if key in node:
                parts = [self.type_of(b, indent) for b in node[key]]
                return " | ".join(dict.fromkeys(parts))
        return "unknown"

    def _inline_object(self, schema: dict, indent: int) -> str:
        rows = self.field_lines(schema, indent + 1, is_request=False, model_name="")
        if not rows:
            return "Record<string, unknown>"
        close = "  " * indent
        return "{\n" + "\n".join(rows) + f"\n{close}}}"

    # ── 字段与模型 ──────────────────────────────────────────────────────

    def field_lines(
        self, schema: dict, indent: int, *, is_request: bool, model_name: str
    ) -> list[str]:
        pad = "  " * indent
        required = set(schema.get("required", []))
        out: list[str] = []
        for name, node in schema.get("properties", {}).items():
            _, nullable = split_nullable(node)
            # 可 null 是**必填**（字段总在），只有请求体里可不传的才加 `?`
            optional = (not nullable) and (name not in required) and is_request
            override = FIELD_TYPES.get((model_name, name))
            ts = override or self.type_of(node, indent)
            out.extend(self._jsdoc(node.get("description", ""), pad))
            out.append(f"{pad}{name}{'?' if optional else ''}: {ts}")
        return out

    @staticmethod
    def _jsdoc(text: str, pad: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        # 注释里出现 ``*/`` 会当场把块注释关掉
        text = text.replace("*/", "*\\/")
        rows = text.splitlines()
        if len(rows) == 1:
            return [f"{pad}/** {rows[0]} */"]
        out = [f"{pad}/**"]
        out.extend(f"{pad} * {r}".rstrip() for r in rows)
        out.append(f"{pad} */")
        return out

    def model(self, key: str) -> str:
        schema = self.schemas[key]
        name = self.names[key]
        lines = self._jsdoc(schema.get("description", ""), "")
        if not schema.get("properties"):
            lines.append(f"export type {name} = {self.type_of(schema)}")
            return "\n".join(lines)
        lines.append(f"export interface {name} {{")
        lines.extend(
            self.field_lines(schema, 1, is_request=key in self.requests, model_name=name)
        )
        lines.append("}")
        return "\n".join(lines)

    def validate(self) -> None:
        """``FIELD_TYPES`` 引用的模型、字段、类型必须都真实存在。

        这三张表是手工写在生成器里的，写错了不会有任何反馈——直到前端拿不到
        该有的类型。所以宁可在这里炸掉。
        """
        for (model, field), ts in FIELD_TYPES.items():
            keys = [k for k in self.schemas if self.names[k] == model]
            if not keys:
                raise SystemExit(f"FIELD_TYPES 指向不存在的模型：{model}")
            if field not in self.schemas[keys[0]].get("properties", {}):
                raise SystemExit(f"FIELD_TYPES 指向不存在的字段：{model}.{field}")
            if ts not in ENUMS and ts not in EXTRA_TYPES:
                raise SystemExit(f"FIELD_TYPES 用了未定义的类型：{ts}")


def generate(spec: dict) -> str:
    renderer = Renderer(spec)
    renderer.validate()

    blocks: dict[str, str] = {}
    for name, values in ENUMS.items():
        blocks[name] = f"export type {name} = " + " | ".join(f"'{v}'" for v in values)
    blocks.update(EXTRA_TYPES)

    for key in renderer.schemas:
        if key in SKIP or key in DEV_ONLY:
            continue
        name = renderer.names[key]
        if name in blocks:
            raise SystemExit(f"两个 schema 撞了同一个契约名：{name}（其中一个来自 {key}）")
        blocks[name] = renderer.model(key)

    parts = [HEADER.rstrip()]
    parts.extend(blocks[name] for name in sorted(blocks))
    return "\n\n".join(parts) + "\n"


def main() -> int:
    text = generate(app.openapi())
    OUT.write_text(text, encoding="utf-8")
    total = text.count("\nexport interface ") + text.count("\nexport type ")
    print(f"{OUT}")
    print(f"  {total} 个类型 / {len(text.splitlines())} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
