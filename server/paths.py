"""运行时路径解析：源码态与打包态共用同一套定位逻辑。

为什么单独成一个模块
--------------------------------------------------------------------------
源码态与打包态的目录布局不同——源码态靠 ``__file__`` 上溯，打包态靠可执行
文件同级目录。若让各模块各自上溯，打包后每一处都要单独改，而且漏改的后果
是**静默故障**：``.env`` 读不到表现为"AI 问答悄悄降级"，语料找不到表现为
"书架空空如也"，都不报错。

因此这里把「根目录在哪」「前端产物在哪」「可写的数据目录在哪」收拢为唯一入口，
其余模块只消费结果。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

#: 语料目录名（同时是判定"某目录是不是语料根"的依据）
NOTES_DIRNAME = "理解笔记"
BOOKS_DIRNAME = "books"
#: 历史人物候选池目录（figures.json + portraits/）。放语料根，
#: 用户加一个人只需丢一张图、加一条 JSON，不必重打包。
FIGURES_DIRNAME = "figures"

#: 运行期数据目录名（历史记录数据库所在）
DATA_DIRNAME = "data"
#: 用户级数据目录名：程序目录不可写时的兜底落点
USER_DATA_DIRNAME = "人生导师"

#: 显式指定语料根目录，优先级最高
ROOT_ENV_VAR = "RSDS_ROOT"
#: 显式指定前端构建产物目录
DIST_ENV_VAR = "RSDS_WEB_DIST"
#: 显式指定配置文件位置
ENV_FILE_VAR = "RSDS_ENV_FILE"
#: 显式指定运行期数据目录（数据库、缓存等）；测试靠它把数据写到临时目录
DATA_DIR_ENV_VAR = "RSDS_DATA_DIR"
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


def _user_data_dir() -> Path:
    """用户级数据目录：程序目录不可写（如放进 Program Files）时的落点。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / USER_DATA_DIRNAME
    return Path.home() / "." + "renshengdaoshi"


def _ensure_writable(path: Path) -> bool:
    """确保目录存在且可写。只做"建目录 + 权限探测"，不写探针文件——
    探针文件用完得删，而本项目所在环境对删除动作敏感（见 build_app.py 的说明）。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def resolve_data_dir() -> Path:
    """定位可写的运行期数据目录（历史记录数据库就落在这里）。

    解析顺序（先命中先返回）：

    1. 环境变量 ``RSDS_DATA_DIR``——测试用它把数据写进临时目录；
    2. 打包态：可执行文件同级的 ``data/``；
    3. 源码态：``PROJECT_ROOT / "data"``；
    4. 兜底：``%LOCALAPPDATA%/人生导师``。

    前三个都指向"程序自己那一份"，好处是**拷贝即迁移**：把整个文件夹搬走，
    历史记录跟着走。但程序目录未必可写（放在 Program Files、或从只读介质
    运行），那种情况下写库会失败——第 4 条兜底保证功能不至于直接没有。

    **会顺带把目录建出来**：这是刻意的，调用方（存储层）不需要再管"目录在不在"，
    而目录建不出来本身就是"该换下一个候选"的判据。
    """
    candidates: list[Path] = []

    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        candidates.append(Path(override).expanduser())

    if is_frozen():
        candidates.append(Path(sys.executable).resolve().parent / DATA_DIRNAME)
    else:
        candidates.append(PROJECT_ROOT / DATA_DIRNAME)

    candidates.append(_user_data_dir())

    for candidate in candidates:
        if _ensure_writable(candidate):
            return candidate.resolve()
    # 全军覆没：返回首选，让存储层去报"不可用"，而不是在这里抛异常
    # ——历史记录写不进去不该连带把书架、求教一起弄挂（见 services/db.py）。
    return candidates[0]


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
