"""运行时路径解析：源码态与打包态共用同一套定位逻辑。

为什么单独成一个模块
--------------------------------------------------------------------------
源码态与打包态的目录布局不同——源码态靠 ``__file__`` 上溯，打包态靠可执行
文件同级目录。若让各模块各自上溯，打包后每一处都要单独改，而且漏改的后果
是**静默故障**：``.env`` 读不到表现为"AI 问答悄悄降级"，语料找不到表现为
"书架空空如也"，都不报错。

因此这里把「根目录在哪」「前端产物在哪」收拢为唯一入口，其余模块只消费结果。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

#: 语料目录名（同时是判定"某目录是不是语料根"的依据）
NOTES_DIRNAME = "理解笔记"
BOOKS_DIRNAME = "books"

#: 显式指定语料根目录，优先级最高
ROOT_ENV_VAR = "RSDS_ROOT"
#: 显式指定前端构建产物目录
DIST_ENV_VAR = "RSDS_WEB_DIST"
#: 显式指定配置文件位置
ENV_FILE_VAR = "RSDS_ENV_FILE"
#: 设为 0/false/no/off 时，即使 web/dist 存在也不由后端托管（纯 API 调试用）
SERVE_ENV_VAR = "RSDS_SERVE_FRONTEND"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 等打包器产出的可执行文件里。"""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Optional[Path]:
    """打包器的资源解包目录（PyInstaller 为 ``sys._MEIPASS``）；源码态返回 None。"""
    if not is_frozen():
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(sys.executable).resolve().parent


def resolve_root() -> Path:
    """定位语料与 ``.env`` 所在的根目录。

    解析顺序（先命中先返回）：

    1. 环境变量 ``RSDS_ROOT``——启动器或用户显式指定；
    2. 打包态：可执行文件同级的 ``corpus/``，没有则退回 exe 同级目录本身；
    3. 源码态：``server/paths.py`` 上溯两层（即仓库根）。

    语料刻意留在可执行文件之外：它是**可增补的数据**（新增笔记、扩感悟池），
    塞进包内既让每次启动多解压一份，也堵死了用户自己往里加东西的路。
    """
    override = os.environ.get(ROOT_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir / "corpus", exe_dir):
            if (candidate / NOTES_DIRNAME).is_dir() or (candidate / BOOKS_DIRNAME).is_dir():
                return candidate
        # 兜底仍返回 exe 同级目录：语料可能缺失，但 .env 至少读得到
        return exe_dir

    return Path(__file__).resolve().parents[1]


def resolve_web_dist() -> Optional[Path]:
    """定位前端构建产物 ``web/dist``；找不到返回 None。

    打包态优先取解包目录内的副本——dist 是构建产物、用户不会去改，随包分发
    最省事；``RSDS_WEB_DIST`` 可指向任意目录，便于本地调试。
    """
    candidates: list[Path] = []

    override = os.environ.get(DIST_ENV_VAR)
    if override:
        candidates.append(Path(override).expanduser())

    bundle = bundle_dir()
    if bundle is not None:
        candidates.append(bundle / "web" / "dist")

    candidates.append(Path(__file__).resolve().parents[1] / "web" / "dist")

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def should_serve_frontend() -> bool:
    """后端是否托管前端静态产物。"""
    value = os.environ.get(SERVE_ENV_VAR)
    if value is None or value == "":
        return True
    return value.strip().lower() not in ("0", "false", "no", "off")


def resolve_env_file() -> Optional[Path]:
    """定位 ``.env``，找不到返回 None（此时纯靠环境变量与内置默认值）。

    解析顺序（先命中先返回）：

    1. 环境变量 ``RSDS_ENV_FILE``——启动器或用户显式指定；
    2. 打包态：**可执行文件同级**的 ``.env``；
    3. ``PROJECT_ROOT / ".env"``——源码态即仓库根。

    打包态刻意把 ``.env`` 放在程序根目录而不是语料目录里：语料收在 ``corpus/``
    下是为了整齐，但配置文件是用户最可能去翻、去改的东西，埋进数据目录等于
    藏起来。放在 exe 旁边，替换 Key 就是编辑一个一眼可见的文件。
    """
    candidates: list[Path] = []

    override = os.environ.get(ENV_FILE_VAR)
    if override:
        candidates.append(Path(override).expanduser())

    if is_frozen():
        candidates.append(Path(sys.executable).resolve().parent / ".env")

    candidates.append(PROJECT_ROOT / ".env")

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


#: 进程级一致的根目录快照，供各模块导入
PROJECT_ROOT = resolve_root()
