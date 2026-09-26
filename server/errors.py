"""业务异常 → HTTP 响应，以及错误响应的声明。

与 ``services/errors.py`` 的分界
--------------------------------------------------------------------------
``services/errors.py`` 定义"错在哪儿"（纯语义，不碰框架）；这里决定"回什么码、
长什么样"。所以**这个模块是全项目唯一 import fastapi 的错误处理处**，服务层不碰它。

它管四件事
--------------------------------------------------------------------------
**1. 统一的错误体。** 所有出错响应都是 ``{"detail": {"code", "message"}}``，
形状定义在 ``schemas/common.py`` 的 :class:`ErrorBody`（契约住 schemas，
这里只负责把它填出来）。

原先有三种形状：``detail: "文本"``（``HTTPException`` 传字符串）、
``detail: {code, message}``（业务错误）、``detail: [{loc, msg}]``（422 校验）。
前端 ``api/client.ts`` 为此写了三段分支去猜"这次是哪种"——那三段就是形状不统一
收的税，而且是**每个**调用方都要交的税。现在只有一种，422 也收编进来了（见
``_validation_error``）。

**2. ``DomainError`` 的出口。** 业务异常不再由各 router 自己转。原先
``_fail`` / ``_shelf_error`` / ``_admin_error`` 三个转换函数逐字相同，
现在交给一个 handler。

**3. ``DatabaseUnavailable`` 的出口。** 库故障一律 503，原先 10 处手写。

注意这一条反过来约束了写法：**凡是需要"降级成空态"而不是 503 的地方，都得自己
try/except**。这样"偏离默认"的地方在代码里就看得见——全项目只有回响与画像两处
这么做，因为它们能在同一条响应里用 ``available: false`` 说清发生了什么，
而裸列表不行（返回 200 加空列表会和"真的没有"分不清）。

**4. 错误响应的声明。** 把 401/403/404/400/503 写进 OpenAPI。不写的话契约里只有
框架自动加的 422，调用方（包括以后生成的类型）不知道还会遇到什么。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas.common import ErrorBody
from .services.db import DatabaseUnavailable
from .services.errors import DomainError

#: 库故障时给用户看的那句话。只此一处，避免同一个意思出现两种文案
#: （原先后台说"数据库暂不可用"、认证与书架说"数据库暂不可用，请稍后再试"）。
DB_DOWN_MESSAGE = "数据库暂不可用，请稍后再试"


def _group(*specs: tuple[int, str]) -> dict[int, dict[str, Any]]:
    return {code: {"model": ErrorBody, "description": text} for code, text in specs}


# ── 单个错误码各自一组，拼装时按需取 ────────────────────────────────────────

UNAUTHORIZED = _group((401, "未登录或会话已过期"))
FORBIDDEN = _group((403, "已登录但权限不足（需要管理员）"))
NOT_FOUND = _group((404, "目标不存在"))
BAD_REQUEST = _group((400, "业务规则不通过，`code` 说明是哪一条"))
DB_DOWN = _group((503, "数据库不可用，稍后重试"))


def merge(*groups: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """把几组合成一个 ``responses=`` 参数。"""
    merged: dict[int, dict[str, Any]] = {}
    for group in groups:
        merged.update(group)
    return merged


# ── 路由级预设：router 声明时挑一个挂上 ────────────────────────────────────
# 挂路由级而不是每个 handler 各写一遍，理由与 `dependencies` 相同：
# 漏一个不会报错，只会让那个接口在契约里凭空少几种错误。

#: 普通登录路由：未登录 / 找不到 / 业务规则不过。
LOGGED_IN = merge(UNAUTHORIZED, NOT_FOUND, BAD_REQUEST)
#: 管理员路由：比上面多一个 403。
ADMIN_ONLY = merge(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, BAD_REQUEST)
#: 会碰数据库的登录路由：再多一个 503。
DB_BACKED = merge(LOGGED_IN, DB_DOWN)
#: 既碰数据库又要管理员。
ADMIN_DB = merge(ADMIN_ONLY, DB_DOWN)


# ── 转换 ────────────────────────────────────────────────────────────────────

#: 状态码 → 兜底 code。路由里那些 ``HTTPException(404, "书架里没有这本书")``
#: 没写 code，就按状态码给个通用值，前端至少能按大类分支。
CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    503: "db_unavailable",
}


def _body(code: str, message: str) -> dict[str, Any]:
    return {"detail": {"code": code, "message": message}}


def _normalize(detail: Any, status_code: int) -> dict[str, Any]:
    """把 FastAPI 的 ``detail`` 收成统一的 ``{code, message}``。

    业务错误本来就带着 ``code``（``{"code": ..., "message": ...}``），原样收下；
    普通的 ``HTTPException(404, "…")`` 只有一个字符串，code 按状态码兜底。
    """
    if isinstance(detail, dict) and ("code" in detail or "message" in detail):
        return _body(
            str(detail.get("code") or CODE_BY_STATUS.get(status_code, "")),
            str(detail.get("message") or ""),
        )
    return _body(CODE_BY_STATUS.get(status_code, ""), str(detail))


def install_error_handlers(app: FastAPI) -> None:
    """装上全局错误出口。由 ``main.py`` 在装配阶段调用一次。"""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        """业务错误：调用方做错了什么，码由异常自己声明。"""
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, str(exc)))

    @app.exception_handler(DatabaseUnavailable)
    async def _db_down(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
        """库故障：503。**只有**明确想降级成空态的地方才该在此之前把它接住。"""
        return JSONResponse(
            status_code=503, content=_body("db_unavailable", DB_DOWN_MESSAGE)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """路由里直接 raise 的那些（404 找不到、401 未登录）。

        注册在 Starlette 的基类上，所以 ``fastapi.HTTPException`` 一并走这里。
        """
        return JSONResponse(
            status_code=exc.status_code,
            content=_normalize(exc.detail, exc.status_code),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """422：请求参数没过 Pydantic 校验。

        收成一整句而不是原样的 ``[{loc, msg}]`` 数组：前端拿到数组也只能取第一条
        的 ``msg`` 显示（见 ``api/client.ts`` 原先那段分支），保留数组只是把"自己
        挑一条"这件事推给每个调用方。字段路径拼进消息里，定位信息不丢。
        """
        errors = exc.errors()
        first = errors[0] if errors else {}
        # loc 形如 ("body", "question")，去掉最前面那层来源，只留字段路径
        parts = [str(part) for part in first.get("loc", ()) if part != "body"]
        message = first.get("msg") or "请求参数不合法"
        return JSONResponse(
            status_code=422,
            content=_body("validation", f"{'.'.join(parts)}: {message}" if parts else message),
        )
