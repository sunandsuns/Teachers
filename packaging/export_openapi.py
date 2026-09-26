"""导出 OpenAPI 规范到 JSON。后端契约的机器可读快照。

用途
--------------------------------------------------------------------------
1. **给前端生成类型**（``npm run gen:api`` 调它，见 ``web/scripts/gen-api.mjs``）
2. **契约回归**：提交前跑一次，diff 有变化就说明接口形状被改动了，
   要么是有意的（那就一起提交），要么是不小心的（那就修回来）

用法
--------------------------------------------------------------------------
    python packaging/export_openapi.py [输出路径]

不传路径时写到项目根的 ``openapi.json``。这个文件**可以提交**——它是给
人 review 的，diff 一眼能看出哪个字段被删了。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.main import app  # noqa: E402


def build_spec() -> dict:
    """生成规范。``app.openapi()`` 是纯内存操作，不建库、不发网络请求。"""
    return app.openapi()


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else ROOT / "openapi.json"
    spec = build_spec()
    # **不要 sort_keys**：schema 里 properties 的顺序就是字段在 Pydantic 里的
    # 定义顺序，那是契约的可读性的一部分（生成前端类型时也照它排）。
    target.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    schemas = spec.get("components", {}).get("schemas", {})
    paths = spec.get("paths", {})
    operations = sum(len([m for m in item if m in ("get", "post", "put", "patch", "delete")])
                     for item in paths.values())
    print(f"{target}")
    print(f"  路径 {len(paths)} 条 / 操作 {operations} 个 / schema {len(schemas)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
