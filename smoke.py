# -*- coding: utf-8 -*-
"""冒烟验证：run.py 默认端口(后端 8000 / 前端 5173) 的前后端联调链路。

覆盖：健康检查与语料规模 → 前端页面可编译 → vite 代理转发 →
寻章检索命中古籍 → 原典分块读取 → 求教（含 LLM 状态）→ 回响（历史记录）→
感悟稳定性 → 阅读页章节链路与感悟页筛选 → 错误路径。

所有请求都走 vite 代理（``localhost:5173``），即浏览器实际使用的那条链路；
后端 API 直连只用于 A 段，以便区分"后端故障"与"代理故障"。

注意：本机 Vite 绑定 IPv6，且环境 http_proxy 会拦截 127.0.0.1，
因此浏览器侧一律用 localhost；后端 API 直连用 127.0.0.1。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FRONT = "http://localhost:5173"
BACK = "http://127.0.0.1:8000"

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


def main():
    ok = True

    def check(label, cond, extra=""):
        nonlocal ok
        if not cond:
            ok = False
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
    a = json.loads(opener.open(req, timeout=150).read().decode())
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
    def post(path, payload, timeout=40):
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
                           "llm": {"base_url": "https://127.0.0.1:1/v1", "api_key": "", "model": ""}})
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
    probe = post("/api/ask", {"question": "冒烟自检：这条用完就删", "top_k": 1})
    check("求教回传历史编号", isinstance(probe.get("history_id"), int), probe.get("history_id"))

    def delete(path):
        request = urllib.request.Request(FRONT + path, method="DELETE")
        try:
            with opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, None

    code, body = delete("/api/history/%d" % probe["history_id"])
    check("单条可以删除", code == 200 and body == {"deleted": 1}, body)

    code, _ = delete("/api/history/%d" % probe["history_id"])
    check("重复删除返回 404", code == 404, code)

    after = json.loads(get(FRONT + "/api/history?limit=5"))
    check("删除后总数回退", after["total"] == listing["total"],
          "%d → %d" % (listing["total"], after["total"]))

    print()
    print("=== G. 阅读页章节链路 ===")
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
    print("=== H. 感悟页筛选 ===")
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
    print("=== I. 错误路径 ===")
    # 未知 id 必须是干净 404；返回 500 或（更糟）回退成前端 HTML 都算故障：
    # 前端 fetch 会拿到一段 HTML 再报 JSON 解析错误，排查起来非常痛苦。
    for path in ("/api/books/nope", "/api/books/01/chapters/nope", "/api/insight/999999"):
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
    print("=== 结论 ===", "全部通过" if ok else "存在失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
