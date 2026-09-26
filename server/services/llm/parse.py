"""从模型回复里抠出 JSON。

为什么要有它
--------------------------------------------------------------------------
模型很少规规矩矩只回一段 JSON：常见的是包在 ```json 围栏里，或者前面先来一句
"好的，以下是我的判断"。两处功能（``profile`` 归纳画像、``figures`` 评定最像
的人物）各自写了一遍同样的抠取逻辑——**围栏剥离那几行是逐字相同的**，唯一的
差别是"要找的是对象还是数组"。

两份抄本的危险不在于长，而在于它们会各自演化：一边改了正则、另一边没改，
于是同一份模型输出在画像里能解析、在评定里就解析不出来。统一在这里。

只管抠，不管解析
--------------------------------------------------------------------------
返回的是**字符串**，不做 ``json.loads``。因为"解析不出来"在两处的后果不同
（画像里是空列表、评定里是空 id），兜底语义属于调用方。这层一旦开始返回
解析好的对象，就得同时决定失败时返回什么，那就把手伸得太长了。
"""

from __future__ import annotations

import re

__all__ = ["FENCED_JSON", "extract_json_block"]

#: 模型常把 JSON 包在围栏里；``` 后面可能跟也可能不跟 ``json`` 这个标记
FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json_block(raw: str, *, array: bool = False) -> str:
    """从模型输出里抠出最像 JSON 的一段。

    ``array=True`` 找 ``[...]``，否则找 ``{...}``。

    没有围栏时退化成"从第一个开括号到最后一个闭括号"：模型在 JSON 后面再补一句
    解释是常事（"以上是我的判断"），取这两端之间的内容照样解析得出来。用
    ``rfind`` 找闭括号而不是 ``find``，就是为了盖住这种情况。

    纯文本处理，不抛异常、不校验 JSON 合法性——那是调用方的事。
    """
    fenced = FENCED_JSON.search(raw)
    if fenced:
        return fenced.group(1).strip()
    opener, closer = ("[", "]") if array else ("{", "}")
    start, end = raw.find(opener), raw.rfind(closer)
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw.strip()
