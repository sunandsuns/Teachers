"""可预期的业务错误：调用方做错了什么，而不是程序出了故障。

为什么放在 services 层
--------------------------------------------------------------------------
因为**服务层要抛它**。服务层不依赖 FastAPI（见 README 的分层说明），所以这里
只有语义与数据，不碰任何框架。把异常变成 HTTP 响应体的是 ``server/errors.py``，
那个模块才 import fastapi。两处同名容易看混，记住这条分界就行：
**这里定义"错在哪儿"，那里决定"回什么码"。**

为什么要有共同基类
--------------------------------------------------------------------------
``AuthError``、``UserBookError``、``AdminError`` 原先各自写了一遍 ``__init__``：
存下 ``code``、调 ``ValueError.__init__``。三个类逐字相同，只差一个默认 code。
更麻烦的在调用侧——三个 router 各自写了一个把异常转成 HTTP 的函数
（``_fail`` / ``_shelf_error`` / ``_admin_error``），那三个函数也逐字相同。

于是"业务错误长什么样"这件事一共有六份定义，改一处必然漏五处。现在只剩一份：
子类继承 :class:`DomainError` 并声明默认 code，转换交给一个全局 handler
（见 ``server/errors.py`` 的 ``install_error_handlers``）。
"""

from __future__ import annotations

from typing import Optional


class DomainError(ValueError):
    """业务错误：输入不合法、状态不允许、无权操作。

    继承 ``ValueError`` 而不是 ``Exception``，是为了让"这多半是调用方的问题"
    在代码里有个形状——服务层内部凡是接 ``ValueError`` 的地方都该想到它。

    ``code`` 给前端做分支（机器读），``message`` 直接展示给用户（人读，所以是中文）。
    """

    #: 子类覆盖它来指明"这是哪一类业务错误"；前端按这个值分支。
    default_code = "domain_error"

    #: 子类可按语义改写。默认 400——绝大多数业务错误是"你给的输入不对"。
    status_code = 400

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code
