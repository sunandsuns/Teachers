"""认证 API 路由：注册、登录、登出、当前用户、改密码。

token 同时写进 httpOnly cookie 与响应体：cookie 给浏览器用（JS 拿不到，
XSS 偷不走），响应体里的那一份给脚本与测试用。

为什么这一组不挂 ``require_user``
--------------------------------------------------------------------------
注册与登录本身要是也要登录，就没人进得来了。所以这是**全项目唯一一组**
不挂登录闸的路由——除了 ``/api/health``。

错误从哪来
--------------------------------------------------------------------------
``AuthError``（邮箱重复、密码太短）与 ``DatabaseUnavailable`` 都由
``server/errors.py`` 的全局出口转换，这里不再逐个 try/except。**唯一保留
try/except 的地方是登出**，理由见那个函数。
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..deps import COOKIE_NAME, current_user, require_user, token_from_request
from ..errors import BAD_REQUEST, DB_DOWN, UNAUTHORIZED, merge
from ..formatting import iso_time
from ..schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    UserInfo,
)
from ..schemas.common import MessageResponse, OkResponse
from ..services.auth import User, get_auth_store
from ..services.db import DatabaseUnavailable

#: 认证接口的错误面：会 401（凭据不对）、400（输入不合法）、503（库挂了）。
#: 没有 404——这一组不按 id 找东西。
router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    responses=merge(UNAUTHORIZED, BAD_REQUEST, DB_DOWN),
)


def user_info(user: User) -> UserInfo:
    """内部用户 → 对外的用户信息。

    是"转换"而不是"模型方法"：``schemas/`` 不放逻辑，而这里要调 ``iso_time``。
    唯一的调用方是 :class:`MeResponse` 与登录注册两处。
    """
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        name=user.name,
        is_admin=user.is_admin,
        created_at=iso_time(user.created_ts) or "",
    )


def _attach_session(response: Response, token: str, expires: float, request: Request) -> None:
    """把 token 写进 httpOnly cookie。

    ``secure`` 跟着请求的实际协议走：本地是 http，写死 ``secure=True`` 会让
    cookie 根本发不出去（浏览器只在 https 下发送 secure cookie），登录看起来
    就"成功了但没记住"。
    """
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=max(1, int(expires - time.time())),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/register", response_model=UserInfo, status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response):
    """注册并**直接登录**。

    注册完还要用户再登一次是多余的——他刚刚已经证明了自己知道密码。
    """
    store = get_auth_store()
    user = store.register(payload.email, payload.password, payload.display_name)
    token, expires = store.issue_token(user.id)
    _attach_session(response, token, expires, request)
    return user_info(user)


@router.post("/login", response_model=UserInfo)
def login(payload: LoginRequest, request: Request, response: Response):
    """登录。"""
    store = get_auth_store()
    store.purge_expired_sessions()  # 顺手清理，不必专门上定时任务
    user = store.authenticate(payload.email, payload.password)

    if user is None:
        # 刻意不区分"邮箱不存在"与"密码错误"：分开了就等于提供一个
        # 探测某个邮箱是否注册过的接口。
        raise HTTPException(
            status_code=401,
            detail={"code": "bad_credentials", "message": "邮箱或密码不正确"},
        )

    token, expires = store.issue_token(user.id)
    _attach_session(response, token, expires, request)
    return user_info(user)


@router.post("/logout", response_model=OkResponse)
def logout(request: Request, response: Response):
    """登出：删掉服务端那份会话，并清 cookie。

    即使 token 已经失效（过期、或本来就没有），也照样返回成功——登出这个
    动作的意图是"让我处于未登录状态"，而那个状态已经达成了。

    **这里是本文件唯一保留 try/except 的地方**：库不可用时照样得让用户登出。
    否则他点登出拿到 503，本地 cookie 却还在，界面看起来像"登出失败"。
    """
    token = token_from_request(request)
    if token:
        try:
            get_auth_store().revoke_token(token)
        except DatabaseUnavailable:
            pass
    response.delete_cookie(COOKIE_NAME, path="/")
    return OkResponse()


@router.get("/me", response_model=MeResponse)
def me(user: Optional[User] = Depends(current_user)):
    """当前用户。未登录时 ``user`` 为 ``null``，而不是 401。

    这是**唯一**用 ``current_user``（可选登录）的接口：它是前端每次启动都要问的
    "我是谁"，而"未登录"根本不是错误。做成 401 的话，匿名访客的每次页面加载
    都会在控制台留一条红字错误。
    """
    return MeResponse(user=user_info(user) if user else None)


@router.post("/password", response_model=MessageResponse)
def change_password(payload: ChangePasswordRequest, user: User = Depends(require_user)):
    """改自己的密码。成功后该用户的全部会话失效，需重新登录。"""
    store = get_auth_store()
    if store.authenticate(user.email, payload.old_password) is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_password", "message": "当前密码不正确"},
        )
    store.update_password(user.id, payload.new_password)
    return MessageResponse(message="密码已修改，请重新登录")
