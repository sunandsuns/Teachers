"""跨域共用的出入参。

放在这里而不是各域各写一份，是因为它们**逐字相同**：删除类接口的
``{"deleted": n}``、成功类接口的 ``{"ok": true}`` 原先在 history 与 profile 里
各定义了一遍 ``DeleteResponse``——两份定义、一个含义，改一处漏一处。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    """**所有**出错响应的形状。

    这是契约里最该显眼的一条：调用方只需要写一次错误处理。

    ``code`` 给机器读：按它分支（比如 ``bad_credentials`` 时把光标放回密码框），
    而不是去比中文文案——文案会随语言变。
    ``message`` 给人读：已经是可以直接展示的一句话。

    ``status`` 与 ``code`` 的对应由 ``server/errors.py`` 决定；这里只是形状。
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {"detail": {"code": "bad_credentials", "message": "邮箱或密码不正确"}}
    })

    code: str = ""
    message: str = ""


class DeleteResponse(BaseModel):
    """删除结果。``deleted`` 是实际删掉的条数——可能少于请求的条数。"""

    model_config = ConfigDict(title="DeleteResult")

    deleted: int


class OkResponse(BaseModel):
    """只要一个"成了"。

    那些没有别的话要回的写操作（登出、重置密码、改一行数据）用它，
    免得每个接口各返回一个裸 dict，在契约里留下一片空白。
    """

    ok: bool = True


class MessageResponse(BaseModel):
    """成了，而且有话要带给用户。"""

    ok: bool = True
    message: str = ""


class RowMutationResponse(BaseModel):
    """改/删数据库某一行。``rowid`` 只有插入时才有。"""

    ok: bool = True
    rowid: Optional[int] = None
