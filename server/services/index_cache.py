"""检索索引的落盘缓存：把建索引的十秒省掉九秒。

为什么要落盘
--------------------------------------------------------------------------
建索引约十秒，其中 98% 花在 jieba 分词上——**每次启动都要重来一遍**（无热重载，
改一行后端就得重启）。而语料是随包发布的只读文件，昨天算出来的分词结果今天
仍然有效。把它存下来，启动就只剩"读文件 + 建倒排表"。

信任的边界
--------------------------------------------------------------------------
缓存最坏的结果不是"没命中"，而是**命中了却不对**：拿一份按旧语料、或按旧切段
规则建的索引去回答今天的问题，结果与界面上的原典对不上，而且**不会报任何错**。
所以这里只做一件事——把"这份缓存是不是当前代码、当前语料算出来的"变成一道
必须通过的校验：

1. :data:`PAYLOAD_VERSION`——载荷结构变了（加字段、改语义）就 +1；
2. ``signature``——调用方给的索引逻辑签名（见 ``retriever.INDEX_LOGIC``）；
3. **语料指纹**——进索引的每一份内容都哈希一遍。

三条缺一不可，任何一条对不上都当成"没有缓存"，老老实实重建。
**宁可白花十秒，不能用一份对不上的索引。**

为什么指纹要哈希内容，而不是看 mtime 或文件大小
--------------------------------------------------------------------------
``mtime`` 在重新 clone、解压、换台机器之后全变，会白白重建一次；而文件大小
判不出"改了个错别字、字数没变"——那恰恰是最危险的一种改动：索引与语料说的
不是同一件事，界面上却看不出任何异常。哈希一遍十几 MB 只要几十毫秒，
换来的是"**只要对得上就一定是对的**"。

本模块的契约
--------------------------------------------------------------------------
读不出来、写不进去、目录不可写、文件被清掉、内容被截断——一律当作"没有缓存"
或"没写成功"，**不抛异常**。这条路径上的任何失败都不该影响应用启动。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol

from ..paths import resolve_data_dir

#: 载荷结构版本。**改了 ``documents`` / ``tf`` / ``df`` 的字段或含义就 +1。**
#: 与语料指纹分开维护：语料没变、只是缓存格式改了时，靠这一条让旧文件失效，
#: 不必去猜"是不是内容也变了"。
PAYLOAD_VERSION = 1

#: 缓存文件名。放在运行期数据目录里（``data/``），与历史记录库同一个落点——
#: 打包态可执行文件旁边，拷走整个文件夹缓存就跟着走。
CACHE_FILENAME = "retrieval-index.json.gz"

#: 关掉缓存的开关。设成 ``0`` / ``false`` / ``no`` / ``off`` 就不读也不写。
#: 两个用途：怀疑"用了过期索引"时一键排除掉这个变量；测试里索引只建一次、
#: 而每个用例各有各的临时数据目录，写了也没机会读到（见 ``tests/conftest.py``）。
ENV_VAR = "RSDS_INDEX_CACHE"

_FALSY = frozenset({"0", "false", "no", "off"})

#: 压缩级别。**刻意用 1 而不是默认的 9。**
#: 实测这份载荷：级别 1 压 0.20s / 8.4MB，级别 6 压 0.77s / 7.3MB，而两者
#: 解压都是 0.06s。多花的那半秒落在**用户正等着应用起来的那一刻**（首次启动、
#: 升级后首次启动），换回来的只是少 1MB 磁盘和每次启动少读 1MB——启动路径上，
#: 快比小重要。
_GZIP_LEVEL = 1


class _Corpus(Protocol):
    """本模块对内容加载器的最小要求（只为类型标注，不构成运行时依赖）。

    刻意不 import ``ContentLoader``：缓存层不该知道语料是怎么加载的，
    只该知道"能问它要书目、能问它要原典全文"。
    """

    def get_books(self) -> list[Any]:
        """全部书目（每项要有 ``book_id`` 与 ``chapters``）。"""
        ...

    def get_source_text(self, book_id: str) -> Optional[str]:
        """某本书的原典全文；没有则 None。"""
        ...


def enabled() -> bool:
    """落盘缓存是否启用。没设这个环境变量就是启用。"""
    value = os.environ.get(ENV_VAR)
    if value is None or value == "":
        return True
    return value.strip().lower() not in _FALSY


def cache_file() -> Path:
    """缓存文件的位置。

    每次都去问 :func:`paths.resolve_data_dir`，不在这里缓存结果——那个函数
    顺带保证目录存在，而数据目录本身可能因环境变量变化而改变（测试就是这么做的）。
    """
    return resolve_data_dir() / CACHE_FILENAME


def corpus_fingerprint(loader: _Corpus, signature: str) -> str:
    """语料指纹 = 索引逻辑签名 + 进索引的每一份内容。

    ``signature`` 由调用方给（见 ``retriever.INDEX_LOGIC``）：它代表"怎么切段、
    用什么分词器"，而那件事不在语料里，哈希多少内容都推不出来。

    原典**全都要算**，包括因体量过大而没进索引的那几本——"跳过"这个判断是根据
    长度做的，长度一变它就可能不再跳过。
    """
    digest = hashlib.sha256()
    digest.update(signature.encode("utf-8"))
    for book in sorted(loader.get_books(), key=lambda b: b.book_id):
        digest.update(book.book_id.encode("utf-8"))
        for chapter in book.chapters:
            digest.update(chapter.chapter_id.encode("utf-8"))
            digest.update(chapter.content.encode("utf-8"))
        digest.update((loader.get_source_text(book.book_id) or "").encode("utf-8"))
    return digest.hexdigest()


def read(path: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    """读出载荷；不可用时返回 None。

    文件不在、解压失败、不是合法 JSON、结构版本对不上、指纹对不上——全部一视同仁。
    调用方只需要判断"拿到还是没拿到"，不需要区分是哪一种。
    """
    if not enabled():
        return None
    try:
        # 一次读进来、一次解压、一次解析。**不要写成 ``gzip.open(...)``
        # 再 ``json.load(handle)``**：那样 json 会分几十次小批量写进去、压缩器
        # 跟着被反复初始化，实测同一份数据要多花近两倍时间（2.5s → 0.9s）。
        blob = path.read_bytes()
        payload = json.loads(gzip.decompress(blob).decode("utf-8"))
    except Exception:  # noqa: BLE001 — 读不出来只意味着"重新建一次"
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != PAYLOAD_VERSION:
        return None
    if payload.get("fingerprint") != fingerprint:
        return None
    return payload


def write(path: Path, payload: dict[str, Any]) -> bool:
    """原子写入；返回是否写成功，**不抛异常**。

    先写同目录的临时文件、再 ``os.replace`` 换入。直接写目标文件的话，写到一半
    失败（磁盘满、进程被杀）会留下一个半截文件，下次启动读到它只会当成"损坏"
    再重建、可能又写坏，用户就陷在"重建 → 写坏"的循环里。同一文件系统内
    ``os.replace`` 是原子的。

    临时文件名带 pid：两个进程同时启动时不会互相写坏对方那一份。
    """
    if not enabled():
        return False
    tmp: Optional[Path] = None
    try:
        # 临时文件也放进 try 里：连"给这个路径拼一个兄弟名"都可能因路径形态
        # 古怪而抛（比如带盘符冒号的名字），而这条路径的契约是**不抛异常**。
        tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
        path.parent.mkdir(parents=True, exist_ok=True)
        # 先序列化、再压缩、最后一次性写盘——理由同 ``read``：让 gzip 的流式
        # 包装器按小批量喂数据，压缩器要反复初始化，白白多花两倍时间。
        # 代价是序列化结果（二十几 MB 字符串）会短暂驻留内存，换来启动时
        # 少等一秒多，划算。
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        tmp.write_bytes(gzip.compress(text.encode("utf-8"), compresslevel=_GZIP_LEVEL))
        os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001 — 写不进去就下次再建，不该影响启动
        return False
    finally:
        # 兜住失败时残留的临时文件。这一句也要吞异常：删不掉不该反过来
        # 把"没写成功"变成"抛了个异常出去"。
        try:
            if tmp is not None and tmp.exists():
                tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
