"""把前端产物复制到 ``webapp/``，供在线发布使用。

为什么要有这一步
--------------------------------------------------------------------------
发布工具会把某些目录当成构建输出排除掉（``dist`` / ``build`` 这类名字），
而 ``web/dist`` 正好叫 dist——直接发布的话，线上 ``/`` 返回的是 API 信息，
页面根本不在包里。换一个不带这些名字的目录（``webapp``）就绕开了。

于是发布链路是：

    npm run build            # 产出 web/dist
    python packaging/prepare_webapp.py   # 复制一份到 webapp/
    （发布，启动命令带 RSDS_WEB_DIST=webapp）

``webapp/`` 是**产物**，不进仓库（见 ``.gitignore``）。所以每次改了前端、
要重新发布之前，**必须重跑本脚本**——它的存在就是为了让这一步不会被忘掉。
它也会提醒你 ``web/dist`` 是否比前端源码旧。

用法::

    python packaging/prepare_webapp.py          # 复制
    python packaging/prepare_webapp.py --check  # 只检查，不写盘
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIST = ROOT / "web" / "dist"
TARGET = ROOT / "webapp"
WEB_SRC = ROOT / "web" / "src"

#: 产物必须有的入口。缺了它，线上拿到的是一个没有页面的服务。
REQUIRED = ("index.html",)


def _newest_mtime(root: Path) -> float:
    """目录下最新的修改时间；空目录返回 0。"""
    latest = 0.0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not any(p in {".vite", "node_modules"} for p in path.parts):
                latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 web/dist 复制到 webapp/ 供发布使用")
    parser.add_argument("--check", action="store_true", help="只检查，不写盘")
    args = parser.parse_args(argv)

    if not WEB_DIST.is_dir():
        print("[x] 找不到 %s——先在 web/ 里跑 npm run build" % WEB_DIST.relative_to(ROOT))
        return 1

    missing = [name for name in REQUIRED if not (WEB_DIST / name).is_file()]
    if missing:
        print("[x] web/dist 里缺少 %s——构建不完整" % "、".join(missing))
        return 1

    # 提醒"改了前端但没重新构建"。发布出去的是旧界面，比报错更难发现。
    dist_mtime, src_mtime = _newest_mtime(WEB_DIST), _newest_mtime(WEB_SRC)
    if src_mtime > dist_mtime:
        print("[!] web/dist 比 web/src 旧——你改了前端但没重新构建，现在发布的是旧界面")

    if args.check:
        print("[√] web/dist 看起来可用（%d 个文件）" % sum(1 for p in WEB_DIST.rglob("*") if p.is_file()))
        return 0

    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(WEB_DIST, TARGET)

    count = sum(1 for path in TARGET.rglob("*") if path.is_file())
    print("[√] 已复制 %d 个文件到 %s" % (count, TARGET.relative_to(ROOT)))
    print("    发布时启动命令要带：RSDS_WEB_DIST=webapp python -m server.main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
