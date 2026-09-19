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

from .paths import resolve_web_dist, should_serve_frontend
from .routers.ask import router as ask_router
from .routers.books import router as books_router
from .routers.history import router as history_router
from .routers.insight import router as insight_router
from .routers.kb import router as kb_router
from .routers.profile import router as profile_router
from .routers.search import router as search_router
from .services.content_loader import get_loader
from .services.history import get_history_store
from .services.kb import get_kb
from .services.retriever import ensure_retriever, get_retriever, index_progress
from .web_ui import mount_frontend

#: 应用版本。发版时改这一处即可——FastAPI 的 OpenAPI 与根路径索引都读它。
APP_VERSION = "1.3.1"


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
    store = get_history_store()
    print("[人生导师] 历史记录库：%s（可用：%s）" % (store.db_path, store.available))
    if not store.available:
        print("[人生导师] 历史记录暂不可用：%s" % store.error)
    yield


app = FastAPI(
    title="人生导师 API",
    description="中国传统经典智慧知识库与智能问答服务",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS 配置：允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(insight_router)
app.include_router(history_router)
app.include_router(profile_router)
app.include_router(kb_router)


@app.get("/api/health")
async def health():
    """健康检查：反映已加载的书目规模与索引规模。

    还会带上建索引的进度（``indexing``）。启动画面靠它把「正在编索引」这句
    换成一条真在走的进度条——索引没建好之前，本接口在 lifespan 里就还没开始
    应答，所以这里的 ``ready`` 只在服务已经可用时才会是 True，而 ``indexing``
    描述的是"此刻进行到哪了"，供惰性构建（首个请求触发）时仍能显示。
    """
    loader = get_loader()
    retriever = get_retriever()
    books = loader.get_books()
    coverage = retriever.source_coverage
    progress = index_progress()
    return {
        "status": "ok",
        "ready": bool(retriever.documents),
        "indexing": progress,
        "books_loaded": len(books),
        "books_with_source": sum(1 for b in books if b.source_file),
        "total_chapters": sum(len(b.chapters) for b in books),
        "total_passages": len(retriever.documents),
        "source_indexed": len(coverage.get("indexed", [])),
        "source_skipped": coverage.get("skipped", []),
        "categories": loader.categories(),
    }


#: 前端构建产物。分发态随包分发；开发态通常不存在（页面走 Vite 的 :5173）。
#: 设 RSDS_SERVE_FRONTEND=0 可强制关闭托管（纯 API 调试）。
FRONTEND_DIST = resolve_web_dist() if should_serve_frontend() else None

if FRONTEND_DIST is not None:
    # 注意：这一步必须在上面所有路由注册完之后。SPA 回退会吞掉一切未匹配的
    # GET，提前挂上会把 /api/* 与 /docs 一并截胡（详见 web_ui.mount_frontend）。
    mount_frontend(app, FRONTEND_DIST)
else:

    @app.get("/")
    async def root():
        """根路径：无前端产物时退化为 API 索引（开发态请走 Vite 的 :5173）。"""
        return {
            "name": "人生导师 API",
            "version": APP_VERSION,
            "endpoints": {
                "books": "/api/books",
                "search": "/api/search?q=关键词",
                "ask": "POST /api/ask",
                "insight": "/api/insight/daily",
                "history": "/api/history",
                "profile": "/api/profile",
                "kb": "/api/kb/graph",
                "docs": "/docs",
            },
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
