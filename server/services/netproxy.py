"""出网时的代理开关。

为什么要有它
--------------------------------------------------------------------------
本机（以及一些部署环境）装了 http_proxy 但 no_proxy 只白名单了 localhost，
于是连自己机器上的服务都会被代理拦成 502。为此有两处代码各自实现了"绕过代理
直连"的开关：

- ``llm/transport.py`` —— 调模型
- ``book_search.py``    —— 查书

问题是它们读了**两个不同的环境变量**：前者认 ``LLM_NO_PROXY``，后者认
``RSDS_NO_PROXY``，而 ``.env.example`` 里只写了 ``LLM_NO_PROXY``。后者的
docstring 还写着"与 LLM 传输层同样的开关"——它不是。用户按文档设了变量，
换个功能照样被代理拦住，且没有任何提示。

统一在这里，两个名字都认（谁先设听谁的），这样既修好了对不上的地方，也不会
让已经写了 ``RSDS_NO_PROXY`` 的人配置失效。
"""

from __future__ import annotations

import os
import urllib.request

__all__ = ["NO_PROXY_ENV_VARS", "no_proxy_requested", "build_opener"]

#: 认的环境变量名。历史上分裂成两个，现在都保留。
NO_PROXY_ENV_VARS = ("LLM_NO_PROXY", "RSDS_NO_PROXY")

_TRUTHY = ("1", "true", "yes")


def no_proxy_requested() -> bool:
    """任一开关被设成真值即返回 True。空串、``0``、``false`` 都不算。"""
    for name in NO_PROXY_ENV_VARS:
        if os.environ.get(name, "").strip().lower() in _TRUTHY:
            return True
    return False


def build_opener() -> urllib.request.OpenerDirector:
    """按环境变量决定走不走代理的 opener。

    默认**遵循系统代理**（不设开关就不改变原有行为）；设了开关则用空代理
    handler，直接连出去。
    """
    if no_proxy_requested():
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()
