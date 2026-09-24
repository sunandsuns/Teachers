# -*- coding: utf-8 -*-
"""冒烟验证：run.py 默认端口(后端 8000 / 前端 5173) 的前后端联调链路。

覆盖：健康检查与语料规模 → 前端页面可编译 → vite 代理转发 →
寻章检索命中古籍 → 原典分块读取 → 求教（含 LLM 状态）→ 回响（历史记录）→
画像（形象与归纳）→ 历史人物名录与画像文件 → 阅读页章节链路 → 感悟页筛选 →
知识库（双链与关系图谱）→ 账号 / 我的书架 / 后台管理（含按用户隔离）→ 错误路径。

所有请求都走 vite 代理（``localhost:5173``），即浏览器实际使用的那条链路；
后端 API 直连只用于 A 段，以便区分"后端故障"与"代理故障"。

注意：本机 Vite 绑定 IPv6，且环境 http_proxy 会拦截 127.0.0.1，
因此浏览器侧一律用 localhost；后端 API 直连用 127.0.0.1。
"""
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FRONT = "http://localhost:5173"
BACK = "http://127.0.0.1:8000"

# 一次求教最多会花掉后端的 LLM_TOTAL_BUDGET（默认 45s），再加上检索与落库的时间。
# 套接字超时必须比它宽——**比预算还短的超时会以"卡死"收场**，而真实原因只是
# 我们等得不够久。本文件曾在这里写 40，上游稍慢就必然失败。
ASK_TIMEOUT = 150
# 探活有独立的预算（PROBE_BUDGET，约 20s），等它用不着那么久
PROBE_TIMEOUT = 40

# 后端直连不能走环境代理
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, timeout=20):
    return opener.open(url, timeout=timeout).read().decode("utf-8")


def wait(url, label, tries=40):
    for _ in range(tries):
        try:
            return get(url)
        except Exception:
            time.sleep(1)
    raise SystemExit("[FAIL] %s 未就绪: %s" % (label, url))


