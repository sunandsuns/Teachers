"""人生导师 FastAPI 后端入口。

同一份应用支撑两种运行方式：

- **开发态**：只提供 ``/api``，页面由 Vite 开发服务器（:5173）现编并代理过来；
- **分发态**：``web/dist`` 存在时由本进程一并托管，页面与接口同源同端口，
  于是整件事可以装进一个原生窗口（见 ``desktop.py``）。

本文件只做**装配**：建应用、挂中间件、注册路由、决定要不要托管前端。
具体逻辑都在 ``services/``（业务）与 ``routers/``（HTTP 边界）里，
前端托管的细节在 ``web_ui.py``。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .errors import install_error_handlers
from .paths import resolve_web_dist, should_serve_frontend
from .routers.admin import router as admin_router
from .routers.ask import router as ask_router
from .routers.auth import router as auth_router
from .routers.books import router as books_router
from .routers.history import router as history_router
from .routers.insight import router as insight_router
from .routers.kb import router as kb_router
from .routers.profile import router as profile_router
from .routers.search import router as search_router
from .routers.shelf import router as shelf_router
from .schemas.system import HealthResponse, IndexProgress, RootResponse
from .services.auth import admin_credentials, get_auth_store
from .services.content_loader import get_loader
from .services.history import get_history_store
from .services.kb import get_kb
from .services.retriever import ensure_retriever, get_retriever, index_progress
from .web_ui import mount_frontend

#: 应用版本。发版时改这一处即可——FastAPI 的 OpenAPI 与根路径索引都读它。
APP_VERSION = "1.5.0"

#: ``/docs`` 上的分组说明与顺序。
#: 不写这一段的话，Swagger 会按 tag 名的字母序把接口堆成一长条，而且只有
#: "admin"、"ask" 这种光秃秃的词，看不出哪一组是干什么的、从哪读起。
OPENAPI_TAGS = [
    {"name": "system", "description": "探活与索引规模。这两个接口**不需要登录**。"},
    {"name": "auth", "description": "注册、登录、登出、改密码。登录注册本身也不需要登录，否则没人进得来。"},
    {"name": "books", "description": "书目、章节、原典正文（分块）。"},
    {"name": "search", "description": "「寻章」：跨笔记与原典的词面检索。"},
    {"name": "ask", "description": "「求教」：检索 + 模型作答。含交给浏览器调云模型的那条 plan/save 通路。"},
    {"name": "history", "description": "「回响」：问答记录与话题聚合。库不可用时降级成 `available: false` 而不是报错。"},
    {"name": "profile", "description": "「画像」：从提问里归纳出的性格特征与历史人物比对。"},
    {"name": "knowledge base", "description": "「知识库」：原典、主题、洞察之间的引用图谱。"},
    {"name": "insight", "description": "「感悟」：按日/按书/按主题取一条洞察。"},
    {"name": "shelf", "description": "个人书架：联网检索书籍、加书、改阅读状态、申请公开。"},
    {"name": "admin", "description": "后台管理。**每个接口都需要管理员身份**；其中数据库那一组是运维口子。"},
]

#: 错误长什么样，写在文档首页——省得每个调用方自己去猜。
API_DESCRIPTION = """中国传统经典智慧知识库与智能问答服务。

