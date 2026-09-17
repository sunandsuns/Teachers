"""人生导师 FastAPI 后端入口。

同一份应用支撑两种运行方式：

- **开发态**：只提供 ``/api``，页面由 Vite 开发服务器（:5173）现编并代理过来；
- **分发态**：``web/dist`` 存在时由本进程一并托管，页面与接口同源同端口，
  于是整件事可以装进一个原生窗口（见 ``desktop.py``）。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .paths import resolve_web_dist, should_serve_frontend
from .routers.ask import router as ask_router
from .routers.books import router as books_router
from .routers.insight import router as insight_router
from .routers.search import router as search_router
from .services.content_loader import get_loader
from .services.retriever import build_retriever_from_loader, get_retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预加载内容并构建检索索引。

    幂等：若索引已存在（例如测试会话中已预建），则不重复构建。
    """
    loader = get_loader()
    if not get_retriever().documents:
        build_retriever_from_loader(loader)
    yield


app = FastAPI(
    title="人生导师 API",
    description="中国传统经典智慧知识库与智能问答服务",
    version="1.0.0",
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


@app.get("/api/health")
async def health():
    """健康检查：反映已加载的书目规模与索引规模。"""
    loader = get_loader()
    retriever = get_retriever()
    books = loader.get_books()
    coverage = retriever.source_coverage
    return {
        "status": "ok",
        "books_loaded": len(books),
        "books_with_source": sum(1 for b in books if b.source_file),
        "total_chapters": sum(len(b.chapters) for b in books),
        "total_passages": len(retriever.documents),
        "source_indexed": len(coverage.get("indexed", [])),
        "source_skipped": coverage.get("skipped", []),
        "categories": loader.categories(),
    }


def _mount_frontend(application: FastAPI, dist: Path) -> None:
    """把前端构建产物挂到同一端口，实现单进程同源部署。

    必须在**所有 API 路由注册完毕之后**调用：SPA 回退会吞掉一切未匹配的 GET，
    排在前面会把 ``/api/*`` 与 FastAPI 自带的 ``/docs`` 一并截胡。
    注意本函数要放在 ``/api/health`` 之后——Starlette 按注册顺序匹配，
    先注册的回退路由会盖住后注册的接口。
    """
    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # 未命中的 /api/* 说明是拼错的接口，应当照常 404。
        # 若回退成 index.html，前端 fetch 会拿到一段 HTML，只报一句
        # 难以定位的 JSON 解析错误，排查成本远高于一个干净的 404。
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")

        # 真实文件优先（favicon、静态图等），其余一律交给前端路由。
        # 前端用 BrowserRouter，直接刷新 /books/01 这类深链必须回退到 index.html，
        # 否则用户一按 F5 就 404。
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="前端产物缺失")
        return FileResponse(index)


#: 前端构建产物。分发态随包分发；开发态通常不存在（页面走 Vite 的 :5173）。
#: 设 RSDS_SERVE_FRONTEND=0 可强制关闭托管（纯 API 调试）。
FRONTEND_DIST = resolve_web_dist() if should_serve_frontend() else None

if FRONTEND_DIST is not None:
    _mount_frontend(app, FRONTEND_DIST)
else:

    @app.get("/")
    async def root():
        """根路径：无前端产物时退化为 API 索引（开发态请走 Vite 的 :5173）。"""
        return {
            "name": "人生导师 API",
            "version": "1.0.0",
            "endpoints": {
                "books": "/api/books",
                "search": "/api/search?q=关键词",
                "ask": "POST /api/ask",
                "insight": "/api/insight/daily",
                "docs": "/docs",
            },
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
