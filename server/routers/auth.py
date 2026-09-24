"""认证 API 路由：注册、登录、登出、当前用户。

token 同时写进 httpOnly cookie 与响应体：cookie 给浏览器用（JS 拿不到，
XSS 偷不走），响应体里的那一份给脚本与测试用。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..deps import COOKIE_NAME, current_user, require_user, token_from_request
from ..services.auth import AuthError, User, get_auth_store
from ..services.db import DatabaseUnavailable

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=254, description="邮箱，即账号")
    password: str = Field(..., max_length=200, description="密码，至少 8 位")
    display_name: str = Field("", max_length=60, description="昵称，可留空")


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class UserInfo(BaseModel):
    """对外的用户信息。**绝不包含密码哈希与 salt。**"""

    id: int
    email: str
    display_name: str
    name: str
    is_admin: bool
    created_at: str


class MeResponse(BaseModel):
    user: Optional[UserInfo] = None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def user_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        name=user.name,
        is_admin=user.is_admin,
        created_at=_iso(user.created_ts),
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


def _fail(exc: AuthError) -> HTTPException:
    """把业务错误转成 400，带上机器可读的 code 供前端分支。"""
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.post("/register", response_model=UserInfo, status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response):
    """注册并**直接登录**。

    注册完还要用户再登一次是多余的——他刚刚已经证明了自己知道密码。
    """
    store = get_auth_store()
    try:
        user = store.register(payload.email, payload.password, payload.display_name)
    except AuthError as exc:
        raise _fail(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用，请稍后再试") from exc

    token, expires = store.issue_token(user.id)
    _attach_session(response, token, expires, request)
    return user_info(user)


@router.post("/login", response_model=UserInfo)
def login(payload: LoginRequest, request: Request, response: Response):
    """登录。"""
    store = get_auth_store()
    try:
        store.purge_expired_sessions()  # 顺手清理，不必专门上定时任务
        user = store.authenticate(payload.email, payload.password)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用，请稍后再试") from exc

    if user is None:
        # 刻意不区分"邮箱不存在"与"密码错误"
        raise HTTPException(
            status_code=401,
            detail={"code": "bad_credentials", "message": "邮箱或密码不正确"},
        )

    token, expires = store.issue_token(user.id)
    _attach_session(response, token, expires, request)
    return user_info(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    """登出：删掉服务端那份会话，并清 cookie。

    即使 token 已经失效（过期、或本来就没有），也照样返回成功——登出这个
    动作的意图是"让我处于未登录状态"，而那个状态已经达成了。
    """
    token = token_from_request(request)
    if token:
        try:
            get_auth_store().revoke_token(token)
        except DatabaseUnavailable:
            pass
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: Optional[User] = Depends(current_user)):
    """当前用户。未登录时 ``user`` 为 ``null``，而不是 401——前端启动时
    就靠它区分"没登录"和"登录已过期"，返回 401 反而要多写一层错误处理。"""
    return MeResponse(user=user_info(user) if user else None)


@router.post("/password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(require_user)):
    """改自己的密码。成功后该用户的全部会话失效，需重新登录。"""
    store = get_auth_store()
    try:
        if store.authenticate(user.email, payload.old_password) is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "bad_password", "message": "当前密码不正确"},
            )
        store.update_password(user.id, payload.new_password)
    except AuthError as exc:
        raise _fail(exc) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用，请稍后再试") from exc
    return {"ok": True, "message": "密码已修改，请重新登录"}
