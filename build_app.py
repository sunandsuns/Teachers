# -*- coding: utf-8 -*-
"""一键打包：把项目组装成可直接分发的「人生导师」桌面应用。

用法::

    python build_app.py                  # 完整流程（构建前端 → 打包 → 组装 → 实机自检）
    python build_app.py --skip-frontend  # 复用已有的 web/dist
    python build_app.py --no-selftest    # 只出产物，不自检
    python build_app.py --selftest-only  # 不重新打包，只对已有产物做实机自检
    python build_app.py --zip            # 最后压成一个 zip

为什么需要这个脚本
--------------------------------------------------------------------------
PyInstaller 只解决"把 Python 打成 exe"，但一个**能直接交给别人的应用**还需要：

1. **前端先构建**——后端托管的是 ``web/dist``，源码交出去没用；
2. **语料与配置留在 exe 之外**——用户要能自己增补语料、替换 API Key；
3. **一份说明文档**——对方拿到压缩包时不该还得回来问你；
4. **打包后实机自检**——产物启动不了的话，前面三步全是白做。

把它们写成脚本而不是 README 里的步骤清单：少做一步产物就是坏的，
而"照着文档做"恰恰是最容易漏步骤的方式。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "packaging" / "app.spec"
DESKTOP_ENTRY = ROOT / "desktop.py"

DIST_DIR = ROOT / "dist"
WORK_DIR = ROOT / "build"
APP_NAME = "人生导师"
APP_DIR = DIST_DIR / APP_NAME
ZIP_PATH = DIST_DIR / f"{APP_NAME}-桌面版.zip"

WEB_DIR = ROOT / "web"
WEB_DIST = WEB_DIR / "dist"

#: 随包分发的语料目录。改这里就要同步改 packaging/app.spec 的说明与启动说明。
#: ``figures`` 是「最像你的一位历史人物」的名录与画像——放包外同样是为了让用户
#: 自己能加人（加一条记录 + 一张 webp 就行，不必重打包）。
CORPUS_DIRS = ("理解笔记", "books", "MaoZeDongAnthology", "WangYangMing", "figures")
#: 部署态的语料根目录名（server/paths.py 会在 exe 同级找它）
CORPUS_NAME = "corpus"

#: 桌面入口写下的启动日志文件名，与 ``desktop.LOG_FILENAME`` 必须一致。
#: 刻意不 import desktop：那会连带拉起 uvicorn 与 webview，打包脚本只需要这个名字。
LOG_FILENAME = "启动日志.txt"

#: 自检用的固定端口。挑一个不常见的，避免和用户已开的服务撞上。
SELFTEST_PORT = 8791
#: 冷启动要建全量索引，给足余量
SELFTEST_TIMEOUT = 180.0

NODE_FALLBACKS = (
    Path(r"C:\Users\songc\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"),
    Path(r"C:\Program Files\nodejs\node.exe"),
)


# ── 输出 ────────────────────────────────────────────────────────────────


def step(text: str) -> None:
    print("\n\033[36m==> %s\033[0m" % text if os.name != "nt" else "\n==> %s" % text)


def ok(text: str) -> None:
    print("    [OK] %s" % text)


def warn(text: str) -> None:
    print("    [警告] %s" % text)


def fail(text: str) -> None:
    print("    [失败] %s" % text)


# ── 前置检查 ────────────────────────────────────────────────────────────


def _check_environment() -> None:
    """确认当前解释器就是为打包准备的那个环境。

    用错解释器是最常见的坑：拿开发环境的 anaconda 跑，产物会夹带一堆
    无关依赖、体积翻倍，甚至把 numpy/pandas 之类的重型包一起拖进去。
    """
    problems = []
    for module, purpose in (("PyInstaller", "打包"), ("webview", "桌面窗口")):
        try:
            __import__(module)
        except ImportError:
            problems.append("%s（%s 需要）" % (module, purpose))

    if problems:
        fail("当前 Python 环境缺少：%s" % "、".join(problems))
        print("        当前解释器：%s" % sys.executable)
        print("        请改用打包专用环境运行，例如：")
        print(r"          C:\Users\songc\.workbuddy\binaries\python\envs\rsds-build\Scripts\python.exe build_app.py")
        raise SystemExit(1)
    ok("打包环境就绪：%s" % sys.executable)

    if not DESKTOP_ENTRY.is_file():
        fail("找不到入口文件 %s" % DESKTOP_ENTRY)
        raise SystemExit(1)
    if not SPEC.is_file():
        fail("找不到打包配置 %s" % SPEC)
        raise SystemExit(1)


def _find_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    for candidate in NODE_FALLBACKS:
        if candidate.is_file():
            return str(candidate)
    fail("找不到 node，无法构建前端。可用 --skip-frontend 复用已有的 web/dist")
    raise SystemExit(1)


def _ensure_icon() -> None:
    icon = ROOT / "assets" / "app.ico"
    if icon.is_file():
        ok("应用图标：%s" % icon)
        return
    warn("缺少 %s，正在生成" % icon)
    subprocess.run([sys.executable, str(ROOT / "packaging" / "make_icon.py")], check=True)


# ── 前端构建 ────────────────────────────────────────────────────────────


def _archive_web_dist(stamp: str) -> None:
    """把已有的 web/dist 整目录挪走，让 vite 从零开始构建。

    为什么不让 vite 自己清空：``vite build`` 前会 ``emptyDir(outDir)``，而那是一次
    "删掉一批文件"的操作——本机的安全护栏在单次要删的文件数超阈值时会直接拦下，
    构建以 ``SAFE_DELETE_BULK_CONFIRM_REQUIRED`` 失败（assets 里累积到 288 个文件时
    就是这么挂的）。重命名不触发任何删除，旧产物还顺手留了一份可比对的副本。

    旧目录堆在 ``build/prev-webdist-*`` 下，已被 gitignore；体积很小（几百 KB）。
    """
    if not WEB_DIST.is_dir():
        return
    archive = WORK_DIR / f"prev-webdist-{stamp}"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIST.rename(archive)
    ok("旧的前端产物已挪到 %s" % archive.relative_to(ROOT))


def _build_frontend(stamp: str) -> None:
    if not (WEB_DIR / "node_modules").is_dir():
        fail("web/node_modules 不存在，请先在 web/ 下执行 npm install")
        raise SystemExit(1)

    _archive_web_dist(stamp)

    node = _find_node()
    # 直接调 vite 的入口脚本，绕开 npm/npx——少一层进程，也少一类环境变量问题
    vite = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.is_file():
        fail("找不到 %s" % vite)
        raise SystemExit(1)

    result = subprocess.run(
        [node, str(vite), "build"],
        cwd=str(WEB_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        fail("前端构建失败：")
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit(1)

    tail = [line for line in (result.stdout or "").splitlines() if line.strip()][-3:]
    ok("前端构建完成 %s" % ("｜".join(tail) if tail else ""))


def _check_web_dist(skip_build: bool) -> None:
    """确认 web/dist 存在，且不比源码旧。

    dist 过期是很容易犯的错误：改了前端却忘了重新构建，之后所有打包
    都带着旧界面，而打开应用时看起来"一切正常"。
    """
    index = WEB_DIST / "index.html"
    if not index.is_file():
        fail("web/dist/index.html 不存在" + ("（已指定 --skip-frontend）" if skip_build else ""))
        raise SystemExit(1)

    if skip_build:
        newest = 0.0
        for path in (WEB_DIR / "src").rglob("*"):
            if path.is_file():
                newest = max(newest, path.stat().st_mtime)
        for name in ("tailwind.config.js", "index.html", "vite.config.ts"):
            path = WEB_DIR / name
            if path.is_file():
                newest = max(newest, path.stat().st_mtime)

        if newest > index.stat().st_mtime:
            warn("web/dist 比前端源码旧——你改了前端但没重新构建，产物将是旧界面")
        else:
            ok("复用已有的 web/dist（比源码新）")
    else:
        ok("web/dist 已重新构建")


# ── 打包 ────────────────────────────────────────────────────────────────


def _run_pyinstaller(stamp: str) -> None:
    """调用 PyInstaller 生成产物目录，然后换入最终位置。

    为什么要绕这么一圈
    ------------------------------------------------------------------
    PyInstaller 会先**删掉**同名输出目录再重建，而"重建"必然摧毁上一次的
    产物。与其在脚本里主动删目录，这里改用「构建到暂存目录 → 重命名换入」：
    删除掉的重命名是原子操作，失败时旧产物完好无损，而且全程不需要批量删文件。

    顺带把 ``workpath`` 也按下标隔离：PyInstaller 在复用工作目录时会先删
    ``base_library.zip`` 等中间产物，同样属于批量删除。
    """
    staging_dist = DIST_DIR / (".staging-" + stamp)
    work_dir = WORK_DIR / ("app-" + stamp)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--log-level",
        "WARN",
        "--distpath",
        str(staging_dist),
        "--workpath",
        str(work_dir),
        str(SPEC),
    ]
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")

    built = staging_dist / APP_NAME
    if result.returncode != 0 or not (built / f"{APP_NAME}.exe").is_file():
        fail("PyInstaller 打包失败：")
        print((result.stdout or "")[-3000:])
        print((result.stderr or "")[-3000:])
        raise SystemExit(1)

    # 旧产物先挪进 build/（那里本来就只放可丢弃的中间产物），再换入新的。
    # 用带时间戳的名字，避免和上一次的备份相撞。
    if APP_DIR.exists():
        graveyard = WORK_DIR / ("prev-" + stamp)
        graveyard.mkdir(parents=True, exist_ok=True)
        APP_DIR.rename(graveyard / APP_NAME)
        warn("上一次的产物已移到 %s（可随时删除）" % (graveyard / APP_NAME))

    APP_DIR.parent.mkdir(parents=True, exist_ok=True)
    built.rename(APP_DIR)

    warnings = [l for l in (result.stderr or "").splitlines() if "WARNING" in l]
    ok("打包完成，%d 条告警" % len(warnings))
    for line in warnings[:5]:
        print("        %s" % line.strip())


# ── 组装 ────────────────────────────────────────────────────────────────


def _copy_corpus() -> int:
    """把语料复制到 ``corpus/``。

    语料刻意不进包体：它是可增补的数据（新增笔记、扩感悟池），塞进
    PyInstaller 的归档里既让每次启动多解压一份，也堵死了用户自己扩充的路。
    """
    target = APP_DIR / CORPUS_NAME
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    for name in CORPUS_DIRS:
        source = ROOT / name
        if not source.is_dir():
            warn("语料目录缺失，跳过：%s" % name)
            continue
        # dirs_exist_ok：直接覆盖而不是先删再拷。删一个上千文件的目录既慢，
        # 又会在中途失败时留下半个语料——覆盖写没有这个问题。
        #
        # ignore：语料里有几个目录本身是 clone 来的 git 仓库（MaoZeDongAnthology、
        # WangYangMing），直接拷会连 .git 一起带走——几 MB 的对象库对检索毫无用处，
        # 还等于把别人的仓库历史塞进了分发包装。
        shutil.copytree(
            source,
            target / name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        copied += sum(1 for _ in (target / name).rglob("*") if _.is_file())

    ok("语料已复制：%d 个文件 → %s" % (copied, target))
    return copied


def _copy_env() -> bool:
    """复制 ``.env`` 到 exe 同级。

    ``server/paths.py::resolve_env_file`` 在打包态优先读 exe 同级的 ``.env``，
    其次是语料根。放这里是为了让用户一眼找到、方便替换 Key。
    """
    source = ROOT / ".env"
    target = APP_DIR / ".env"

    if source.is_file():
        shutil.copy2(source, target)
        ok("已内置 .env（含 API Key）——注意：拿到包的人可以看到并使用这个 Key")
        return True

    example = ROOT / ".env.example"
    if example.is_file():
        shutil.copy2(example, target)
        ok("未找到 .env，已放入 .env.example（对方填入自己的 Key 即启用 AI 问答）")
    else:
        warn("既无 .env 也无 .env.example，AI 问答将以纯本地检索模式运行")
    return False


def _copy_readme() -> None:
    source = ROOT / "packaging" / "启动说明.txt"
    if source.is_file():
        shutil.copy2(source, APP_DIR / source.name)
        ok("已放入启动说明")
    else:
        warn("缺少 packaging/启动说明.txt，产物里将没有使用说明")


def _report_size() -> None:
    total = 0
    for path in APP_DIR.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    corpus = 0
    for path in (APP_DIR / CORPUS_NAME).rglob("*"):
        if path.is_file():
            corpus += path.stat().st_size
    ok("产物体积：共 %.1f MB（其中语料 %.1f MB）" % (total / 1e6, corpus / 1e6))


# ── 实机自检 ────────────────────────────────────────────────────────────


def _http(url: str, *, timeout: float = 20.0, payload=None):
    """直连本机服务。

    必须用空代理 opener：本机若配了 http_proxy 而 no_proxy 没白名单 127.0.0.1，
    走系统代理会得到 502，自检会误报为"产物有问题"。
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
        return response.status, response.headers.get("content-type", ""), body


