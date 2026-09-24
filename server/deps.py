"""FastAPI 依赖：从请求里解出当前用户。

放在独立模块而不是 ``routers/auth.py`` 里，是因为多个路由包（书架、后台、
历史、画像）都要用它。让它依赖 ``routers`` 下的某个模块会形成无谓的耦合。

三种粒度
--------------------------------------------------------------------------
- :func:`current_user` —— **可选**登录。解不出来就是 ``None``，不报错。
  这是"未登录也能浏览公共书架、检索、求教"的实现方式。
- :func:`require_user` —— 必须登录，否则 401。
- :func:`require_admin` —— 必须是管理员，否则 403。

token 从哪读
--------------------------------------------------------------------------
优先 ``Authorization: Bearer``，其次 httpOnly cookie。两条都支持是因为：
浏览器走 cookie（省得 JS 碰 token，XSS 偷不走），脚本与冒烟测试走 header
（curl 带 cookie 很啰嗦）。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request

from .services.auth import User, get_auth_store

#: 会话 cookie 名。带项目前缀，免得和同域下别的应用撞名。
COOKIE_NAME = "rsds_session"


def token_from_request(request: Request) -> str:
    """按优先级从请求里取 token；取不到返回空串。"""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE_NAME, "") or ""


def current_user(request: Request) -> Optional[User]:
    """当前用户，未登录返回 ``None``。"""
    token = token_from_request(request)
    if not token:
        return None
    return get_auth_store().resolve_token(token)


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    """必须登录。"""
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """必须是管理员。

    先走 ``require_user`` 再判 ``is_admin``：未登录返回 401（"你去登录"），
    已登录但非管理员返回 403（"你没权限"）——这两种情况该给用户的提示不同。
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