def read_env_file():
    """读项目根目录的 ``.env``（``run.py`` 加载的就是它）。

    只为取管理员凭据。**不 import 后端模块**：那会把整个应用连同索引一起拉起来，
    而冒烟脚本的定位是"从外面敲门"，它不该对被测进程的内部结构有任何依赖。
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


class Session:
    """带 cookie 的会话。

    登录状态靠 httpOnly cookie 传递，而 ``urllib`` 默认**不**保存 cookie——
    用裸 ``opener`` 发两次请求，第二次就是未登录。这个类把 cookie jar 与
    "发一次 JSON 请求"这两件事包在一起，各段只关心路径与载荷。
    """

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.jar),
        )

    def call(self, path, method="GET", payload=None, timeout=30):
        """返回 ``(状态码, 解析后的响应体)``。**HTTP 错误不抛**。

        4xx/5xx 在这个脚本里是**被断言的对象**（匿名 401、非管理员 403、
        保护表 400），抛异常就没法检查它们了。
        """
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            FRONT + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=timeout) as resp:
                body = resp.read().decode()
                return resp.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, body

    def clear(self):
        """丢掉全部 cookie，回到匿名。"""
        self.jar.clear()


def fetch_module(path):
    """取一个前端模块的**转译结果**，返回 ``(状态码, 正文)``。

    ``Session.call`` 会把响应当 JSON 解析，而 vite 转译出来的是 JS 文本，所以另起一个。
    这里问的是"浏览器打开这个页面时会不会白屏"：vite 是按需转译的，
    模块里但凡有个写错的 import 或 JSX 语法问题，这里就会拿到 500。
    """
    try:
        with opener.open(FRONT + path, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main():
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

    print("=== A. 后端直连 127.0.0.1:8000 ===")
    wait(BACK + "/api/health", "后端")
    h = json.loads(get(BACK + "/api/health"))
    check("健康检查 status", h["status"] == "ok", h["status"])
    check("书目数 == 15", h["books_loaded"] == 15, h["books_loaded"])
    check("章节数 == 352", h["total_chapters"] == 352, h["total_chapters"])
    check("检索段落数 > 8000", h["total_passages"] > 8000, h["total_passages"])
    check("类目含「历史文献」", "历史文献" in h["categories"], h["categories"])
    check("有原典的书 == 13", h.get("books_with_source") == 13, h.get("books_with_source"))
    check("原典已入检索库 >= 10", h.get("source_indexed", 0) >= 10, h.get("source_indexed"))
    check("超大书跳过索引", "史记" in h.get("source_skipped", []) and
          "资治通鉴" in h.get("source_skipped", []), h.get("source_skipped"))

    books = json.loads(get(BACK + "/api/books"))
    no_source = [b["title"] for b in books if not b["has_source"]]
    check("07–15 均含原典", not [t for t in no_source if t not in ("毛泽东选集", "王阳明心学")],
          "无原典：%s" % (no_source or "无"))

    print()
    print("=== B. 前端 dev server localhost:5173 ===")
    html = wait(FRONT + "/", "前端")
    check("index.html 含 #root", 'id="root"' in html)
    app = get(FRONT + "/src/App.tsx")
    check("App.tsx 已转译", ("jsx" in app))
    check("含寻章路由 /search", "/search" in app)
    check("含画像路由 /profile", "/profile" in app)
    check("含知识库路由 /knowledge", "/knowledge" in app)
    check("含我的书架路由 /shelf", "/shelf" in app)
    check("含后台路由 /admin", "/admin" in app)
    check("含登录路由 /login", "/login" in app)

    # 路由"已声明"和"页面能打开"是两件事：App.tsx 里写了 lazy(() => import(...))，
    # 就算被 import 的那个文件编译不过，App.tsx 依然"含 /shelf"。所以这里把新页面
    # 逐个拉一遍——vite 是按需转译的，能拿到 200 就说明这个模块真的编得过。
    for module in (
        "/src/pages/Shelf.tsx",
        "/src/pages/Admin.tsx",
        "/src/pages/Login.tsx",
        "/src/pages/Register.tsx",
        "/src/features/auth/AuthPage.tsx",
        "/src/features/shelf/ShelfPage.tsx",
        "/src/features/shelf/BookFinder.tsx",
        "/src/features/admin/AdminPage.tsx",
        "/src/features/admin/DatabasePanel.tsx",
    ):
        code, body = fetch_module(module)
        check("vite 能转译 %s" % module, code == 200, "" if code == 200 else code)

    print()
    print("=== C. 经 vite 代理访问后端（前端真实链路）===")
    h2 = json.loads(get(FRONT + "/api/health"))
    check("代理 /api/health 通", h2["books_loaded"] == 15)

    r = json.loads(
        get(FRONT + "/api/search?q=" + urllib.parse.quote("知行合一") + "&top_k=3")
    )["results"]
    check("寻章检索有结果", len(r) > 0)
    for x in r:
        print("        [%.3f] %s" % (x["score"], x["source"]))

    q = urllib.parse.quote("才者，德之资也")
    r2 = json.loads(get(FRONT + "/api/search?q=" + q + "&top_k=3"))["results"]
    hit_hist = any(x["book_id"] in ("13", "14", "15") for x in r2)
    check("古籍检索命中历史文献类目", hit_hist, [x["source"] for x in r2])

    # 原典检索：一句原经文应能命中「原典」而非仅笔记
    r3 = json.loads(
        get(FRONT + "/api/search?q=" + urllib.parse.quote("上善若水") + "&top_k=8")
    )["results"]
    kinds = {x["kind"] for x in r3}
    check("检索结果含 kind 字段", kinds <= {"notes", "source"}, kinds)
    check("检索能命中原典", "source" in kinds,
          [(x["kind"], x["source"]) for x in r3 if x["kind"] == "source"][:2])

    r4 = json.loads(
        get(FRONT + "/api/search?q=" + urllib.parse.quote("上善若水")
            + "&top_k=8&kind=source")
    )["results"]
    check("kind=source 只返回原典", bool(r4) and all(x["kind"] == "source" for x in r4),
          len(r4))
    check("原典命中带字符偏移", all(isinstance(x["offset"], int) and x["offset"] > 0 for x in r4),
          r4[0]["offset"] if r4 else "无")

    r5 = json.loads(
        get(FRONT + "/api/search?q=" + urllib.parse.quote("上善若水")
            + "&top_k=8&kind=notes")
    )["results"]
    check("kind=notes 只返回笔记", all(x["kind"] == "notes" for x in r5), len(r5))

    print()
    print("=== D. 原典全文（分块）===")
    small = json.loads(get(FRONT + "/api/books/08/source"))  # 道德经约 7700 字
    check("短书一次取完", small["has_more"] is False and len(small["content"]) == small["total"],
          "道德经 %d 字" % small["total"])
    check("原典含经文原句", "道可道" in small["content"])

    big = json.loads(get(FRONT + "/api/books/14/source"))  # 资治通鉴 321 万字
    check("大书按块返回", big["has_more"] is True, "资治通鉴 %d 字" % big["total"])
    check("块大小受控", len(big["content"]) == big["limit"], big["limit"])
    page2 = json.loads(get(FRONT + "/api/books/14/source?offset=%d" % big["limit"]))
    check("翻页可继续", page2["content"] and page2["content"] != big["content"])

    for book_id, name in (("07", "孙子兵法"), ("13", "史记"), ("15", "贞观政要")):
        body = json.loads(get(FRONT + "/api/books/%s/source" % book_id))
        check("%s 原典可读" % name, len(body["content"]) > 1000, "%d 字" % body["total"])

    # 从检索偏移量跳读：该位置附近应能看到命中语句
    if r4:
        off = max(0, r4[0]["offset"] - 20)
        jump = json.loads(
            get(FRONT + "/api/books/%s/source?offset=%d" % (r4[0]["book_id"], off))
        )
        check("按偏移量跳读原典", "上善若水" in jump["content"],
              "%s @ %d" % (jump["title"], jump["offset"]))

    print()
    print("=== E. 求教与感悟 ===")
    status = json.loads(get(FRONT + "/api/ask/status"))
    check("LLM 状态可查", "enabled" in status, "enabled=%s model=%s" % (status["enabled"], status["model"] or "(无)"))
    check("LLM 状态含候选数", isinstance(status.get("available_models"), int),
          "available_models=%s" % status.get("available_models"))

    req = urllib.request.Request(
        FRONT + "/api/ask",
        data=json.dumps({"question": "工作中遇到小人怎么办？", "top_k": 3}).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    a = json.loads(opener.open(req, timeout=ASK_TIMEOUT).read().decode())
    elapsed = time.time() - started
    check("求教返回回答", bool(a["answer"]), "%d 字" % len(a["answer"]))
    check("求教引用段落", a["retrieved_count"] == 3, a["retrieved_count"])
    # 上游集体故障时必须快速降级，而不是让前端等到超时
    check("求教在时间预算内返回", elapsed < 90, "%.1fs" % elapsed)
    print("        llm_used=%s model=%s" % (a["llm_used"], a["model"] or "(本地检索)"))
    if not a["llm_used"]:
        print("        （上游当前不可用，已按预期降级到本地检索）")

    # 自定义模型通道。这里刻意只走"不会真的连上"的两条路径：
    # smoke 用的是真实 .env，拿真 Key 去探活会花钱，也依赖上游此刻的状态。
    def post(path, payload, timeout=PROBE_TIMEOUT):
        req = urllib.request.Request(
            FRONT + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(opener.open(req, timeout=timeout).read().decode())

    p1 = post("/api/ask/probe", {"base_url": "https://example.com/v1", "api_key": "", "model": ""})
    check("自定义模型：缺 Key 时明确拒绝", p1["ok"] is False and "API Key" in p1["error"],
          p1["error"])

    # 端口 1 上不会有服务，用来验证"连不上"是一次结构化的报告而非 500
    p2 = post("/api/ask/probe", {"base_url": "https://127.0.0.1:1/v1", "api_key": "sk-x", "model": ""})
    check("自定义模型：连不上时返回原因而非报错", p2["ok"] is False and bool(p2["error"]),
          p2["error"][:60])

    # 只填一半时，求教应当照常按默认模型走，而不是带着半截配置去试探
    a2 = post("/api/ask", {"question": "如何面对挫折？", "top_k": 2,
                           "llm": {"base_url": "https://127.0.0.1:1/v1", "api_key": "", "model": ""}},
             timeout=ASK_TIMEOUT)
    check("求教：自定义端点填不全时仍能正常作答", bool(a2["answer"]), "%d 字" % len(a2["answer"]))

    d = json.loads(get(FRONT + "/api/insight/daily"))
    check("今日感悟返回", bool(d["text"]), d["text"][:30])
    d2 = json.loads(get(FRONT + "/api/insight/daily"))
    check("今日感悟同日稳定", d["text"] == d2["text"])

    t = json.loads(get(FRONT + "/api/insight/themes"))
    check("主题数 == 8", len(t["themes"]) == 8, t["themes"])

    print()
    print("=== F. 回响（历史记录）===")
    # 这一段验的是"求教 → 自动落库 → 可查可删"这条链，以及数据库确实是
    # 应用自己建出来的（用户下载后不需要做任何初始化）。
    # 注意：本段只删自己造的那一条，不碰用户已有的历史记录。
    hist = json.loads(get(FRONT + "/api/history/status"))
    check("历史库可用（自动创建，无需初始化）", hist["available"] is True,
          hist.get("error") or hist["db_path"])
    check("保留期半个月", hist["retention_days"] == 15, "%s 天" % hist["retention_days"])
    check("库文件确实落在磁盘上", Path(hist["db_path"]).is_file(), hist["db_path"])
    check("下次自动清理时间可查", bool(hist["next_purge_at"]), hist["next_purge_at"])

    listing = json.loads(get(FRONT + "/api/history?limit=5"))
    check("刚才的求教已自动存入", listing["total"] >= 1, "共 %d 条" % listing["total"])
    check("列表项字段齐备",
          all({"id", "question", "answer", "model", "llm_used", "retrieved_count",
               "created_at", "created_ts"} <= set(x) for x in listing["items"]))
    check("记下的就是刚才问的那个问题",
          any(x["question"] == "工作中遇到小人怎么办？" for x in listing["items"]),
          [x["question"] for x in listing["items"]][:3])
    stamps = [x["created_ts"] for x in listing["items"]]
    check("列表按时间倒序", stamps == sorted(stamps, reverse=True), stamps[:3])

    # 自己造一条再删掉：既验了删除链路，又不会动到用户原有的记录
    probe = post("/api/ask", {"question": "冒烟自检：这条用完就删", "top_k": 1},
                 timeout=ASK_TIMEOUT)
    check("求教回传历史编号", isinstance(probe.get("history_id"), int), probe.get("history_id"))

    def delete(path):
        request = urllib.request.Request(FRONT + path, method="DELETE")
        try:
            with opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, None

    def put(path, payload):
        request = urllib.request.Request(
            FRONT + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with opener.open(request, timeout=20) as response:
            return json.loads(response.read().decode())

    code, body = delete("/api/history/%d" % probe["history_id"])
    check("单条可以删除", code == 200 and body == {"deleted": 1}, body)

    code, _ = delete("/api/history/%d" % probe["history_id"])
    check("重复删除返回 404", code == 404, code)

    after = json.loads(get(FRONT + "/api/history?limit=5"))
    check("删除后总数回退", after["total"] == listing["total"],
          "%d → %d" % (listing["total"], after["total"]))

    # 本次冒烟为了验链路而问的那几句也都自动落了库，一并带走。
    # "不碰用户已有的记录"意味着**自己写的每一条都要收干净**，而不只是那条
    # 显式命名的探针——否则跑几轮之后，用户的「回响」里会堆满冒烟留下的问题。
    for made in (a["history_id"], a2["history_id"]):
        delete("/api/history/%d" % made)
    left_history = json.loads(get(FRONT + "/api/history?limit=5"))
    check("自己造出来的记录已清理干净",
          left_history["total"] == listing["total"] - 2, "%d 条" % left_history["total"])

    # 勾选删除：挑着删，而不是只能一条条点、或者整库清空。这里造的仍然是自己的
    # 记录——同话题连问两次验"整段删"，另造一条验"按 id 删"，验完一并收干净。
    topic = "smoke-bulk-topic"
    made = [post("/api/ask", {"question": "冒烟自检：勾选删除 %d" % i, "top_k": 1,
                              "conversation_id": topic}, timeout=ASK_TIMEOUT)
            for i in (1, 2)]
    check("同话题的两次问答归到一段",
          all(x.get("conversation_id") == topic for x in made),
          [x.get("conversation_id") for x in made])

    gone = post("/api/history/delete", {"ids": [], "topics": [topic]})
    check("勾选删除：勾中整段即删掉段内所有记录", gone["deleted"] == 2, gone)

    # 界面上"全都没勾"和"勾了但已被别处删掉"都会走到这里，两者都不许误伤
    untouched = post("/api/history/delete", {"ids": [], "topics": []})
    check("勾选删除：没勾任何东西时不误删", untouched["deleted"] == 0, untouched)

    spare = post("/api/ask", {"question": "冒烟自检：勾选删单条", "top_k": 1},
                 timeout=ASK_TIMEOUT)
    one = post("/api/history/delete", {"ids": [spare["history_id"]], "topics": []})
    check("勾选删除：只勾单条就只删那条", one["deleted"] == 1, one)
    gone_code, _ = delete("/api/history/%d" % spare["history_id"])
    check("勾选删除后那条确实没了", gone_code == 404, gone_code)

    after_bulk = json.loads(get(FRONT + "/api/history?limit=5"))
    check("勾选删除的自造记录已清理干净",
          after_bulk["total"] == left_history["total"], "%d 条" % after_bulk["total"])

    print()
    print("=== G. 画像 ===")
    # 画像与「回响」是同一个库、同一批素材：从问过的记录里归纳"你是谁"。
    # 这里**不断言"一定归纳出了东西"**——上游此刻好坏不定，而画像本来就该在
    # 归纳不出来时保持原样（那是设计，不是故障）。要验的是：结构齐备、
    # 分类是封闭集合、以及归纳不出来时能说出原因而不是 500。
    prof = json.loads(get(FRONT + "/api/profile"))
    check("画像可读（与历史同一个库）", prof["available"] is True,
          prof.get("error") or "ok")
    check("分类是七个的封闭集合", len(prof["categories"]) == 7, prof["categories"])
    check("分类含性格与规划",
          "性格" in prof["categories"] and "规划" in prof["categories"])
    check("带出形象性别", prof["avatar"] in ("male", "female"), prof["avatar"])
    check("每条特征都带依据与把握",
          all({"id", "category", "content", "evidence", "confidence"} <= set(x)
              for x in prof["traits"]))
    check("特征的分类都在封闭集合里",
          all(x["category"] in prof["categories"] for x in prof["traits"]))
    check("待归纳的条数是整数", isinstance(prof["pending"], int), prof["pending"])

    switched = put("/api/profile/avatar", {"gender": "female"})
    check("形象可以切换", switched["avatar"] == "female", switched["avatar"])
    check("切换后读回来是新值",
          json.loads(get(FRONT + "/api/profile"))["avatar"] == "female")
    check("认不出的性别回落默认",
          put("/api/profile/avatar", {"gender": "别的"})["avatar"] == "male")
    # 还原成用户原来选的那个，别把人家形象改了
    put("/api/profile/avatar", {"gender": prof["avatar"]})

    code, _ = delete("/api/profile/traits/999999")
    check("删不存在的特征返回 404", code == 404, code)

    # 归纳一次，走真实模型。**只删自己造出来的那几条**——与历史那一段同一套
    # 规矩：不碰用户原有的画像。（副作用：后端的"上次归纳时刻"会前移到此刻，
    # 于是下次打开画像页不会自动归纳；手动点「重新归纳」照常可用。）
    before = {x["id"] for x in prof["traits"]}
    extracted = post("/api/profile/extract", {"lang": "zh"}, timeout=ASK_TIMEOUT)
    check("归纳响应字段齐备",
          {"ok", "extracted", "total", "llm_used", "error"} <= set(extracted),
          extracted.get("error") or "ok")
    check("没走模型时说得出原因",
          extracted["llm_used"] or bool(extracted["error"]),
          extracted["error"] or "llm_used=%s" % extracted["llm_used"])
    check("新增条数与响应一致",
          extracted["extracted"] >= 0 and extracted["total"] >= 0,
          "新增 %d 条，现有 %d 条" % (extracted["extracted"], extracted["total"]))

    added = [x for x in json.loads(get(FRONT + "/api/profile"))["traits"]
             if x["id"] not in before]
    for trait in added:
        delete("/api/profile/traits/%d" % trait["id"])
    left = json.loads(get(FRONT + "/api/profile"))["traits"]
    check("自己造出来的特征已清理干净",
          {x["id"] for x in left} == before,
          "清掉 %d 条，剩 %d 条" % (len(added), len(left)))

    print()
    print("=== G2. 最像你的一位历史人物 ===")
    # 与画像同一段：**不断言"一定评出了谁"**（上游好坏不定，评不出来时保持原样
    # 是设计）。要验的是：名录读得出来、画像文件真的取得到、穿越读不到。

    def get_raw(path):
        """取原始字节：画像不是 JSON，解不了码也不需要解。"""
        try:
            with opener.open(FRONT + path, timeout=20) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, b""

    prof = json.loads(get(FRONT + "/api/profile"))
    figure = prof["figure"]
    check("画像里带着历史人物这一块",
          {"id", "name", "era", "blurb", "reason", "credit", "portrait",
           "week", "chosen_at", "pool_size", "needs_refresh"} <= set(figure))
    check("名录读得出来（该性别下不止一两个人）",
          figure["pool_size"] > 1, "%d 位候选" % figure["pool_size"])
    check("要不要重评是个布尔值", isinstance(figure["needs_refresh"], bool))
    check("选中的人物与画像地址同时有或同时无",
          bool(figure["id"]) == bool(figure["portrait"]),
          figure["id"] or "还没评出人来")
    if figure["id"]:
        check("选中的人带得出时代与署名",
              bool(figure["era"]) and bool(figure["credit"]), figure["era"])
        check("记着是哪个周评出的", len(figure["week"]) == 8, figure["week"])

    # 画像走真实的 webp 响应；404 与穿越一并验掉
    portrait_id = urllib.parse.quote(figure["id"] or "taoyuanming")
    code, body = get_raw("/api/profile/figure/portrait/" + portrait_id)
    check("画像文件取得到", code == 200 and len(body) > 1024,
          "HTTP %d，%d 字节" % (code, len(body)))
    code, _ = get_raw("/api/profile/figure/portrait/" + urllib.parse.quote("查无此人"))
    check("不在名录里的 id 返回 404", code == 404, code)
    code, _ = get_raw("/api/profile/figure/portrait/..%2F..%2F.env")
    check("穿越的 id 也返回 404", code == 404, code)

    print()
    print("=== H. 阅读页章节链路 ===")
    # 阅读页是三段式：书目详情 → 左栏目录 → 右侧正文。前两段原先没有覆盖。
    detail = json.loads(get(FRONT + "/api/books/01"))
    check("书目详情含章节数与原典标记",
          detail["chapter_count"] > 0 and detail["has_source"] is True,
          "%s｜%s｜%d 章" % (detail["title"], detail["category"], detail["chapter_count"]))

    chapters = json.loads(get(FRONT + "/api/books/01/chapters"))
    check("章节列表非空", len(chapters) > 0, len(chapters))
    check("章节项字段齐备",
          all({"chapter_id", "title", "book_id"} <= set(c) for c in chapters))

    # 「导言」章的正文是全书序言，自带 H1 标题，与目录标签名并不相同
    # （目录叫"导言"，正文标题是"《易经》上篇理解笔记"），所以分两条断言：
    # 序言章验"取得到且非空"，另取一实质章验"成篇且标题对得上"。
    head = chapters[0]
    chapter = json.loads(
        get(FRONT + "/api/books/01/chapters/%s" % head["chapter_id"])
    )
    check("序言章正文非空", bool(chapter["content"].strip()),
          "%s｜%d 字" % (chapter["title"], len(chapter["content"])))

    body = json.loads(
        get(FRONT + "/api/books/01/chapters/%s" % chapters[1]["chapter_id"])
    )
    check("实质章成篇且正文标题对得上",
          len(body["content"]) > 1000 and body["title"] in body["content"],
          "%s｜%d 字" % (body["title"], len(body["content"])))

    print()
    print("=== I. 感悟页筛选 ===")
    theme = t["themes"][0]
    by_theme = json.loads(
        get(FRONT + "/api/insight/by-theme/" + urllib.parse.quote(theme))
    )
    check("按主题筛选有结果", by_theme["total"] > 0, "%s｜%d 条" % (theme, by_theme["total"]))
    check("筛选结果的主题确实包含该主题",
          all(theme in item["themes"] for item in by_theme["items"]))

    by_book = json.loads(get(FRONT + "/api/insight/by-book/01"))
    check("按书目筛选有结果", by_book["total"] > 0, "%d 条" % by_book["total"])
    check("按书目筛选的结果都属于该书",
          all(item["book_id"] == "01" for item in by_book["items"]))

    one = json.loads(get(FRONT + "/api/insight/%d" % by_book["items"][0]["id"]))
    check("单条感悟可查", bool(one["text"]), one["text"][:20])

    rand = json.loads(get(FRONT + "/api/insight/random"))
    check("随机感悟返回", bool(rand["text"]), rand["text"][:20])

    print()
    print("=== J. 知识库（双链与关系图谱）===")
    # 这一段验的是"笔记里写下的关系真的被读成了图"：15 部书 + 8 个主题是节点，
    # 笔记里的主题表与交叉点段是边。孤岛与认不出的引用都算故障——前者说明语料
    # 断了链，后者说明笔记里写错了书名（比如写了《通鉴》却没登记别名）。
    kb = json.loads(get(FRONT + "/api/kb/graph"))
    node_ids = {n["id"] for n in kb["nodes"]}
    check("节点数 == 15 部书 + 8 个主题", len(node_ids) == 23, len(kb["nodes"]))
    check("书节点齐备", all("book:%02d" % i in node_ids for i in range(1, 16)))
    check("主题节点齐备", all("theme:%s" % th in node_ids for th in t["themes"]))
    check("每条边的两端都在节点表里",
          all(e["source"] in node_ids and e["target"] in node_ids for e in kb["edges"]))
    check("图上没有自环", all(e["source"] != e["target"] for e in kb["edges"]))
    check("互参边都带着原文",
          all(e["label"] for e in kb["edges"] if e["kind"] == "cross"))
    check("认不出的引用为空",
          kb["stats"]["unresolved_refs"] == [], kb["stats"]["unresolved_refs"])
    check("主题都在封闭集合内",
          kb["stats"]["unknown_themes"] == [], kb["stats"]["unknown_themes"])

    connected = {e["source"] for e in kb["edges"]} | {e["target"] for e in kb["edges"]}
    isolated = [n["label"] for n in kb["nodes"]
                if n["kind"] == "book" and n["id"] not in connected]
    check("没有孤立的书", not isolated, isolated or "无")
    print("        节点 %d｜边 %d（主题归属 %d / 经典互参 %d）" % (
        len(kb["nodes"]), kb["stats"]["edges"],
        kb["stats"]["theme_edges"], kb["stats"]["cross_edges"]))

    expanded = json.loads(get(FRONT + "/api/kb/graph?chapters=true"))
    chapter_nodes = [n for n in expanded["nodes"] if n["kind"] == "chapter"]
    check("展开后含全部章节", len(chapter_nodes) == h["total_chapters"], len(chapter_nodes))
    check("每章都有一条构成边",
          sum(1 for e in expanded["edges"] if e["kind"] == "part") == len(chapter_nodes))

    node = json.loads(get(FRONT + "/api/kb/nodes/book:08"))
    check("书节点带元信息", node["node"]["meta"]["author"] == "老子",
          node["node"]["meta"]["author"])
    check("出链与反链是两个方向",
          {l["direction"] for l in node["outgoing"]} == {"out"}
          and {l["direction"] for l in node["backlinks"]} == {"in"})
    check("《道德经》被多本书参照", len(node["backlinks"]) >= 3,
          [l["label"] for l in node["backlinks"]])
    check("八个主题明细齐备", len(node["theme_rows"]) == 8, len(node["theme_rows"]))
    check("每条主题明细都带着判断与章句",
          all(r["judgment"] and r["quote"] for r in node["theme_rows"]))

    # 双链的要点：A 写了它参照 B，那么站在 B 这边必须看得见 A。
    # 取语料里确定存在的一对（贞观政要·与项目内其他经典的交叉点 → 道德经）。
    other = json.loads(get(FRONT + "/api/kb/nodes/book:15"))
    out_labels = {l["label"] for l in other["outgoing"]}
    check("《贞观政要》写出了它参照的经典", "道德经" in out_labels, sorted(out_labels))
    check("被参照的那本能看到这条反向链接",
          any(l["label"] == "贞观政要" for l in node["backlinks"]),
          [l["label"] for l in node["backlinks"]])

    local = json.loads(get(FRONT + "/api/kb/nodes/book:08/local"))
    focus = local["stats"]["focus"]
    check("局部图只留与焦点相连的边",
          all(e["source"] == focus or e["target"] == focus for e in local["edges"]),
          "%d 条边" % len(local["edges"]))
    check("局部图带上这本书自己的章节",
          any(n["kind"] == "chapter" for n in local["nodes"]),
          sum(1 for n in local["nodes"] if n["kind"] == "chapter"))
    check("局部图是全图的子集",
          {(e["source"], e["target"], e["kind"]) for e in local["edges"]}
          <= {(e["source"], e["target"], e["kind"]) for e in expanded["edges"]})

    hits = json.loads(get(FRONT + "/api/kb/search?q=" + urllib.parse.quote("道德")))
    check("按名字找得到节点", any(n["id"] == "book:08" for n in hits),
          [n["label"] for n in hits])
    check("空查询返回关联最多的节点",
          json.loads(get(FRONT + "/api/kb/search"))[0]["degree"] > 0)

    print()
    print("=== L. 账号 / 我的书架 / 后台管理 ===")
    # 这一段走的是完整的一条业务链：
    #   注册 → 加书到自己的书架 → 申请公开 → 管理员批准 → 进公共书架 → 检索得到
    # 全部用**手造的候选**（source_key 为空），所以不依赖 OpenLibrary 此刻是否可达：
    # 加书只在 source_key 非空时才去补详情。
    stamp = str(int(time.time()))
    alice = Session()
    bob = Session()

    email = "smoke+%s@example.com" % stamp
    code, created = alice.call(
        "/api/auth/register", "POST",
        {"email": email, "password": "smokepass123", "display_name": "冒烟"},
    )
    check("注册返回 201", code == 201, code)
    check("注册即登录（cookie 已种下）",
          alice.call("/api/auth/me")[1]["user"] is not None)
    check("响应里没有密码字段",
          not ({"password", "password_hash", "salt"} & set(created or {})),
          sorted(created or {}))

    code, dup = alice.call(
        "/api/auth/register", "POST",
        {"email": email, "password": "smokepass123"},
    )
    check("重复邮箱被拒（400）", code == 400, code)

    code, _ = alice.call(
        "/api/auth/register", "POST",
        {"email": "smoke+short@example.com", "password": "123"},
    )
    check("密码太短被拒（400）", code == 400, code)

    anon = Session()
    check("匿名访问 /api/auth/me 得到 null 而非 401",
          anon.call("/api/auth/me")[1]["user"] is None)

    code, _ = anon.call("/api/shelf")
    check("匿名读我的书架返回 401", code == 401, code)
    code, _ = anon.call("/api/admin/overview")
    check("匿名访问后台返回 401", code == 401, code)

    # 加一本不存在于公共语料里的书，方便后面验证"检索能命中自己的书架"
    CANDIDATE = {
        "title": "冒烟测试之书",
        "author": "冒烟作者",
        "year": "2026",
        "cover_url": "",
        "source_key": "",
        "source": "openlibrary",
        "summary": "这本书只为验证链路而存在。",
        "subjects": ["测试"],
    }
    code, book = alice.call("/api/shelf/books", "POST", {**CANDIDATE, "with_guide": False})
    check("加书返回 201", code == 201, code)
    check("加书立刻返回（导读不挡路）", isinstance(book, dict) and book.get("id"), book)
    book_id = (book or {}).get("id")

    shelf = alice.call("/api/shelf")[1]
    check("我的书架里有这本书",
          any(b["id"] == book_id for b in shelf["books"]), shelf["total"])
    check("初始可见性是 private", book.get("visibility") == "private", book.get("visibility"))

    hits = alice.call(
        "/api/search?q=" + urllib.parse.quote("冒烟测试之书") + "&kind=shelf"
    )[1]["results"]
    check("检索能命中自己的书架（kind=shelf）",
          any(x["kind"] == "shelf" for x in hits), [x["source"] for x in hits])

    mixed = alice.call(
        "/api/search?q=" + urllib.parse.quote("冒烟测试之书") + "&top_k=10"
    )[1]["results"]
    check("不带 kind 时私人书架也在检索范围内",
          any(x["kind"] == "shelf" for x in mixed), len(mixed))

    other = bob.call(
        "/api/auth/register", "POST",
        {"email": "smoke+other+%s@example.com" % stamp, "password": "smokepass123"},
    )
    check("第二个账号注册成功", other[0] == 201, other[0])
    other_shelf = bob.call("/api/shelf")[1]
    check("别人的书架里看不到我的书", other_shelf["total"] == 0, other_shelf["total"])
    code, _ = bob.call("/api/shelf/books/%s" % book_id)
    check("越权读别人的书返回 404（而不是 403，免得泄露存在性）", code == 404, code)
    code, _ = bob.call("/api/admin/overview")
    check("普通用户访问后台返回 403", code == 403, code)

    # 历史记录的归属：用 /api/ask/save 直接记账，不必真的调一次模型
    alice.call("/api/ask/save", "POST", {
        "question": "冒烟问题：这本书讲了什么？",
        "answer": "冒烟回答。",
        "model": "smoke",
        "retrieved_count": 1,
    })
    mine = alice.call("/api/history")[1]
    check("登录用户的回响里有自己的记录",
          any("冒烟问题" in i["question"] for i in mine["items"]), mine["total"])
    # 匿名桶**不是空的**：登录功能上线前留下的问答、以及本次冒烟前面几段匿名求教的
    # 记录，user_id 都是 NULL，本来就归在匿名那一份里。所以这里不能断言"为空"——
    # 那是在断言"历史被清空了"，而不是在断言"隔离生效了"。要看的是 alice 那条有没有漏过来。
    anon_items = anon.call("/api/history")[1]["items"]
    check("匿名看不到登录用户的记录",
          not any("冒烟问题" in i["question"] for i in anon_items),
          "匿名桶 %d 条，均非 alice 的记录" % len(anon_items))
    # bob 是本次新注册的账号，名下一条记录都没有，这里可以直接断言为空。
    check("别的用户看不到我的记录",
          bob.call("/api/history")[1]["items"] == [])

    alice.call("/api/shelf/books/%s/submit" % book_id, "POST")
    pending = alice.call("/api/shelf/books/%s" % book_id)[1]
    check("申请公开后可见性为 pending", pending["visibility"] == "pending",
          pending["visibility"])

    env = read_env_file()
    admin_email = os.environ.get("RSDS_ADMIN_EMAIL") or env.get(
        "RSDS_ADMIN_EMAIL", "admin@renshengdaoshi.local")
    admin_password = os.environ.get("RSDS_ADMIN_PASSWORD") or env.get(
        "RSDS_ADMIN_PASSWORD", "admin123456")
    admin = Session()
    code, _ = admin.call("/api/auth/login", "POST",
                         {"email": admin_email, "password": admin_password})
    check("内置管理员能登录", code == 200, "%s / %s" % (code, admin_email))

    if code == 200:
        overview = admin.call("/api/admin/overview")[1]
        check("总览含今日计数", isinstance(overview.get("history_today"), int), overview)
        check("总览含语料规模", overview.get("corpus_books") == 15, overview.get("corpus_books"))
        check("总览含待审数", isinstance(overview.get("pending_review"), int),
              overview.get("pending_review"))

        queue = admin.call("/api/admin/review")[1]
        check("待审队列里有刚提交的那本书",
              any(r["id"] == book_id for r in queue), len(queue))
        check("待审项带提交人邮箱",
              any(r["user_email"] == email for r in queue),
              [r["user_email"] for r in queue])

        code, reviewed = admin.call(
            "/api/admin/review/%s" % book_id, "POST",
            {"approve": True, "note": "", "category": "测试"},
        )
        check("批准返回 200", code == 200, code)
        check("批准后可见性为 public", reviewed.get("visibility") == "public",
              reviewed.get("visibility"))

        public = admin.call("/api/admin/public")[1]
        check("公共书架里有这条贡献",
              any(b["title"] == "冒烟测试之书" for b in public),
              [b["book_id"] for b in public])
        check("贡献书号带 u 前缀（不与内置书号撞车）",
              all(b["book_id"].startswith("u") for b in public if b["title"] == "冒烟测试之书"))

        # 批准之后，**匿名**也应该检索得到——它已经进了公共书架
        public_hit = anon.call(
            "/api/search?q=" + urllib.parse.quote("冒烟测试之书") + "&top_k=10"
        )[1]["results"]
        check("批准后匿名也能检索到这本书", bool(public_hit), len(public_hit))

        users = admin.call("/api/admin/users")[1]
        check("用户列表含刚注册的账号",
              any(u["email"] == email for u in users), len(users))
        check("用户列表标出管理员",
              any(u["is_admin"] for u in users), [u["email"] for u in users])

        tables = admin.call("/api/admin/db/tables")[1]
        names = {t["name"] for t in tables}
        check("数据库表列表含 users / user_books / public_books",
              {"users", "user_books", "public_books"} <= names, sorted(names))
        check("表列表不暴露 sqlite 内部表",
              not any(n.startswith("sqlite_") for n in names), sorted(names))

        code, users_table = admin.call("/api/admin/db/tables/users?limit=5")
        check("能读 users 表结构", code == 200 and bool(users_table["columns"]), code)
        protected = {c["name"] for c in users_table["columns"] if c["protected"]}
        check("密码哈希与 salt 标为受保护",
              {"password_hash", "salt"} <= protected, sorted(protected))
        check("读表不会把密码哈希藏起来（管理员看得到，但不能改）",
              "password_hash" in {c["name"] for c in users_table["columns"]})

        code, err = admin.call(
            "/api/admin/db/tables/users/rows", "POST",
            {"email": "x@example.com", "password_hash": "x", "salt": "y"},
        )
        check("不允许从数据库界面直接插入用户", code == 400, code)
        code, err = admin.call("/api/admin/db/tables/nope", "GET")
        check("未知表返回 400 而非 500", code == 400, code)

        audit = admin.call("/api/admin/audit")[1]
        actions = {a["action"] for a in audit}
        check("审计里有刚才那次批准", "approve_book" in actions, sorted(actions))
        check("审计记下了操作人", all(a["user_id"] for a in audit), audit[:2])

    code, _ = alice.call("/api/auth/logout", "POST")
    check("登出返回 200", code == 200, code)
    check("登出后 /api/auth/me 为 null",
          alice.call("/api/auth/me")[1]["user"] is None)
    code, _ = alice.call("/api/shelf")
    check("登出后读我的书架回到 401", code == 401, code)

    print()
    print("=== K. 错误路径 ===")
    # 未知 id 必须是干净 404；返回 500 或（更糟）回退成前端 HTML 都算故障：
    # 前端 fetch 会拿到一段 HTML 再报 JSON 解析错误，排查起来非常痛苦。
    for path in ("/api/books/nope", "/api/books/01/chapters/nope",
                 "/api/insight/999999", "/api/kb/nodes/book:99",
                 "/api/kb/nodes/nonsense/local"):
        try:
            get(FRONT + path)
            code = 200
        except urllib.error.HTTPError as exc:
            code = exc.code
        check("%s 返回 404" % path, code == 404, code)

    try:
        get(FRONT + "/api/nope")
        code = 200
    except urllib.error.HTTPError as exc:
        code = exc.code
    check("未知接口返回 404 而非前端页面", code == 404, code)

    print()
    # 把项数打出来：README 里写着"API 层 N 项"，那个数字靠人肉维护迟早会飘，
    # 让它自己报数，对不上了一眼就能看出来。
    print("=== 结论 ===", "全部通过" if ok else "存在失败项",
          "（共 %d 项，失败 %d 项）" % (total, failed))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
