"""内部取值 → 接口上的表示。

现在只有一件事：时间戳 → 带时区偏移的 ISO 8601。

为什么值得单独一个模块
--------------------------------------------------------------------------
这个函数原先被抄了**四份**，而且已经不是同一个函数了：

- ``routers/admin.py``、``routers/auth.py``、``routers/shelf.py`` 三份按 **UTC**
  输出（``+00:00``），空值给**空串**；
- ``services/history.py`` 一份按**本地时区**输出（``+08:00``），空值给 ``None``。

两种写法在浏览器里其实是等价的：前端一律走 ``new Date(...)``（见
``features/admin/constants.ts`` 的 ``shortTime`` 与 ``features/history/format.ts``
的 ``formatTime``），带偏移量的 ISO 8601 解析出来是同一个瞬间。但"同一个函数
有四种实现"本身就是 bug 的温床——改一处忘了另三处，表现出来就是列表里某一列
的时间跟别处差八小时，而且没人会立刻发现。

统一到**本地时区带偏移量**：它是四份里占多数的那种，而且人直接看接口输出、
看日志时不用在脑子里做时区换算。偏移量写在字符串里，所以不存在歧义。

空值为什么不统一
--------------------------------------------------------------------------
因为两边的需要正好相反，且都是对的：

- ``services/history.py`` 的 ``status()`` 要把"从没清理过"表示成 ``null``；
- ``Record.created_at`` 与 ``routers/admin.py`` 的字段声明是 ``str``，要空串。

把"空值给什么"塞进公共函数，就等于替所有调用点做了这个决定。所以这里原样返回
``None``，要空串的地方自己写 ``or ""``——那是个显示决定，摆在调用点上才看得见。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def iso_time(ts: Optional[float]) -> Optional[str]:
    """时间戳 → 带时区偏移的 ISO 8601（前端 ``new Date(…)`` 能直接解析）。

    空值原样返回 ``None``；需要 ``str`` 的调用点自己写 ``or ""``。
    """
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
