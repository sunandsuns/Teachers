"""导出 OpenAPI 规范到 JSON。后端契约的机器可读快照。

用途
--------------------------------------------------------------------------
1. **给人看 / 给别的工具吃**：把整份契约导成一个文件，拿去 review，或喂给
   Postman、openapi-generator 之类的外部工具
2. **契约回归**：改动前后各导一份 diff 一下，字段被删、类型被改一眼可见

注意它**不是**前端类型的来源
--------------------------------------------------------------------------
``npm run gen:api``（``packaging/gen_web_types.py``）是**直接 import app 现取**
``app.openapi()`` 的，不读这个文件。刻意如此：多一道中间产物，就多一次"拿着
过期的 JSON 生成出过期的类型"的机会。这个脚本产出的是给人 review 的快照。

输出默认不入库
--------------------------------------------------------------------------
写到项目根的 ``openapi.json``，且已写进 ``.gitignore``（见该文件里那条说明）：
它随时可以重新生成，而**真正的"生成的契约"是 ``web/src/api/types.gen.ts``**——
那份入库，并且有守卫测试盯着它与当前契约一致。

用法
--------------------------------------------------------------------------
    python packaging/export_openapi.py [输出路径]

不传路径时写到项目根的 ``openapi.json``。
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
