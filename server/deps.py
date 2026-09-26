"""FastAPI 依赖：从请求里解出当前用户。

放在独立模块而不是 ``routers/auth.py`` 里，是因为多个路由包（书架、后台、
历史、画像）都要用它。让它依赖 ``routers`` 下的某个模块会形成无谓的耦合。

三种粒度
--------------------------------------------------------------------------
- :func:`current_user` —— **可选**登录。解不出来就是 ``None``，不报错。
  现在几乎没人直接用它（路由级那道闸已经保证走到处理函数的请求都有身份），
  留着是因为 ``/api/auth/me`` 要靠它把"未登录"当成一个正常取值返回——
  前端据此决定摆出登录页还是正文。
- :func:`require_user` —— 必须登录，否则 401。
- :func:`require_admin` —— 必须是管理员，否则 403。

哪些接口要登录
--------------------------------------------------------------------------
**登录之前一个接口也不放行**——这套产品现在的入口就是登录页，登录之前一个
页面也看不了。界面上那道门之后，后端必须跟着收紧，否则它只是装饰：直接打
接口照样绕过去。

只有两组留开：

- ``/api/auth/*`` —— 登录注册本身。它要是也要登录，就没人进得来了。
- ``/api/health`` —— 探活用。部署平台拿它判断服务起没起来，它不该需要身份。

其余全部挂 ``require_user``（``/api/admin/*`` 更严，挂 ``require_admin``）。
实现统一用**路由级** ``dependencies=[Depends(require_user)]``，而不是在每个
处理函数上各写一遍：漏一个 handler 不会报错，只会安静地对匿名开放。

处理函数里那个 ``user: Optional[User] = Depends(current_user)`` 保留原样：
路由级已经保证有身份，所以它运行时不会是 ``None``；继续写成 Optional 是因为
``_owner()`` 要把"没有归属"这个取值交给 store 层，而库里可能还留着账号体系
上线之前那些 ``user_id IS NULL`` 的老数据。

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
