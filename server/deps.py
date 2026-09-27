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

处理函数里要身份就写 ``user: User = Depends(require_user)``，直接用 ``user.id``。
路由级那道闸已经保证了有身份，所以**不需要**再写成 ``Optional`` 然后到处
``user.id if user else None``——那个 ``else`` 分支永远走不到，只是一层伪装成
"兼容"的死代码。（原先 history / profile / ask / search / insight 五处都这么写，
现在只剩 ``/api/auth/me`` 一个接口用可选的 ``current_user``，因为它是真的允许
未登录。）

token 从哪读
--------------------------------------------------------------------------
**先 cookie，再 ``Authorization: Bearer``**——两者的顺序是踩出来的，不是随手排的。

部署平台的网关会往每一个进入后端的请求里注入它自己的
``Authorization: Bearer <JWT>``（那是网关的身份，不是本应用的）。原先写成
"header 优先"，于是后端每次都在验网关那串东西，而用户自己那枚 cookie
**从头到尾没被看过**。表现就是"登录返回 200、此后的接口全被当成匿名"，而且
从外部完全看不出问题在哪：token 明明送达了，只是被另一条头挤掉了。

所以反过来：

1. **有自己的 cookie 就用 cookie**——浏览器走这条，它带着 httpOnly 的 token，
   不经过 JS，最安全。
2. 没有 cookie 时才看 ``Authorization``，并且要求它**形状确实是本应用的 token**
   （见 :data:`_TOKEN_RE`）。网关那个 JWT 是 ``43.298.43`` 三段，第二段不是
   纯数字，自然被排除；脚本与冒烟测试用 ``Bearer`` 则照常工作。

两条都支持的原因没变：浏览器用 cookie（XSS 偷不走），脚本用 header（curl 带
cookie 很啰嗦）。
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import Depends, HTTPException, Request

from .services.auth import User, get_auth_store

#: 会话 cookie 名。带项目前缀，免得和同域下别的应用撞名。
COOKIE_NAME = "rsds_session"

#: 本应用 token 的形状：``{用户 id}.{过期时刻}.{签名}``。
#:
#: 签名是 ``base64url(HMAC-SHA256(...))`` 去掉 padding，32 字节恒为 43 字符。
#: 用它把"自己人"和"别人塞进来的凭据"分开——网关注入的 JWT 第二段是长串
#: base64，不是数字，因此匹配不上。**别把它放宽**：放宽了就等于把别人的凭据
#: 也拖进验签路径，又会退回到"用户自己的 cookie 被挤掉"那个坑里。
_TOKEN_RE = re.compile(r"^\d{1,12}\.\d{1,12}\.[A-Za-z0-9_-]{43}$")


def token_from_request(request: Request) -> str:
    """按优先级从请求里取 token；取不到返回空串。

    顺序是 **cookie → Authorization**，理由见模块开头"token 从哪读"。
    """
    cookie_token = request.cookies.get(COOKIE_NAME, "") or ""
    if cookie_token:
        return cookie_token
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        candidate = header[7:].strip()
        if _TOKEN_RE.match(candidate):
            return candidate
    return ""


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
