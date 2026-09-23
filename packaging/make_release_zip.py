"""把 ``build_app.py`` 的产物打成可以直接发出去的 zip。

为什么不能直接发 ``build_app.py --zip`` 的那个包
--------------------------------------------------------------------------
``build_app.py`` 会把仓库里的 ``.env``（**含真实密钥**）复制进产物——这是故意的：
不带着真 Key，实机自检里"内置 Key 真的调通了模型"那一条就无从验证。但正因为如此，
**那个包不能对外发**。所以发布链路是两步，中间夹一道替换与扫描：

    build_app.py --skip-frontend --zip --no-ask   # 产物 + 自检（带真 Key）
    python packaging/make_release_zip.py          # 换成 .env.example，扫一遍，压成发布包

这个脚本做四件事：

1. 把产物里的 ``.env`` 换成 ``.env.example``（没有 example 就直接删掉 .env）；
2. **全量扫描**产物与 zip 内层，找形如 ``sk-`` 的密钥残留——"以为换掉了其实
   还留着一份"是这一步唯一真正危险的失败模式，所以要双向确认，不能只信步骤 1；
3. 压成 zip，顶层目录仍是 ``人生导师/``；
4. 用 **ASCII 文件名**命名（``renshengdaoshi-v<版本>-windows-x64.zip``）。
   GitHub 服务端会剥掉附件名里的非 ASCII 字符，中文名会变成只剩 `-` 与 `.zip`。

版本号从 ``server/main.py`` 的 ``APP_VERSION`` 读，不另立一份——两处版本号迟早对不上。

用法::

    python packaging/make_release_zip.py            # 换 .env、扫描、压缩
    python packaging/make_release_zip.py --check    # 只扫描不写盘
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "人生导师"
APP_DIR = ROOT / "dist" / APP_NAME
LEGACY_ZIP = ROOT / "dist" / f"{APP_NAME}-桌面版.zip"
MAIN_PY = ROOT / "server" / "main.py"

#: 真 Key 形如 ``sk-`` 加 32 位以上十六进制。
#: 宁可宽松一点——误报只是多看一眼，漏报是把密钥发到公网。
KEY_RE = re.compile(rb"sk-[0-9a-fA-F]{24,}")

#: 可能在文本文件里留下密钥的后缀（扫描 zip 内层时用）。
SCAN_SUFFIXES = (".env", ".example", ".txt", ".py", ".json", ".md", ".cfg", ".ini", ".toml")


def read_version() -> str:
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', MAIN_PY.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("读不到 APP_VERSION：%s" % MAIN_PY)
    return match.group(1)


def scan_tree(root: Path) -> list[tuple[str, str]]:
    """逐文件找密钥残留，返回 ``[(相对路径, 片段)]``。"""
    hits: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        for match in KEY_RE.finditer(blob):
            hits.append((str(path.relative_to(root)), match.group().decode("ascii", "replace")[:16] + "…"))
    return hits


def strip_key() -> str:
    """把产物里的 ``.env`` 换成不含密钥的一份。返回一句说明，便于日志复述。

    顺带把 ``.env.example`` 也放进去：包里的 ``启动说明.txt`` 与发布说明都会让
    对方"参考同目录的 .env.example"，那就得真的在同目录里。
    """
    env = APP_DIR / ".env"
    example = ROOT / ".env.example"
    if not env.exists():
        return "产物里本来就没有 .env"
    if not example.is_file():
        env.unlink()
        return "没有 .env.example，直接删掉了产物里的 .env"
    shutil.copyfile(example, env)
    shutil.copyfile(example, APP_DIR / ".env.example")
    return "已用 .env.example 覆盖产物里的 .env，并在同目录留了一份 .env.example"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把打包产物做成可发布的 zip")
    parser.add_argument("--check", action="store_true", help="只扫描，不改文件、不压缩")
    args = parser.parse_args(argv)

    if not APP_DIR.is_dir():
        raise SystemExit("找不到产物目录：%s（先跑 build_app.py）" % APP_DIR)

    version = read_version()
    target = ROOT / "dist" / f"renshengdaoshi-v{version}-windows-x64.zip"

    if args.check:
        hits = scan_tree(APP_DIR)
        print("扫描 %s：%s" % (APP_DIR.name, _describe(hits)))
        return 1 if hits else 0

    print(strip_key())

    hits = scan_tree(APP_DIR)
    print("更换后扫描产物：%s" % _describe(hits))

    files = [p for p in APP_DIR.rglob("*") if p.is_file()]
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            zf.write(path, Path(APP_NAME) / path.relative_to(APP_DIR))
    print("已压成：%s（%.1f MB，%d 个文件）" % (
        target.relative_to(ROOT), target.stat().st_size / 1e6, len(files)))

    # 压完再扫一遍 zip 内层。只信"写进去的确实是干净的"，不信上面那一步。
    inner: list[str] = []
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        for name in names:
            if not name.endswith(SCAN_SUFFIXES):
                continue
            if KEY_RE.search(zf.read(name)):
                inner.append(name)
    print("扫描 zip 内层：%s" % ("发现 %d 个文件含可疑密钥！%s" % (len(inner), inner[:5])
                                if inner else "0 处可疑密钥 ✓"))
    print("zip 内配置文件：%s" % [n for n in names if Path(n).name in (".env", ".env.example")])

    # 旧的中文名 zip 容易被误发（GitHub 会把附件名削成 `-.zip`，根本看不出是什么）
    if LEGACY_ZIP.exists():
        LEGACY_ZIP.unlink()
        print("已删掉容易误发的中文名旧包：%s" % LEGACY_ZIP.name)

    return 1 if (hits or inner) else 0


def _describe(hits: list[tuple[str, str]]) -> str:
    if not hits:
        return "0 处可疑密钥 ✓"
    return "发现 %d 处可疑密钥！%s" % (len(hits), hits[:5])


if __name__ == "__main__":
    sys.exit(main())
