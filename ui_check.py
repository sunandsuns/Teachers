# -*- coding: utf-8 -*-
"""用 CDP 驱动真实 Chrome，检查页面**渲染出来之后**的样子。

为什么不用 ``chrome --screenshot``：那个模式要么在 load 事件就拍（只能拍到骨架屏），
要么开 ``--virtual-time-budget`` 等数据（但虚拟时间不产生渲染机会，
IntersectionObserver 的回调会被吞掉，于是"滚到才入场"的卡片全部停在 opacity-0，
拍出一张空白页）。两者都会让人误判成 UI 坏了。

这里改走 CDP：先 ``Runtime.evaluate`` 轮询"数据到了没"，再截图。
顺带订阅控制台与网络失败——白屏之外的另一种"不流畅"是页面能看但满屏报错。

用法（需要 run.py 已经把前后端拉起来）::

    python ui_check.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# 与 run.py 的默认前端端口一致。run.py 在端口被占时会自动避让，那时用
# ``UI_FRONT_PORT=5174 python ui_check.py`` 指过来。
FRONT = "http://localhost:%s" % os.environ.get("UI_FRONT_PORT", "5173")
CDP_PORT = 9222

# 截图落到 `.workbuddy/shots/`：那是 .gitignore 里写明的"本地工具目录
# （临时脚本、界面截图）"。脚本本身是 smoke.py 的同级工具，留在根目录；
# 但它的**产物**不入库——十几张 PNG 混进 git 只会让 diff 没法看。
OUT = Path(__file__).resolve().parent / ".workbuddy" / "shots"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# 这些噪音不是页面问题：vite 的 HMR 握手、React DevTools 的提示、
# 以及跳转时被浏览器主动取消的请求（net::ERR_ABORTED 是正常的导航中断）。
NOISE = ("[vite]", "Download the React DevTools", "favicon", "ERR_ABORTED")

# 第 3 段会**故意**用错密码登录一次，好确认后端把错误如实显示出来了。
# 那支 401 是我们想看到的结果，不该被算成"页面报错"。
EXPECTED_401 = "/api/auth/login"


class CDP:
    """极简 CDP 客户端：发一条命令、等它回来，路上收到的通知先攒着。"""

    def __init__(self, url: str):
        from websockets.sync.client import connect

        self.ws = connect(url, max_size=64 * 1024 * 1024)
        self.next_id = 0
        self.events: list[dict] = []

    def send(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv(timeout=30))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def pump(self, seconds: float) -> None:
        """把这段时间里到达的通知收进 ``self.events``。"""
        end = time.time() + seconds
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv(timeout=0.2))
            except TimeoutError:
                continue
            except Exception:
                return
            if "method" in msg:
                self.events.append(msg)

    def evaluate(self, expression: str):
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, timeout: float = 25.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.25)
            try:
                if self.evaluate(expression):
                    return True
            except Exception:
                pass
        return False

    def goto(self, path: str) -> None:
        self.send("Page.navigate", {"url": FRONT + path})
        # 等一次 load；拿不到也无所谓，下面的 wait_for 会兜住
        end = time.time() + 15
        while time.time() < end:
            self.pump(0.2)
            if any(e.get("method") == "Page.loadEventFired" for e in self.events[-12:]):
                break

    def shot(self, name: str) -> None:
        data = self.send("Page.captureScreenshot", {"format": "png"})["data"]
        (OUT / name).write_bytes(base64.b64decode(data))

    def console_problems(self) -> list[str]:
        problems = []
        for event in self.events:
            method = event.get("method")
            params = event.get("params", {})
            if method == "Runtime.consoleAPICalled" and params.get("type") == "error":
                text = " ".join(
                    str(a.get("value", a.get("description", "")))
                    for a in params.get("args", [])
                )
                problems.append("console: " + text)
            elif method == "Log.entryAdded":
                entry = params.get("entry", {})
                if entry.get("level") == "error":
                    # 带上 URL 与状态码：只报"401"没法定位是哪支请求，
                    # 而"哪支请求在匿名状态下被打了 401"才是要判断的事。
                    problems.append("log: %s %s %s" % (
                        entry.get("url", ""), entry.get("text", ""),
                        entry.get("source", "")))
            elif method == "Network.loadingFailed":
                problems.append("network: %s %s" % (
                    params.get("type"), params.get("errorText")))
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                status = response.get("status", 0)
                if status >= 400:
                    problems.append("http %d %s" % (status, response.get("url", "")))
        return [p for p in problems
                if not any(n in p for n in NOISE)
                and not (EXPECTED_401 in p and "401" in p)]


def read_env_file() -> dict:
    """读项目根目录的 ``.env``（``run.py`` 加载的就是它），只为取管理员凭据。

    跟 ``smoke.py`` 一样从脚本自身位置推路径。**不 import 后端模块**：那会把整个
    应用连同索引一起拉起来，而本脚本的定位是"从外面敲门"。

    路径必须相对脚本解析：写死绝对路径的话，仓库挪个位置就会静默退回内置默认值，
    然后以"管理员登录失败"的面目报错，离病因很远。
    """
    values = {}
    path = Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def page_ws_url() -> str | None:
    for _ in range(40):
        try:
            raw = urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % CDP_PORT, timeout=2).read()
            for target in json.loads(raw):
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


# 给 React 受控输入框赋值：直接改 value 不会触发 onChange，
# 必须走原生 setter 再派发 input 事件。
SET_VALUE = """
(function (sel, val) {
  var el = document.querySelector(sel);
  if (!el) return false;
  var setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, val);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})(%s, %s)
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    if chrome is None:
        print("[跳过] 没找到 Chrome/Edge，无法做浏览器层检查")
        return 0

    # profile 目录**跨运行复用**，不删。
    #
    # 原先每次跑都 `rmtree` 重来，图的是"cookie 不残留"：上一次跑完登录成
    # 管理员，下一次进来就"已经是登录状态"，登录门不出现、登录页显示的是
    # "已登录"面板，好几个断言会假通过。这个担心是对的，但为它删掉整个
    # profile 有两个代价：
    #
    #   · 一个 chrome profile 有近千个文件，`rmtree` 会撞上批量删除保护，
    #     脚本直接被拦下来（这是实测到的，不是假想）；
    #   · 那近千个文件里九成是缓存和着色器缓存，跟"干净状态"毫无关系，
    #     每次白等它重建。
    #
    # 真正要清的只有**会话**，而会话就是 cookie——登录态走 httpOnly cookie，
    # 前端刻意没有把 token 落 localStorage（见 `api/client.ts` 的说明）。
    # 所以下面用 CDP 精确清掉 cookie 与站点存储，一个文件都不用动。
    # profile 目录在 `.workbuddy/` 下，本来就不入库。
    profile = str(OUT / ".prof-cdp")
    process = subprocess.Popen([
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-proxy-server", "--proxy-bypass-list=*",
        "--hide-scrollbars", "--window-size=1440,1200",
        "--remote-debugging-port=%d" % CDP_PORT,
        "--user-data-dir=" + profile,
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ok = True
    total = 0
    failed = 0

    def check(label, cond, extra=""):
        nonlocal ok, total, failed
        total += 1
        if not cond:
            ok = False
            failed += 1
        print("  [%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))

    try:
        ws_url = page_ws_url()
        if ws_url is None:
            print("[FAIL] 连不上 Chrome 调试端口")
            return 1
        cdp = CDP(ws_url)
        for domain in ("Page", "Runtime", "Log", "Network"):
            cdp.send(domain + ".enable")
        # 从"没有会话"这个状态开始。profile 是复用的，上一次跑完可能还是
        # 管理员登录态，不清掉的话登录门不出现、登录页直接显示"已登录"面板，
        # 好几个断言会假通过。
        #
        # cookie 走 Network 域；localStorage 里还留着模型设置与语言偏好
        # （`rsds.modelSettings` / `rsds.lang`），一并按源清掉——语言要是
        # 被上一次运行留成英文，后面所有"页面上有某句中文"的断言全会失败。
        cdp.send("Network.clearBrowserCookies")
        try:
            cdp.send("Storage.clearDataForOrigin", {
                "origin": FRONT,
                "storageTypes": "local_storage,session_storage,cookies",
            })
        except RuntimeError:
            # 个别版本的 headless 不认这个域。cookie 已经清过了，
            # 而 localStorage 只有偏好、没有会话，降级不致命。
            pass

        def lands_on(expected, target, timeout=14.0):
            """导航到 `target`，断言浏览器最终停在 `expected`。

            判据里必须带上"这是一份**新**文档"：只看
            `location.pathname === expected` 会被上一页蒙过去——本脚本里相邻两段
            常常起点与终点同名（登录页 → 登录页），下一页还没加载出来就已经
            "通过"了。所以先在当前文档上埋一个记号，新文档读不到它，
            两个条件同时成立才算数。
            """
            cdp.evaluate("window.__staleDoc = true")
            cdp.goto(target)
            return cdp.wait_for(
                "window.__staleDoc === undefined && location.pathname === %s"
                % json.dumps(expected), timeout=timeout)

        print("=== 1. 打开网站第一眼是登录页 ===")
        # 这一段就是需求本身：**未登录的人看到的第一屏是登录页**。
        # 断言的是浏览器地址栏与页面结构，不是"页面上有某个词"——
        # 后者会被顶栏里恰好也写着「登录」的按钮蒙过去。
        cdp.goto("/")
        check("打开首页落在登录页（地址栏 /login）",
              cdp.wait_for("location.pathname === '/login'", timeout=12),
              cdp.evaluate("location.pathname"))
        check("登录页有邮箱与密码输入框",
              cdp.wait_for("!!document.querySelector('input[type=email]') && "
                           "!!document.querySelector('input[type=password]')"))
        # 「独立整屏」的判据是**没有顶栏**：`nav` 住在 `TopBar` 里，是全站唯一的
        # 导航容器。它不在，就说明这一屏没被套进正式界面壳——那排导航在还没登录
        # 的人眼里是七个同样的死胡同，点哪个都会回到这一页。
        check("登录屏不显示顶栏导航（整屏，不是 AppShell）",
              cdp.evaluate("!document.querySelector('nav')"))
        check("登录之前看不到书架内容",
              cdp.evaluate(
                  "document.querySelectorAll('a[href^=\"/books/\"]').length === 0"))
        cdp.pump(0.5)
        cdp.shot("ui-01-login-first.png")

        print()
        print("=== 2. 权限边界：登录之前一个页面也看不了 ===")
        # 门禁是**路由表**上那条 `RequireAuth` 分组，不是各页自己的判断。所以这段
        # 的职责是守住那张清单：哪天把某条路由挪出分组（或加了一条却忘了放进去），
        # 这里就会红——那种错误不会报错，只会安静地对匿名开放。
        #
        # `/` 与 `/books/01` 也在清单里。它们曾经对匿名放行（"书架是门面"），
        # 现在门面换成了登录页本身——能翻书目、能点开读，都是登录之后的事。
        GATED = ("/", "/books/01", "/shelf", "/search", "/knowledge", "/ask",
                 "/history", "/profile", "/insights", "/admin")
        for path in GATED:
            landed = lands_on("/login", path)
            check("匿名进 %s 被送到登录页" % path, landed,
                  cdp.evaluate("location.pathname"))
            check("  %s 送到的那一屏真的能登录（有邮箱框）" % path,
                  cdp.evaluate("!!document.querySelector('input[type=email]')"))
        cdp.pump(0.4)
        cdp.shot("ui-02-boundary-login.png")

        print()
        print("=== 3. 登录页：错误凭据要报错 ===")
        cdp.goto("/login")
        check("登录页有邮箱与密码输入框",
              cdp.wait_for("!!document.querySelector('input[type=email]') && "
                           "!!document.querySelector('input[type=password]')"))
        cdp.evaluate(SET_VALUE % ("'input[type=email]'", "'nobody@example.com'"))
        cdp.evaluate(SET_VALUE % ("'input[type=password]'", "'wrong-password'"))
        cdp.evaluate("document.querySelector('form').requestSubmit()")
        check("错误密码会显示错误提示",
              cdp.wait_for("document.body.innerText.indexOf('邮箱或密码') >= 0 || "
                           "document.body.innerText.indexOf('不正确') >= 0"))
        cdp.pump(0.4)
        cdp.shot("ui-03-login-error.png")

        env = read_env_file()
        admin_email = os.environ.get("RSDS_ADMIN_EMAIL") or env.get(
            "RSDS_ADMIN_EMAIL", "admin@renshengdaoshi.local")
        admin_password = os.environ.get("RSDS_ADMIN_PASSWORD") or env.get(
            "RSDS_ADMIN_PASSWORD", "admin123456")

        print()
        print("=== 3b. 从被拦下的那一页进去：登完回到原地 ===")
        # "登录完成后转跳"最容易断在两处：门没把来路带上，或者登录页跳注册页时
        # 把 `state` 丢了。这里端到端走一遍，断言的是**浏览器地址栏**——
        # 不是"页面上出现了某个词"：后者会被顶栏里恰好也写着「求教」的链接蒙过去。
        cdp.goto("/search")
        check("匿名进 /search 被送到登录页", lands_on("/login", "/search"),
              cdp.evaluate("location.pathname"))
        # 门要把来路带上，登录页才知道该说"回哪儿"。`state` 一丢这条就红。
        check("登录页点名了来路（「登录后回到……」）",
              cdp.wait_for("document.body.innerText.indexOf('登录后回到') >= 0"))

        cdp.wait_for("!!document.querySelector('input[type=email]')")
        cdp.evaluate(SET_VALUE % ("'input[type=email]'", json.dumps(admin_email)))
        cdp.evaluate(SET_VALUE % ("'input[type=password]'", json.dumps(admin_password)))
        cdp.evaluate("document.querySelector('form').requestSubmit()")
        check("登录完回到被拦下那一页",
              cdp.wait_for("location.pathname === '/search'", timeout=15),
              cdp.evaluate("location.pathname"))
        check("管理员登录成功（导航出现「后台」）",
              cdp.wait_for("document.body.innerText.indexOf('后台') >= 0"))
        cdp.pump(0.6)
        cdp.shot("ui-04-logged-in.png")

        print()
        print("=== 4. 后台管理：四个分页逐个切 ===")
        cdp.goto("/admin")
        check("总览渲染出今日计数",
              cdp.wait_for("document.body.innerText.indexOf('今日问答') >= 0"))
        cdp.pump(0.8)
        cdp.shot("ui-05-admin-overview.png")

        # 标签只有四个（ADMIN_TABS = 总览/新书审核/用户/数据库）。逐个点过去，
        # 用 aria-pressed 断言"确实切过去了"——只查"目标词出现了"是不够的：
        # 各面板里都有"用户""表"这类词，点空了也会通过。第一版就在这里把
        # "公共书架"（其实是审核面板里的一小块）当成了标签，点了个寂寞，断言照过。
        #
        # 顺带查**入场方式是否一致**：总览是十二张卡逐张入场（`rise`），
        # 数据库是大块入场（`fade-up`）。断言读的是渲染出来的 `animationName`
        # 而不是元素上的类名——类名挂着但 Tailwind 没生成 CSS 时，页面根本不动，
        # 而类名断言照样通过（这个坑本轮踩过一次，见第 8 段的注释）。
        ENTRANCE = """
        (function (sel) {
          var el = document.querySelector(sel);
          if (!el) return null;
          var cs = window.getComputedStyle(el);
          return { anim: cs.animationName, transform: cs.transform };
        })(%s)
        """

        for tab, marker, probe, expected in (
            ("新书审核", "待审", None, None),
            ("用户", "设为管理员", None, None),
            ("数据库", "rowid", "#main .animate-fade-up", "fade-up"),
            ("总览", "今日问答", "#main .animate-rise", "rise"),
        ):
            clicked = cdp.evaluate(
                "(function(){var b=Array.from(document.querySelectorAll('button'))"
                ".find(e=>e.textContent.trim()===%s);"
                "if(!b) return false; b.click(); return true;})()" % json.dumps(tab))
            cdp.pump(1.2)
            check("能点到「%s」标签" % tab, clicked)
            # 必须限定在**这一组**开关里查 aria-pressed。全文档找第一个
            # `button[aria-pressed=true]` 会命中顶栏的语言切换器（它也这么标），
            # 于是每次都读到「中文」。分段控件的容器是 role=group，
            # 用组内独有的「总览」认出它。
            selected = cdp.evaluate("""
            (function () {
              var groups = Array.from(document.querySelectorAll('[role=group]'));
              for (var i = 0; i < groups.length; i++) {
                if (groups[i].textContent.indexOf('总览') < 0) continue;
                var b = groups[i].querySelector('button[aria-pressed="true"]');
                return b ? b.textContent.trim() : null;
              }
              return null;
            })()
            """)
            check("「%s」成为选中项" % tab, selected == tab, selected)
            check("「%s」显示了本页内容" % tab,
                  cdp.evaluate("document.body.innerText.indexOf(%s) >= 0"
                               % json.dumps(marker)))
            if probe:
                # 要**等目标元素出现**再采，不能点完就采：「数据库」这一页先渲染
                # 一个 `Loading`（它要等 `/admin/tables` 回来才画表格），
                # 点完立刻查只会拿到 null——那是采样时机的问题，不是动画没生效。
                #
                # 演完之后再采也没关系：动画是 `both` 填充，`animationName`
                # 会一直挂在元素上。这条断言要证的是"CSS 真的存在"，
                # 而 `animationName` 恰好就是这件事的证据（缺 CSS 时它是 `none`）。
                appeared = cdp.wait_for(
                    "!!document.querySelector(%s)" % json.dumps(probe), timeout=15)
                entrance = cdp.evaluate(ENTRANCE % json.dumps(probe)) if appeared else None
                got = (entrance or {}).get("anim")
                check("「%s」的入场动画真的生效（%s）" % (tab, expected),
                      got == expected,
                      "animationName=%s transform=%s" % (
                          got, (entrance or {}).get("transform")))
            cdp.shot("ui-06-admin-%s.png" % tab)

        print()
        print("=== 5. 登录之后：书架首页与我的书架都进来了 ===")
        # 这一段是第 2 段的反面。少了它，第 2 段全绿也证明不了任何事——
        # 整站都坏在登录页上时，同样"每一个路径都把人送到登录页"。
        # 书架首页的渲染检查也搬到了这里：它现在得先有会话才看得见。
        cdp.goto("/")
        check("登录后书架首页真的渲染了（不是又弹回登录页）",
              cdp.wait_for(
                  "location.pathname === '/' && "
                  "document.querySelectorAll('a[href^=\"/books/\"]').length >= 15",
                  timeout=15),
              cdp.evaluate("location.pathname"))
        # 别去数 `.opacity-0`：卡片右上那个悬停箭头本来就常驻 opacity-0，
        # 数出来永远不是 0。真正要问的是"用户看得见第一张卡片吗"——
        # 于是把卡片自身与所有祖先的 opacity 乘起来，看有效值是不是 1。
        EFFECTIVE_OPACITY = """
        (function () {
          var el = document.querySelector('a[href^="/books/"]');
          if (!el) return -1;
          var value = 1;
          while (el && el !== document.documentElement) {
            value *= parseFloat(window.getComputedStyle(el).opacity || '1');
            el = el.parentElement;
          }
          return value;
        })()
        """
        check("首张书卡已入场（有效不透明度为 1）",
              cdp.wait_for(EFFECTIVE_OPACITY + " === 1", timeout=10),
              cdp.evaluate(EFFECTIVE_OPACITY))
        title = cdp.evaluate("document.querySelector('h2') && document.querySelector('h2').textContent")
        check("首张卡片有书名", bool(title), title)
        cdp.pump(0.6)
        cdp.shot("ui-07-home-logged-in.png")

        # 停在 /shelf 上、又没有输入框，说明这一页是个空壳（挂在半路），
        # 所以两个条件一起问。
        check("登录后进我的书架不再被拦，且这一页真的渲染了",
              lands_on("/shelf", "/shelf")
              and cdp.wait_for("!!document.querySelector('input')", timeout=10),
              cdp.evaluate("location.pathname"))

        print()
        print("=== 6. 联网检索：上游成败都要给出明确反馈 ===")
        cdp.goto("/shelf")
        cdp.wait_for("!!document.querySelector('input')")
        cdp.evaluate(SET_VALUE % ("'input'", "'活着'"))
        cdp.evaluate(
            "(function(){var b=Array.from(document.querySelectorAll('button'))"
            ".find(e=>e.textContent.trim().indexOf('联网检索')>=0); if(b) b.click();})()")
        # 断言的是**不变量**：点完之后界面必须说点什么——要么候选列表，
        # 要么一句能读懂的错误。上游通不通由网络决定，两种都实测遇到过
        # （走代理时 502 落进错误分支；网络正常时 OpenLibrary 会返回候选），
        # 所以断言不能押在其中一支上，否则换台机器就翻脸。
        #
        # 判据一律用**结构**，不用文案：
        #
        #   · 候选行的形状是"带按钮的 li"——`BookFinder` 里只有它长这样。
        #     早先这里找的是含「加进」的按钮，而真实文案是「加入书架」，
        #     于是上游一通这条就假失败；偏偏上游不通时又会因为走了错误分支
        #     而"通过"——等于这条断言只在坏的那一支上有效，白写。
        #   · 用结构还顺带免疫中英文切换和以后的文案改动。
        HAS_ALERT = "!!document.querySelector('[role=alert]')"
        HAS_CANDIDATES = (
            "Array.from(document.querySelectorAll('ul > li'))"
            ".some(li => li.querySelector('button'))")

        cdp.wait_for("%s || %s" % (HAS_ALERT, HAS_CANDIDATES), timeout=60)
        has_alert = cdp.evaluate(HAS_ALERT)
        has_results = cdp.evaluate(HAS_CANDIDATES)
        check("检索后有明确反馈（候选或错误）", has_alert or has_results,
              "错误提示" if has_alert else ("候选列表" if has_results else "什么都没有"))
        # 这条才是这段的重点：上游失败时**不能**同时显示"没有找到这本书"。
        # 那会把"服务连不上"说成"世上没这本书"，用户会去改书名而不是重试。
        check("上游失败时不谎称「没有找到」",
              not (has_alert and cdp.evaluate(
                  "document.body.innerText.indexOf('没有找到这本书') >= 0")))
        cdp.pump(0.5)
        cdp.shot("ui-08-search-feedback.png")

        print()
        print("=== 7. 书架卡片渲染（经接口放一本书，再看 UI）===")
        added = cdp.evaluate("""
        (async function () {
          var r = await fetch('/api/shelf/books', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
              title: 'UI 检查之书', author: '检查者', year: '2026',
              cover_url: '', source_key: '', source: 'ui_check',
              summary: '这本书由 UI 检查脚本经接口加入，用来确认书架卡片渲染正常。',
              subjects: ['测试'], with_guide: false
            })
          });
          return r.status;
        })()
        """)
        check("经接口加书返回 201", added == 201, added)
        cdp.goto("/shelf")
        on_card = cdp.wait_for(
            "document.body.innerText.indexOf('UI 检查之书') >= 0")
        check("书架卡片渲染出来", on_card)
        # 状态药丸的可读文本就是「想读/在读/读过」，但筛选行里也有同样的词，
        # 所以查 aria-label（`改为「想读」`）——那是卡片上独有的，且顺带确认了
        # 这些药丸对读屏软件是"可操作的"而不是三个摆设。
        check("卡片带三个可切换的阅读状态药丸",
              cdp.evaluate(
                  "['想读','在读','读过'].every(s => "
                  "!!document.querySelector('[aria-label=\"改为「' + s + '」\"]'))"))
        check("卡片标出「仅自己」（默认私有）",
              cdp.evaluate("document.body.innerText.indexOf('仅自己') >= 0"))
        check("卡片给了移出书架与申请公开两个动作",
              cdp.evaluate("document.body.innerText.indexOf('移出书架') >= 0 && "
                           "document.body.innerText.indexOf('申请公开') >= 0"))
        cdp.pump(0.6)
        cdp.shot("ui-09-shelf-card.png")

        print()
        print("=== 8. 换模块的转场 ===")
        # jsdom 不跑 CSS 动画，单元测试只能验证"类名挂对了"。这里量真实曲线：
        # 点一下导航，然后按 ~50ms 一档采 `transform` / `opacity`，
        # 看它是不是真的从位移+透明走到落定。
        PROBE = """
        (function () {
          var frame = document.querySelector('[data-page-frame]');
          if (!frame) return null;
          var cs = window.getComputedStyle(frame);
          return {
            dir: frame.getAttribute('data-page-frame'),
            anim: cs.animationName,
            transform: cs.transform,
            opacity: cs.opacity,
          };
        })()
        """

        def click_and_sample(selector, times=9, gap=0.045):
            """点一个链接，随后连续采样转场框的样式。"""
            cdp.evaluate(
                "(function(){var a=document.querySelector(%s); if(a) a.click();})()"
                % json.dumps(selector))
            out = []
            for _ in range(times):
                out.append(cdp.evaluate(PROBE))
                time.sleep(gap)
            return out

        cdp.goto("/")
        cdp.wait_for("document.querySelectorAll('a[href^=\"/books/\"]').length >= 15")

        samples = click_and_sample('a[href="/ask"]')
        first = samples[0] or {}
        check("向右换模块挂的是 forward 动画",
              first.get("anim") == "stage-forward",
              "%s / %s" % (first.get("dir"), first.get("anim")))
        check("起点是透明的", float(first.get("opacity") or 1) < 1,
              first.get("opacity"))
        check("起点有横向位移", "matrix" in (first.get("transform") or ""),
              first.get("transform"))

        # 落定：末样应该不透明、且变换回到 none（末帧是 `transform: none`，
        # 动画结束后不留包含块，页面里的 sticky 元素才不会被打扰）
        last = samples[-1] or {}
        check("终点完全不透明", float(last.get("opacity") or 0) == 1, last.get("opacity"))
        check("终点变换归零（不留包含块）",
              last.get("transform") in ("none", "matrix(1, 0, 0, 1, 0, 0)"),
              last.get("transform"))
        check("求教页确实渲染出来了",
              cdp.evaluate("document.body.innerText.indexOf('求教') >= 0"))

        # 落定之后不该留下横向滚动条（动画途中那一次在下面第 8 段末尾量，
        # 那时 34px 的溢出才真的存在；这条查的是"收尾干不干净"）。
        check("落定后不残留横向滚动条",
              cdp.evaluate(
                  "document.documentElement.scrollWidth "
                  "<= document.documentElement.clientWidth + 1"))

        # 反向：从求教回书架，应该演 back
        back_first = click_and_sample('a[href="/"]', times=2)[0] or {}
        check("向左换模块挂的是 back 动画",
              back_first.get("anim") == "stage-back",
              "%s / %s" % (back_first.get("dir"), back_first.get("anim")))

        # 纵深：进不在导航上的页面
        cdp.goto("/")
        cdp.wait_for("document.querySelectorAll('a[href^=\"/books/\"]').length >= 15")
        depth_first = click_and_sample('a[href="/books/01"]', times=2)[0] or {}
        check("进不在导航上的页面挂的是 depth 动画",
              depth_first.get("anim") == "stage-depth",
              "%s / %s" % (depth_first.get("dir"), depth_first.get("anim")))

        # 换页要回到顶部：在书架滚下去一点，点导航，新页面该从头看起。
        #
        # 这里**不写死**滚多少像素。视口是 1440x1200，书架撑满也就比视口
        # 多出几十像素，`scrollTo(0, 600)` 会被浏览器夹到真实上限（实测 76），
        # 于是"滚了 600 就该过 100"变成一个跟布局联动的假失败。
        # 滚到文档底部，然后确认它确实动了：如果纹丝不动，说明这一页根本
        # 不滚动，那"换页回顶部"这条断言就是空的，应该报出来而不是假装通过。
        cdp.goto("/")
        cdp.wait_for("document.querySelectorAll('a[href^=\"/books/\"]').length >= 15")
        cdp.pump(0.4)
        cdp.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        cdp.pump(0.35)
        scrolled = cdp.evaluate("window.scrollY")
        check("先确认滚动生效", scrolled > 0,
              "scrollY=%s / 文档高=%s / 视口高=%s" % (
                  scrolled,
                  cdp.evaluate("document.documentElement.scrollHeight"),
                  cdp.evaluate("document.documentElement.clientHeight")))
        click_and_sample('a[href="/ask"]', times=2)
        check("换模块后回到顶部", cdp.evaluate("window.scrollY") == 0,
              cdp.evaluate("window.scrollY"))

        # 首帧不该演：进页面时内容自己会入场，舞台再演一遍是两层叠加
        cdp.goto("/history")
        cdp.wait_for("document.body.innerText.length > 0")
        check("首次进入不演转场动画",
              cdp.evaluate(
                  "(document.querySelector('[data-page-frame]') || {})"
                  ".getAttribute && document.querySelector('[data-page-frame]')"
                  ".getAttribute('data-page-frame') === 'static'"))

        # 视觉留档。
        #
        # 先说清楚一张静图**做不到**什么：转场是"滑 34px + 转 1.8deg"，
        # 幅度是刻意做小的（够让眼睛读出方向就行，不是翻相册），所以任何一张
        # 静图都看不出"动感"。这里不假装能展示动画——它只负责一件事：
        # 证明**动画进行中的那一帧渲染是好的**，没有裁切、没有顶出横向滚动条、
        # 没有把布局挤歪。动感本身由上面那组曲线断言负责。
        #
        # 定格手法：负的 `animation-delay` + `paused`，把动画钉在时间轴的固定
        # 位置上，不跟机器快慢赛跑。（先前试过"放慢 10 倍、等一会儿再拍"：
        # 缓动是 expo-out，前段极快，等 1.1s 时动画已走完八成，拍到的是基本
        # 落定的一页，什么也说明不了。）
        #
        # 每张都**当场量一次**自己被钉在了哪。不量的话，万一定格没生效，
        # 截出来照样是一张好看的图，而这份"证据"是假的——比没有证据更糟。
        FREEZE_CSS = """
        (function (offset) {
          var old = document.getElementById('freeze-motion');
          if (old) old.remove();
          var s = document.createElement('style');
          s.id = 'freeze-motion';
          s.textContent =
            '[data-page-frame] { animation-duration: 3200ms !important;'
            + ' animation-delay: -' + offset + 'ms !important;'
            + ' animation-play-state: paused !important; }';
          document.head.appendChild(s);
        })(%d)
        """

        def translate_x(matrix):
            """从 `matrix()` / `matrix3d()` 里取出 translateX。取不到返回 None。

            注意只扫**括号里面**：`matrix3d` 这个名字本身带个 `3`，
            连名字一起扫的话每个下标都会往后错一位，取出来的是别的分量。
            """
            if not matrix or '(' not in matrix:
                return None
            inner = matrix[matrix.index('(') + 1:matrix.rindex(')')]
            nums = [float(v) for v in
                    re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?', inner)]
            if matrix.startswith('matrix3d') and len(nums) >= 13:
                return nums[12]
            if matrix.startswith('matrix(') and len(nums) >= 5:
                return nums[4]
            return None

        # 转场**途中**也要量一次溢出。横向那 34px 只存在于动画进行时，
        # 等落定再量 `scrollWidth` 是量不到的（那时已经归零），
        # 那条断言就成了摆设——舞台上的 `overflow-x: clip` 到底有没有生效，
        # 只有在动画途中才看得出来。
        GEOMETRY = """
        (function () {
          var doc = document.documentElement;
          return { scrollW: doc.scrollWidth, clientW: doc.clientWidth };
        })()
        """

        def freeze_and_shoot(selector, offset_ms, name):
            """把转场钉在时间轴的 `offset_ms` 处，拍一张，回报钉住的样子。"""
            cdp.evaluate(FREEZE_CSS % offset_ms)
            cdp.evaluate(
                "(function(){var a=document.querySelector(%s); if(a) a.click();})()"
                % json.dumps(selector))
            cdp.pump(0.4)
            frozen = cdp.evaluate(PROBE) or {}
            geo = cdp.evaluate(GEOMETRY) or {}
            cdp.shot(name)
            cdp.evaluate(
                "(function(){var s=document.getElementById('freeze-motion');"
                "if(s) s.remove();})()")
            return frozen, geo

        # 取 160ms / 3200ms = 5% 那一帧：expo-out 前段极快，5% 时已经走完约
        # 七成，于是位移还剩 24px（实测）、不透明度到了 0.28——既看得见内容，
        # 又确实处在"没落定"的状态。再往前挪就基本是全透明，拍出来是白纸。
        cdp.goto("/")
        cdp.wait_for("document.querySelectorAll('a[href^=\"/books/\"]').length >= 15")
        mid, mid_geo = freeze_and_shoot('a[href="/ask"]', 160,
                                        "ui-10-transition-midflight-forward.png")
        check("定格真的钉住了中途那一帧（否则截图是假证据）",
              "matrix" in (mid.get("transform") or "")
              and float(mid.get("opacity") or 1) < 1,
              "transform=%s opacity=%s" % (mid.get("transform"), mid.get("opacity")))
        # 只断言类名是不够的：类名对了、但 transform 写成 0 的话，页面根本不动。
        # 这里直接读**渲染出来**的 translateX，确认它真的往右偏了。
        mid_dx = translate_x(mid.get("transform"))
        check("定格时确实向右偏了（方向不只在类名上）",
              mid_dx is not None and mid_dx > 5, "translateX=%s" % mid_dx)
        check("转场途中没有横向溢出（舞台的 clip 真的生效）",
              mid_geo.get("scrollW", 0) <= mid_geo.get("clientW", 0) + 1,
              "scrollWidth=%s clientWidth=%s" % (
                  mid_geo.get("scrollW"), mid_geo.get("clientW")))

        # 反向也拍一张：内容从**左**边进来，溢出的方向相反。两个方向要
        # 各看一次，因为"顶出横向滚动条"只会在其中一边显形。
        cdp.goto("/ask")
        cdp.wait_for("document.body.innerText.indexOf('求教') >= 0")
        back_mid, back_geo = freeze_and_shoot('a[href="/"]', 160,
                                              "ui-11-transition-midflight-back.png")
        check("反向定格同样钉住了（换边溢出也要看一眼）",
              "matrix" in (back_mid.get("transform") or "")
              and float(back_mid.get("opacity") or 1) < 1,
              "transform=%s opacity=%s" % (
                  back_mid.get("transform"), back_mid.get("opacity")))
        back_dx = translate_x(back_mid.get("transform"))
        check("反向定格确实向左偏了（两个方向是镜像的）",
              back_dx is not None and back_dx < -5, "translateX=%s" % back_dx)
        check("反向途中也没有横向溢出",
              back_geo.get("scrollW", 0) <= back_geo.get("clientW", 0) + 1,
              "scrollWidth=%s clientWidth=%s" % (
                  back_geo.get("scrollW"), back_geo.get("clientW")))

        print()
        print("=== 9. 控制台与网络 ===")
        cdp.pump(1.0)
        problems = cdp.console_problems()
        check("全程没有控制台报错与请求失败", not problems,
              problems[:4] if problems else "")

    finally:
        process.terminate()

    print()
    # 把项数打出来：README 里写着"界面层 N 项"，那个数字靠人肉维护迟早会飘，
    # 让它自己报数，对不上了一眼就能看出来。
    print("=== 结论 === %s（共 %d 项，失败 %d 项）"
          % ("全部通过" if ok else "存在失败项", total, failed))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
