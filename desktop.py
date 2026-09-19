"""桌面版入口：把后端与前端合成一个原生窗口应用。

与 ``run.py`` 的区别
--------------------------------------------------------------------------
``run.py`` 面向开发者：拉起 uvicorn 与 Vite 两个进程，端口固定，关掉终端就没了。
这里面向拿到包的人：单进程、自动挑端口、有独立窗口与标题栏。

窗口用系统自带的 WebView2 内核（Windows 10 1803+ 与 Windows 11 均预装），
所以不需要任何额外运行时——这也是不选 Electron / Tauri 的原因：
为了一个已存在的 Python 后端，没必要再拉进一整套 Node 或 Rust 工具链。

用法::

    人生导师.exe                   # 打包后双击
    python desktop.py              # 源码态
    python desktop.py --no-window  # 只起服务并打印地址，便于调试

打包后没有控制台，启动信息与异常一律写进程序目录下的「启动日志.txt」；
排查问题时先看它。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn

from server.paths import PROJECT_ROOT, bundle_dir, is_frozen, resolve_data_dir

#: 注意：``server.main`` 刻意**不在这里导入**。
#: 它会连带导入 jieba，而 jieba 在 import 期就建立带 ``sys.stderr`` 的日志
#: handler；打包态的窗口模式里 ``sys.stderr`` 是 None，那个 handler 就被永久
#: 钉在空流上，之后每次分词都往启动日志里刷一段 AttributeError 回溯，
#: 把真正的错误淹掉。所以必须等日志流重定向完成后再导入（见 ``main``）。

APP_TITLE = "人生导师 · 经典智慧知识库"
HOST = "127.0.0.1"
#: 起始端口：避开 8000/8080 这些常被别的程序占用的位置
DEFAULT_PORT = 8760
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 840
MIN_WINDOW_SIZE = (920, 640)
#: 索引构建耗时随语料增长，给足冷启动余量
READY_TIMEOUT = 120.0
#: 窗口内核探针：重试次数与间隔。次次失败才判定为死，避免误伤慢机器。
PROBE_ATTEMPTS = 6
PROBE_INTERVAL = 1.5
#: 打包态的输出落在这个文件里，出问题时用户可以直接把它发回来
LOG_FILENAME = "启动日志.txt"

#: 启动画面。配色与前端 ``tailwind.config.js`` 对齐（``cinnabar-600`` #a32e22、
#: ``paper-100`` #f6f3ea、``ink-800`` #2f2c27）——**曾经这里用的是 #a63b2a 与
#: #f7f4ec，那是配色表改之前的旧值**，于是启动时和进入后是两种朱砂、两种纸色，
#: 切换的瞬间会明显跳一下。改配色表时这里要一起改。
#:
#: 进度条走的是**渐近曲线**而不是无限循环动画：索引构建实测约 7 秒（几乎全在
#: jieba 分词上），一条永远在来回滑的动画看起来和"卡住了"没有区别。这里让它
#: 按时间逼近上限、并由文案说明正在做什么，真实完成由 ``_wait_ready`` 切页——
#: 所以进度条**不会假称完成**，也不必担心停在 99%。
_SPLASH_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>人生导师</title>
<style>
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; align-items: center; justify-content: center;
    background: #f6f3ea; color: #2f2c27;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    -webkit-user-select: none; user-select: none;
  }
  .frame { text-align: center; width: 232px; }
  .title { font-size: 22px; letter-spacing: 6px; margin: 0 0 10px; font-weight: 500; }
  .hint { font-size: 13px; color: #8a857a; margin: 0; height: 18px; }
  .track { width: 100%; height: 2px; background: #ddd4bd; margin: 18px 0 0; overflow: hidden; }
  .track i { display: block; width: 0; height: 100%; background: #a32e22; transition: width .6s ease-out; }
  .pct { font-size: 11px; color: #b0aca3; margin: 8px 0 0; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
  <div class="frame">
    <h1 class="title">人生导师</h1>
    <p class="hint" id="hint">正在编索引，稍候片刻</p>
    <div class="track"><i id="bar"></i></div>
    <p class="pct" id="pct">0%</p>
  </div>
<script>
// 渐近进度：p = 1 - e^(-t/τ)。τ 取 2.6s，实测 7 秒时约到 93%。
// 上限压到 96%，剩下的留给"真正就绪"那一下——页面切换才是完成信号。
(function () {
  var STAGES = [
    [0,    '正在编索引，稍候片刻'],
    [0.15, '正在读十三部原典'],
    [0.55, '正在读深读笔记'],
    [0.85, '正在计算词频权重']
  ];
  var TAU = 2.6, CEIL = 0.96, start = Date.now();
  var bar = document.getElementById('bar'),
      pct = document.getElementById('pct'),
      hint = document.getElementById('hint'),
      lastStage = -1;

  function tick() {
    var t = (Date.now() - start) / 1000;
    var p = Math.min(CEIL, 1 - Math.exp(-t / TAU));
    bar.style.width = (p * 100).toFixed(1) + '%';
    pct.textContent = Math.round(p * 100) + '%';
    for (var i = STAGES.length - 1; i >= 0; i--) {
      if (p >= STAGES[i][0] && i !== lastStage) {
        hint.textContent = STAGES[i][1];
        lastStage = i;
        break;
      }
    }
    setTimeout(tick, 120);
  }
  tick();
})();
</script>
</body>
</html>"""

