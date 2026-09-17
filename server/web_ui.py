"""前端产物托管：把 ``web/dist`` 挂到 API 的同一端口，实现单进程同源部署。

从 ``main.py`` 搬出来，是因为它与"应用装配"无关——这是一段独立的静态资源
服务逻辑，且带着一处极易踩错的顺序约束（见 :func:`mount_frontend` 的说明），
单独成文件比夹在装配代码里更容易被读到。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

#: 前端单页应用的入口文件
INDEX_HTML = "index.html"


def mount_frontend(application: FastAPI, dist: Path) -> None:
    """把前端构建产物挂到同一端口，实现单进程同源部署。

    必须在**所有 API 路由注册完毕之后**调用：SPA 回退会吞掉一切未匹配的 GET，
    排在前面会把 ``/api/*`` 与 FastAPI 自带的 ``/docs`` 一并截胡。
    本函数内部注册的回退路由同样如此——Starlette 按注册顺序匹配，
    先注册的回退会盖住后注册的接口。
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
        index = dist / INDEX_HTML
        if not index.is_file():
            raise HTTPException(status_code=404, detail="前端产物缺失")
        return FileResponse(index)
