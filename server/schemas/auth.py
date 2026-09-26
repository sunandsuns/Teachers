"""auth 接口的出入参。

从 ``routers/auth.py`` 搬来这里：契约是**双方的**，放在 HTTP 边界模块里
会让"接口长什么样"散落在十个路由文件中。
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

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
    email: str = Field(..., description="邮箱，同时是登录账号")
    display_name: str = Field(..., description="昵称；注册时留空则为空串")
    name: str = Field(..., description="界面上优先显示的名字：有昵称用昵称，没有就用邮箱 @ 之前那一段")
    is_admin: bool
    created_at: str


class MeResponse(BaseModel):
    user: Optional[UserInfo] = None