_FAIL_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>启动失败</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { display: flex; align-items: center; justify-content: center;
         background: #f7f4ec; color: #3a3630;
         font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
  .frame { text-align: center; max-width: 420px; padding: 0 24px; }
  h1 { font-size: 18px; font-weight: 500; margin: 0 0 12px; }
  p { font-size: 13px; line-height: 1.8; color: #6b655c; margin: 0; }
</style></head>
<body><div class="frame">
<h1>没能启动起来</h1>
<p>后台服务在预期时间内没有就绪。请关闭本窗口后重试；若反复出现，
请确认程序目录下的 corpus 文件夹（语料）是否完整。</p>
</div></body></html>"""


def _setup_logging() -> Optional[Path]:
    """打包态把输出重定向到程序目录下的日志文件。

    桌面版是 ``console=False`` 构建，没有控制台窗口：

    - ``sys.stdout`` / ``sys.stderr`` 在窗口模式下是 ``None``，
      此时任何一次 ``print`` 都会抛 ``AttributeError`` 把启动流程打断；
    - 真出了问题时，用户手上没有任何信息可以反馈，只能描述"打不开"。

    所以冻结态一律落盘。源码态不动，保持终端里的即时反馈。

    调用时机很讲究：必须早于任何可能在 import 期建立日志 handler 的库
    （jieba 就是典型），否则那些 handler 会捕获重定向之前的空流。
    """
    if not is_frozen():
        return None

    target = Path(sys.executable).resolve().parent / LOG_FILENAME
    try:
        stream = open(target, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None

    sys.stdout = stream
    sys.stderr = stream

    # 双保险：重定向之前万一已有 handler 建立（第三方库在 import 期干的），
    # 把它们也改指到新流上，否则日志里只会不停出现 NoneType 回溯。
    import logging

    for handler in logging.root.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(stream)

    print("\n===== %s 启动 =====" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("[人生导师] 语料目录：%s" % PROJECT_ROOT)
    return target


def _notify(message: str, *, error: bool = True) -> None:
    """弹一个原生消息框（源码态退化为打印）。

    ``console=False`` 的可执行文件出错时不会有任何可见输出，用户看到的只是
    "双击没反应"。这种情况下列出原因的唯一通道就是弹框。
    """
    if not is_frozen():
        print(message, file=sys.stderr)
        return
    try:
        import ctypes

        # 0x10 = MB_ICONERROR，0x40 = MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10 if error else 0x40)
    except Exception:  # noqa: BLE001 — 弹框本身失败已无计可施
        pass


def _free_port(preferred: int = DEFAULT_PORT) -> int:
    """挑一个空闲端口。固定端口容易被别的程序占掉，因此向后探测。"""
    for candidate in range(preferred, preferred + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((HOST, candidate))
        except OSError:
            continue
        return candidate
    raise SystemExit("[人生导师] 找不到可用端口，请检查是否有大量程序占用 8760-8809")


class _ThreadedServer(uvicorn.Server):
    """跑在后台线程里的 uvicorn。

    信号处理器只能由主线程安装，而主线程要留给窗口的事件循环，
    所以整个跳过父类的安装动作。
    """

    def install_signal_handlers(self) -> None:
        pass


def _start_server(port: int, application) -> _ThreadedServer:
    """在后台线程启动 uvicorn。

    ``application`` 由调用方传入而不是在这里 import：``server.main`` 必须在
    日志重定向之后才能导入（原因见模块头注释），所以导入时机由 ``main`` 掌握。
    传对象而非导入串，同时也避免了 PyInstaller 的静态分析歧义。
    """
    config = uvicorn.Config(
        application,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = _ThreadedServer(config)
    threading.Thread(target=server.run, name="uvicorn", daemon=True).start()
    return server


def _wait_ready(port: int, timeout: float = READY_TIMEOUT) -> bool:
    """轮询健康检查，直到索引构建完成。

    用空代理 opener：本机若配了 http_proxy 而 no_proxy 没白名单 127.0.0.1，
    直接 urlopen 会被代理拦下返回 502，于是永远等不到"就绪"。

    健康检查在 lifespan 完成后才能应答，因此这里返回 True 时索引已可用，
    窗口跳过去就是能直接用的状态，不会先白屏再慢慢加载。
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://{HOST}:{port}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.25)
    return False


def _resolve_icon() -> str | None:
    """定位窗口图标；缺失不视为错误，用系统默认即可。"""
    candidates = []
    bundle = bundle_dir()
    if bundle is not None:
        candidates.append(bundle / "assets" / "app.ico")
    candidates.append(PROJECT_ROOT / "assets" / "app.ico")
    if is_frozen():
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "app.ico")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _serve_forever(server: _ThreadedServer) -> int:
    """无窗口模式：阻塞直到 Ctrl+C，期间保持服务可用。"""
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[人生导师] 正在停止…")
    finally:
        server.should_exit = True
    return 0


def _probe_window(window, attempts: Optional[int] = None, interval: Optional[float] = None) -> bool:
    """探一探窗口内核是否真的活着。

    窗口建起来 ≠ 页面渲染得出来。WebView2 的浏览器进程若崩掉（安全软件拦截、
    运行时损坏），``load_url`` 只是把消息投出去，一路上不抛任何异常，
    用户看到的就是一个永远停在"正在编索引"的白窗口——而说明书里承诺过
    这种情况下会退回系统浏览器。这个探针就是来兑现那句话的。

    用一次极短的 JS 求值当探针：内核已失效时它会抛
    ``CoreWebView2 is no longer valid``。给若干次重试是为了容错"页面还没渲染完"
    这种正常情况——只要成功过一次就算活着，只有次次都抛才判定为死。
    """
    for _ in range(max(1, attempts or PROBE_ATTEMPTS)):
        time.sleep(PROBE_INTERVAL if interval is None else interval)
        try:
            if window.evaluate_js("1") is not None:
                return True
        except Exception:  # noqa: BLE001 — 探测失败本身就是答案
            continue
    return False


def _fallback_to_browser(url: str, reason: object) -> None:
    """内置窗口不可用时的退路：改用系统浏览器。

    必须**弹一个模态框把进程顶住**：浏览器那一页正是当前进程在服务，
    进程一停页面就白了。冻结态下 ``_notify`` 是阻塞的，弹框在，服务就在；
    用户点掉它才会走到退出。源码态退化为打印，进程本来就随终端活着。
    """
    print(f"[人生导师] 内置浏览器内核不可用：{reason}", file=sys.stderr)
    print(f"[人生导师] 已改用系统浏览器打开：{url}", file=sys.stderr)
    webbrowser.open(url)
    _notify(
        "内置浏览器窗口没能正常显示，已改用你的默认浏览器打开。\n\n"
        f"地址：{url}\n\n"
        "（常用的话可以把该地址存为书签。关闭本提示后应用仍在运行，"
        "不想留着的空白窗口直接关掉即可。）"
    )


def _boot(window, port: int, url: str) -> None:
    """窗口就绪后要做的事：等索引建好 → 载入页面 → 回头看内核有没有崩。

    特意做成模块级函数而不是 ``main`` 里的闭包：白屏兜底那条分支在真实环境里
    极难复现（得有一台 WebView2 坏掉的机器），可它对拿到包的人恰恰最要紧，
    所以必须能用一个假窗口把它测出来。
    """
    if not _wait_ready(port):
        window.load_html(_FAIL_HTML)
        return
    try:
        window.load_url(url)
    except Exception as error:  # noqa: BLE001
        _fallback_to_browser(url, error)
        return
    # load_url 不报错也可能是白屏（内核崩了），所以还得回头看它一眼
    if not _probe_window(window):
        _fallback_to_browser(url, "内置内核没有响应，页面未能渲染")


def main(argv: list[str] | None = None) -> int:
    # 先重定向日志，再导入会建立日志 handler 的模块（见模块头注释）
    log_path = _setup_logging()
    from server.main import app

    parser = argparse.ArgumentParser(description="以桌面窗口运行「人生导师」")
    parser.add_argument("--port", type=int, default=0, help="固定端口；默认自动挑选空闲端口")
    parser.add_argument("--no-window", action="store_true", help="只启动服务不开窗口，便于调试")
    args = parser.parse_args(argv)

    port = args.port or _free_port()
    server = _start_server(port, app)
    url = f"http://{HOST}:{port}/"

    if args.no_window:
        print(f"[人生导师] 服务地址：{url}")
        print(f"[人生导师] 语料目录：{PROJECT_ROOT}")
        # 历史记录库的位置：用户想备份或彻底删掉记录时，得知道它在哪
        print(f"[人生导师] 数据目录：{resolve_data_dir()}")
        if log_path is not None:
            # 冻结态没有控制台，得告诉用户去哪里看地址
            print(f"[人生导师] 以上信息已写入：{log_path}")
        return _serve_forever(server)

    import webview  # 延迟导入：无窗口调试时不必拉起 GUI 依赖

    window = webview.create_window(
        APP_TITLE,
        html=_SPLASH_HTML,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=MIN_WINDOW_SIZE,
        text_select=True,
    )

    def boot() -> None:
        _boot(window, port, url)

    try:
        webview.start(boot, icon=_resolve_icon())
    except Exception as error:  # noqa: BLE001
        # WebView2 内核整体缺失等环境问题：退回系统浏览器，总比彻底打不开强
        if _wait_ready(port):
            _fallback_to_browser(url, error)
            print(
                "[人生导师] 浏览器里看完后，用任务管理器结束「人生导师.exe」即可退出。",
                file=sys.stderr,
            )
            return _serve_forever(server)
        return 1
    finally:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 — 顶层兜底，必须把原因告诉用户
        traceback.print_exc()
        _notify(
            "「人生导师」启动失败：\n\n"
            f"{type(error).__name__}: {error}\n\n"
            f"详细信息见程序目录下的「{LOG_FILENAME}」。"
        )
        raise SystemExit(1)