class SelfTestResult(NamedTuple):
    """自检结论。

    ``artifact_ok`` **只统计与产物有关的项**：第三方模型端点此刻不可用是常有的事
    （本项目这个端点尤其爱抖），把它算成"产物坏了"会让人对着一个其实没问题的包
    反复重打。外部失败单独列出，结论里说清楚。
    """

    artifact_ok: bool
    external_failures: tuple[str, ...]
    failures: tuple[str, ...]


def _retire_selftest_artifacts() -> None:
    """把自检期间产生的文件挪出产物。

    自检会让 exe 真的跑起来，于是程序目录里多出两样东西：

    - ``data/``：历史记录数据库，还带着一条自检用的求教记录。
      用户打开「回响」看到一条别人的测试记录，比看到空列表更莫名其妙；
    - ``启动日志.txt``：这次自检的启动日志，里面是本机的路径与时间。

    两者都不该跟着分发包走。同理不用删除：改名挪进 ``build/``——本机对批量删除
    有护栏，而且留着便于排查。
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("data", LOG_FILENAME):
        source = APP_DIR / name
        if not source.exists():
            continue
        target = WORK_DIR / ("prev-selftest-%s-%s" % (name, stamp))
        suffix = 0
        while target.exists():
            suffix += 1
            target = WORK_DIR / ("prev-selftest-%s-%s-%d" % (name, stamp, suffix))
        source.rename(target)
        ok("自检产生的 %s 已挪到 %s" % (name, target.relative_to(ROOT)))


def _selftest(run_ask: bool = True) -> SelfTestResult:
    """启动打包好的 exe，逐项验证它真的能用。

    自检覆盖的都是"打包专属"的失败模式——源码态怎么跑都通，
    只有冻成 exe 之后才会暴露：

    - 语料找不到 → 书架空的
    - ``.env`` 读不到 → AI 问答悄悄降级
    - 前端产物没进包 → 窗口一片空白
    - jieba 词典没进包 → 检索悄悄变差
    - sqlite3 没打进包 / 程序目录不可写 → 历史记录一直空的

    自检结束后会把 exe 建出来的 ``data/`` 与 ``启动日志.txt`` 一起挪出产物，
    免得"自检用的求教记录"和本机路径跟着分发包到用户手里。
    """
    exe = APP_DIR / f"{APP_NAME}.exe"
    base = "http://127.0.0.1:%d" % SELFTEST_PORT

    process = subprocess.Popen(
        [str(exe), "--no-window", "--port", str(SELFTEST_PORT)],
        cwd=str(APP_DIR),
    )
    #: (标签, 是否通过, 说明, 是否依赖外部网络)
    checks: list[tuple[str, bool, str, bool]] = []

    def check(label: str, passed: bool, detail: str = "", *, external: bool = False) -> None:
        checks.append((label, passed, detail, external))
        mark = "通过" if passed else ("未通过·外部" if external else "失败")
        print("        [%s] %s %s" % (mark, label, detail))

    try:
        print("        启动中（首次要建全量索引，请稍候）…")
        deadline = time.time() + SELFTEST_TIMEOUT
        healthy = False
        while time.time() < deadline:
            try:
                status, _, body = _http(base + "/api/health", timeout=5)
                if status == 200:
                    healthy = True
                    break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)

        if not healthy:
            check("服务在 %.0fs 内就绪" % SELFTEST_TIMEOUT, False,
                  "详见 %s" % (APP_DIR / "启动日志.txt"))
            return SelfTestResult(False, (), ("服务未就绪",))

        health = json.loads(body)
        check("语料加载完整（15 本书）", health["books_loaded"] == 15,
              "books=%s chapters=%s passages=%s" % (
                  health["books_loaded"], health["total_chapters"], health["total_passages"]))
        check("原典已入检索库（jieba 词典生效）", health["source_indexed"] >= 10,
              "source_indexed=%s" % health["source_indexed"])

        status, content_type, body = _http(base + "/")
        check("前端页面由后端托管", status == 200 and "text/html" in content_type
              and 'id="root"' in body, content_type)

        status, _, body = _http(base + "/books/01")
        check("深链刷新回退到前端", status == 200 and 'id="root"' in body)

        status, _, body = _http(base + "/api/search?q=%E4%B8%8A%E5%96%84%E8%8B%A5%E6%B0%B4&top_k=5")
        results = json.loads(body)["results"]
        check("寻章检索有结果", len(results) > 0, "%d 条" % len(results))

        status, _, body = _http(base + "/api/books/08/source")
        check("原典全文可分块读取", json.loads(body)["total"] > 1000)

        ask_status = json.loads(_http(base + "/api/ask/status")[2])
        check(".env 被读取（AI 问答已启用）", ask_status["enabled"] is True,
              "base_url=%s" % ask_status["base_url"])

        # 历史记录：下载下来直接就能用——库要自己建、自己落位，不需要任何初始化
        history = json.loads(_http(base + "/api/history/status")[2])
        check("历史记录库自动创建", history["available"] is True,
              history.get("error") or history["db_path"])
        check("历史库落在程序目录下（拷贝即迁移）",
              Path(history["db_path"]).resolve().parent == (APP_DIR / "data").resolve(),
              history["db_path"])
        check("保留期半个月", history["retention_days"] == 15,
              "%s 天" % history["retention_days"])

        if run_ask and ask_status["enabled"]:
            started = time.time()
            try:
                _, _, body = _http(
                    base + "/api/ask",
                    timeout=180,
                    payload={"question": "工作中遇到小人怎么办？", "top_k": 3},
                )
                answer = json.loads(body)
                elapsed = time.time() - started
                check("求教能在预算内返回", elapsed < 120, "%.1fs" % elapsed)
                # 这一项依赖第三方端点——它挂了不代表产物有问题，单独归类
                check("内置 Key 真的调通了模型", answer["llm_used"] is True,
                      "model=%s" % (answer["model"] or "(本地检索降级)"), external=True)
                # 求教要顺手记账（无论走没走模型）
                after = json.loads(_http(base + "/api/history?limit=5")[2])
                check("求教已自动记入历史", after["total"] >= 1 and bool(after["items"]),
                      "共 %s 条" % after["total"])
            except Exception as error:  # noqa: BLE001 — 自检不该因单项异常中断
                check("求教接口可用", False, "%s: %s" % (type(error).__name__, error))
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        _retire_selftest_artifacts()

    failures = tuple(c[0] for c in checks if not c[1])
    external = tuple(c[0] for c in checks if not c[1] and c[3])
    return SelfTestResult(not (set(failures) - set(external)), external, failures)


def _conclude(result: SelfTestResult) -> int:
    """打印自检结论并给出退出码。

    产物本身没问题就返回 0——外部端点此刻不通不该拦住分发：包是好的，
    对方用的是自己的网络和 Key。真正要拦的是产物级的失败。
    """
    if not result.artifact_ok:
        print("自检结论：**未通过**，请先解决上面标「失败」的项再分发")
        return 1
    if result.external_failures:
        print("自检结论：产物本身通过 ✓；另有 %d 项依赖第三方模型端点，此刻不通：" % len(
            result.external_failures))
        for label in result.external_failures:
            print("          · %s" % label)
        print("          （与产物无关，不必重打。稍后可用 --selftest-only 复测。）")
        return 0
    print("自检结论：通过 ✓ 可以直接把这个文件夹（或 zip）交给别人")
    return 0


# ── 打包 zip ────────────────────────────────────────────────────────────


def _make_zip() -> None:
    # 不删旧 zip，改名挪走：本机对删除有护栏（删一个几百条目的归档会被判成
    # "批量删除"而直接拦下，整个脚本以非零退出），而重命名不触发任何删除。
    # 顺带把上一版归档留成可比对的副本，和 PyInstaller 输出目录的处理一致。
    if ZIP_PATH.exists():
        retired = WORK_DIR / f"prev-zip-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        ZIP_PATH.rename(retired)
        ok("上一次的分发包已挪到 %s" % retired.relative_to(ROOT))

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in APP_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(DIST_DIR))
    ok("已压缩：%s（%.1f MB）" % (ZIP_PATH, ZIP_PATH.stat().st_size / 1e6))


# ── 主流程 ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包「人生导师」桌面应用")
    parser.add_argument("--skip-frontend", action="store_true", help="复用已有的 web/dist，不重新构建")
    parser.add_argument("--no-selftest", action="store_true", help="跳过打包后的实机自检")
    parser.add_argument("--selftest-only", action="store_true",
                        help="不重新打包，直接对 dist/ 里已有的产物做实机自检")
    parser.add_argument("--no-ask", action="store_true", help="自检时跳过真实问答（省时间）")
    parser.add_argument("--zip", action="store_true", help="最后额外压成 zip")
    args = parser.parse_args(argv)

    #: 本次构建的标记，用于隔离暂存目录与工作目录（见 _run_pyinstaller）
    stamp = time.strftime("%Y%m%d-%H%M%S")

    # 只自检：产物已经在了，重跑一遍 PyInstaller 要几分钟却不会改变什么。
    # 排查"是不是打包坏了"时最常用的一条路径。
    if args.selftest_only:
        exe = APP_DIR / f"{APP_NAME}.exe"
        if not exe.is_file():
            fail("找不到已有产物 %s，请先完整打包一次" % exe)
            return 1
        step("实机自检（复用已有产物）")
        result = _selftest(run_ask=not args.no_ask)
        if args.zip and result.artifact_ok:
            _make_zip()
        print("\n产物目录：%s" % APP_DIR)
        return _conclude(result)

    step("1/6 检查打包环境")
    _check_environment()
    _ensure_icon()

    step("2/6 构建前端")
    if args.skip_frontend:
        _check_web_dist(skip_build=True)
    else:
        _build_frontend(stamp)
        _check_web_dist(skip_build=False)

    step("3/6 PyInstaller 打包")
    _run_pyinstaller(stamp)

    step("4/6 组装语料与配置")
    _copy_corpus()
    _copy_env()
    _copy_readme()
    _report_size()

    step("5/6 实机自检")
    result = SelfTestResult(True, (), ())
    if args.no_selftest:
        warn("已跳过（--no-selftest）")
    else:
        result = _selftest(run_ask=not args.no_ask)

    step("6/6 完成")
    if args.zip and result.artifact_ok:
        _make_zip()
    elif args.zip:
        warn("自检未通过，跳过压缩")

    print("\n产物目录：%s" % APP_DIR)
    return _conclude(result)


if __name__ == "__main__":
    sys.exit(main())
