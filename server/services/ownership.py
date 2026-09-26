"""归属过滤：把"当前是谁"变成 SQL 条件。

单独成模块的理由
--------------------------------------------------------------------------
这条条件是**权限边界**，而它原先在 ``services/history.py`` 与
``services/profile.py`` 里各写了一份，两份逐字相同。

"两份必须永远一致"的代码，迟早会不一致——而这里一旦不一致，后果不是显示错乱，
是把别人的数据端出来。所以只留一份，并把"``None`` 不是不过滤"这件事讲清楚。

它和 ``deps.require_user`` 的分工
--------------------------------------------------------------------------
路由那一侧拿到的是**真实的** ``user.id``（路由级闸已经保证有身份），所以
``None`` 这一支在 router 路径里走不到。它存在是因为**服务层与 store 层要能直接
接收 ``None``**——库里还留着账号体系上线之前那些 ``user_id IS NULL`` 的老数据，
测试也会直接拿 ``None`` 调 store。也就是说：``None`` 是这个模块的合法输入，
不是"没人登录"的兜底。
"""

from __future__ import annotations

from typing import Optional


def scope_clause(user_id: Optional[int]) -> tuple[str, tuple]:
    """把"这份数据属于谁"变成一个 WHERE 片段，返回 ``(sql, 参数)``。

    ``None`` 是**匿名那一份**，不是"不过滤"。没有登录的人看到的是
    ``user_id IS NULL`` 的记录——登录功能上线之前留下的那些，以及匿名状态下新
    产生的那些。若把 ``None`` 当成"全部"，任何一次匿名读取都会把所有人的数据
    端出来，那正是加用户系统要防的事。

    调用时必须与其余条件用 ``AND`` 拼在同一条 SQL 里（见各 store 的用法）。
    """
    if user_id is None:
        return "user_id IS NULL", ()
    return "user_id = ?", (int(user_id),)