**所有接口都要登录**，只有 ``/api/auth/*`` 与 ``/api/health`` 留开：这套产品的入口就是登录页，登录之前一个页面也看不了。

出错时响应体只有一种形状：

```json
{"detail": {"code": "bad_credentials", "message": "邮箱或密码不正确"}}
```

``code`` 给机器读（按它分支），``message`` 给人读（可直接展示）。唯一的例外是 422——
参数没过校验时 ``code`` 固定为 ``validation``，``message`` 里带着字段路径。

数据库不可用时，**裸列表类的接口**返回 503 而不是空列表：空的用户列表和"读不到"
分不清。只有响应里带 ``available`` 字段的那两个（回响、画像）会降级成 200 加
``available: false``。
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预加载内容并构建检索索引。

    幂等：索引已存在（例如测试会话中已预建）则不重复构建。
    这里预建只是把冷启动的一次性开销提前，即便跳过了，首个请求也会惰性补上
    （见 ``retriever.ensure_retriever``）。

    顺带碰一下历史记录存储：**把建库动作提到启动时**。它本来是惰性的，但那样
    用户问第一句话时会多等一次建表；更重要的是，万一程序目录不可写而落到了
    用户目录兜底，启动日志里就会写清楚库最终落在哪，排查时不用猜。
    画像与历史同一个库文件，所以这一次就把两张表都建好了。

    知识库图谱（``get_kb``）也一并预热：它同样是惰性的，而建图只要十几毫秒。
    既然已经在为索引等七秒，顺手做掉，用户点进「知识库」就是现成的一张图。
    """
    loader = get_loader()
    ensure_retriever(loader)
    get_kb().warm_up()
    # 这一下也必须兜住：历史记录是附加项，它要是能在启动时把整个应用拖死，
    # 就等于让一个记账功能决定了书架、寻章、求教能不能用。真实踩过——
    # 容器里没有家目录，取数据目录的那一步就抛了异常。
    try:
        store = get_history_store()
        print("[人生导师] 历史记录库：%s（可用：%s）" % (store.db_path, store.available))
        if not store.available:
            print("[人生导师] 历史记录暂不可用：%s" % store.error)
    except Exception as exc:  # noqa: BLE001 — 启动期的附加项，失败只记录
        print("[人生导师] 历史记录暂不可用：%s" % exc)

    # 内置管理员：首次启动写进库。之后每次启动只做一次存在性检查——
    # 已存在就什么都不做，**绝不重置密码**（否则管理员自己改过的密码
    # 会被每次重启悄悄改回默认值）。
    try:
        created = get_auth_store().ensure_admin()
        email, _ = admin_credentials()
        if created is not None:
            print("[人生导师] 已创建内置管理员：%s" % email)
            print("[人生导师] 初始密码取 RSDS_ADMIN_PASSWORD，默认值仅供本机使用；"
                  "上线前请务必用环境变量覆盖。")
        else:
            print("[人生导师] 管理员账号：%s" % email)
    except Exception as exc:  # noqa: BLE001 — 同上，启动期的附加项
        print("[人生导师] 管理员初始化失败：%s" % exc)
    yield


app = FastAPI(
    title="人生导师 API",
    description=API_DESCRIPTION,
    version=APP_VERSION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

# 全局错误出口：统一的 {code, message} 形状、业务异常、库故障（见 errors.py）。
install_error_handlers(app)

# CORS 配置：允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)
app.include_router(auth_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(insight_router)
app.include_router(history_router)
app.include_router(profile_router)
app.include_router(kb_router)
app.include_router(shelf_router)
app.include_router(admin_router)


@app.get("/api/health", tags=["system"], response_model=HealthResponse)
async def health():
    """健康检查：反映已加载的书目规模与索引规模。

    还会带上建索引的进度（``indexing``）。启动画面靠它把「正在编索引」这句
    换成一条真在走的进度条——索引没建好之前，本接口在 lifespan 里就还没开始
    应答，所以这里的 ``ready`` 只在服务已经可用时才会是 True，而 ``indexing``
    描述的是"此刻进行到哪了"，供惰性构建（首个请求触发）时仍能显示。

    **本接口不需要登录**——部署平台拿它判断服务起没起来。
    """
    loader = get_loader()
    retriever = get_retriever()
    books = loader.get_books()
    coverage = retriever.source_coverage
    return HealthResponse(
        status="ok",
        ready=bool(retriever.documents),
        indexing=IndexProgress(**index_progress()),
        books_loaded=len(books),
        books_with_source=sum(1 for b in books if b.source_file),
        total_chapters=sum(len(b.chapters) for b in books),
        total_passages=len(retriever.documents),
        source_indexed=len(coverage.get("indexed", [])),
        source_skipped=coverage.get("skipped", []),
        categories=loader.categories(),
    )


#: 前端构建产物。分发态随包分发；开发态通常不存在（页面走 Vite 的 :5173）。
#: 设 RSDS_SERVE_FRONTEND=0 可强制关闭托管（纯 API 调试）。
FRONTEND_DIST = resolve_web_dist() if should_serve_frontend() else None

if FRONTEND_DIST is not None:
    # 注意：这一步必须在上面所有路由注册完之后。SPA 回退会吞掉一切未匹配的
    # GET，提前挂上会把 /api/* 与 /docs 一并截胡（详见 web_ui.mount_frontend）。
    mount_frontend(app, FRONTEND_DIST)
else:

    @app.get("/", tags=["system"], response_model=RootResponse)
    async def root():
        """根路径：无前端产物时退化为 API 索引（开发态请走 Vite 的 :5173）。"""
        return RootResponse(
            name="人生导师 API",
            version=APP_VERSION,
            endpoints={
                "books": "/api/books",
                "search": "/api/search?q=关键词",
                "ask": "POST /api/ask",
                "insight": "/api/insight/daily",
                "history": "/api/history",
                "profile": "/api/profile",
                "kb": "/api/kb/graph",
                "docs": "/docs",
            },
        )


if __name__ == "__main__":
    import os

    import uvicorn

    # 端口从环境变量取：线上部署只暴露一个由平台注入的端口（``PORT``），
    # 写死 8000 就起不来。本地不带这个变量时仍是 8000，开发习惯不变。
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000) or 8000))
