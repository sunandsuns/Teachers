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
import shutil
import sys
import tempfile
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

#: 数据库文件名。刻意用 ASCII：用户未必会去翻它，但排查问题时命令行工具（以及各种
#: sqlite 客户端）对非 ASCII 路径并不都友好。定义在这里而不是存储层，是因为
#: :func:`resolve_data_dir` 要按"这个目录里有没有库"来判该不该接续旧数据。
DB_FILENAME = "history.db"

#: 部署态（线上容器）的数据目录：放在项目**外面**。
#: 线上发布上传的是整个项目目录，"项目里的 data/" 会被一次次覆盖，用户账号就跟着
#: 没了——所以库必须落在项目外。以前这件事靠发布时记得带 ``RSDS_DATA_DIR=/data``，
#: 漏一次就复现（发布工具的启动命令未必带着它）。把它写成代码默认，纪律就不再是
#: 唯一防线。容器是复用的，``/data`` 留得住。
DEPLOY_DATA_DIR = "/data"

#: 接续旧库时，一层目录最多看多少个子目录。这一步走在启动路径上，必须有上限：
#: 不能因为用户把程序放进了某个条目极多的目录，就让启动去遍历它。
_LEGACY_SCAN_LIMIT = 200

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
        # 相对路径按项目根解析，不跟着进程的工作目录漂——服务从别处启动时
        # （线上部署就是）cwd 未必是项目根，写相对路径就成了碰运气。
        target = Path(override).expanduser()
        candidates.append(target if target.is_absolute() else resolve_root() / target)

    bundle = bundle_dir()
    if bundle is not None:
        candidates.append(bundle / "web" / "dist")

    candidates.append(Path(__file__).resolve().parents[1] / "web" / "dist")

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def _user_data_dir() -> Path:
    """用户级数据目录：程序目录不可写（如放进 Program Files）时的落点。

    **不许抛异常**：这条路径的解析发生在启动阶段（lifespan 会碰一下历史库），
    抛一个异常就是整个应用起不来——而历史记录只是个附加项，为它赔上全部功能
    是本末倒置。

    这里兜的是 ``Exception`` 而不是某几种具体异常，因为已经栽过两次，两次都
    不是同一类：

    1. 容器里没有 ``HOME``，``Path.home()`` 抛 ``RuntimeError``；
    2. 容器里**有** ``HOME`` 的时候——下面那行少写了括号，``/`` 的优先级高于
       ``+``，表达式成了 ``(Path.home() / ".") + "renshengdaoshi"``，
       ``Path + str`` 抛 ``TypeError``。它既不是 ``RuntimeError`` 也不是
       ``OSError``，原先的 except 接不住，异常一路穿到接口层——线上凡是碰
       数据库的接口（回响、画像）**整片 500**，只有不碰库的页面还活着。
       本地开发永远看不到：Windows 上 ``LOCALAPPDATA`` 有值，函数在第一行
       就返回了，那一行根本没被执行过。

    教训是"想清楚会抛哪几种"这件事本身就不牢靠，而这个函数的失败代价是
    整个功能不可用，所以一律兜住。
    """
    try:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / USER_DATA_DIRNAME
        # 括号不能省，见上面第 2 次事故
        return Path.home() / ("." + "renshengdaoshi")
    except Exception:  # noqa: BLE001 — 本函数的契约就是"不许抛异常"
        pass
    # 退到临时目录：那里几乎总是可写，数据能不能留到下次另说，至少应用能起来。
    try:
        return Path(tempfile.gettempdir()) / "renshengdaoshi"
    except Exception:  # noqa: BLE001
        # 最后一道：连临时目录都问不出来时给个相对路径，交给调用方去 resolve。
        return Path(".") / "renshengdaoshi"


def _ensure_writable(path: Path) -> bool:
    """确保目录存在且可写。只做"建目录 + 权限探测"，不写探针文件——
    探针文件用完得删，而本项目所在环境对删除动作敏感（见 build_app.py 的说明）。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


#: 上一次"接续旧库"的结果：``(从哪来, 到哪去)``。启动日志会把它念出来——
#: "数据自己回来了"这件事必须让用户看见，否则他只会以为又丢了一次。
LAST_ADOPTION: Optional[tuple[str, str]] = None


def deploy_data_dir() -> Optional[Path]:
    """线上容器里的数据目录 ``/data``；本地开发返回 None。

    **只在非 Windows 上认**：Windows 下 ``Path("/data")`` 会落到当前盘符的根目录
    （``C:\\data``），本地开发被它劫持是纯粹的坏事，而容器是 Linux，这个闸门不会
    误伤线上。真正能不能用由调用方的 :func:`_ensure_writable` 决定——普通用户建不出
    ``/data`` 时它会安静地退到项目目录，不会把启动打挂。
    """
    if os.name == "nt":
        return None
    return Path(DEPLOY_DATA_DIR)


def _looks_like_database(path: Path) -> bool:
    """看文件头判断这是不是一个 SQLite 库。

    光按文件名认是不够的：一个叫 ``history.db`` 的文件在谁的机器上都不稀奇，
    而认错了就是把别人家的数据拷进用户的库。SQLite 的文件头是固定的，认不出来
    就当它不是，宁可少接一次也不接错。
    """
    try:
        if not path.is_file() or path.stat().st_size < 100:
            return False
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _previous_database_sources() -> list[Path]:
    """列出"上一次那一份"库可能在哪。

    形状只有一个：``<装着程序的文件夹>/人生导师/data/history.db``。

    带那层 ``人生导师`` 目录是刻意的——发布包解压出来必然是
    ``renshengdaoshi-v1.5.6-windows-x64/人生导师/…``，所以"旧版本文件夹"与
    "新版本文件夹"是同一层的兄弟，往上找一级就看到它了。反过来，开发机上仓库根
    目录那份 ``data/`` 没有这层外壳，天然被排除在外（那份库与打包版不是同一条链，
    接过来只会让人莫名其妙）。

    扫描范围只有 exe 的上两级及其下一层，而且**两个方向都封了顶**：相邻文件夹是
    有界的，一层套一层的目录（node_modules 之类）也走不进去。这一步在启动路径上，
    不能让它有机会去遍历一个几万条目的目录。
    """
    anchor = Path(sys.executable).resolve().parent
    sources: list[Path] = []

    def add(path: Path) -> None:
        if len(sources) < _LEGACY_SCAN_LIMIT:
            sources.append(path)

    def children_of(root: Path) -> list[Path]:
        """列一层子目录，条目数封顶。排序只为了结果稳定，便于测试。"""
        try:
            found = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            return []
        found.sort(key=lambda p: p.name)
        return found[:_LEGACY_SCAN_LIMIT]

    for root in (anchor.parent, anchor.parent.parent):
        add(root / USER_DATA_DIRNAME / DATA_DIRNAME / DB_FILENAME)
        for child in children_of(root):
            add(child / USER_DATA_DIRNAME / DATA_DIRNAME / DB_FILENAME)
            for grandchild in children_of(child):
                add(grandchild / USER_DATA_DIRNAME / DATA_DIRNAME / DB_FILENAME)

    # 程序目录不可写时库会退到用户级目录，那条路上的记录同样值得接过来
    add(_user_data_dir() / DB_FILENAME)
    return sources


def _adopt_previous_database(target: Path) -> Optional[Path]:
    """新版本第一次运行时，把上一次那一份记录接过来。

    桌面版的"升级"就是解压出一个新文件夹，而库在程序自己那份目录里——于是升级完
    一打开，账号、历史、书架全空了，用户的原话是"每次我更新版本数据库就没了"。
    旧库其实就在隔壁那棵 ``<旧版本文件夹>/人生导师/data/`` 里，这里把它找回来。

    三条纪律：

    1. **只在目标目录还没有库的时候做**。已经有一份就不动它（既有副本说了算，
       说明书承诺的"整个文件夹拷走，data 跟着走"不会被打断）；
    2. **只拷贝、不移动**。旧的那份原地留着，用户想回头还能找到，也不涉及删除；
    3. **找不到、拷不动都当没这回事**。接续成功是加分项，失败不该影响启动——
       大不了是"这一次没有历史记录"，而不是应用起不来。
    """
    if (target / DB_FILENAME).is_file():
        return None

    newest: Optional[Path] = None
    for candidate in _previous_database_sources():
        if not _looks_like_database(candidate):
            continue
        try:
            if candidate.resolve() == (target / DB_FILENAME).resolve():
                continue
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest.stat().st_mtime:
            newest = candidate
    if newest is None:
        return None

    # WAL 模式下的库由三个文件组成，只搬主文件会丢掉最近那些还没落盘的记录。
    # 源进程已退出（正被使用的库不会出现在这条路径上），三个文件一起读是自洽的。
    try:
        target.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            source = newest.with_name(newest.name + suffix)
            if source.is_file():
                shutil.copy2(source, target / (DB_FILENAME + suffix))
    except OSError:
        return None

    global LAST_ADOPTION
    LAST_ADOPTION = (str(newest), str(target))
    return target / DB_FILENAME


def resolve_data_dir() -> Path:
    """定位可写的运行期数据目录（历史记录数据库就落在这里）。

    解析顺序（先命中先返回）：

    1. 环境变量 ``RSDS_DATA_DIR``——测试用它把数据写进临时目录；
    2. 部署态（非 Windows + 非打包）：``/data``——**在项目外面**。理由见
       :data:`DEPLOY_DATA_DIR`：线上库一旦落在项目里，下次发布就把它覆盖了；
    3. 打包态：可执行文件同级的 ``data/``；
    4. 源码态：``PROJECT_ROOT / "data"``；
    5. 兜底：``%LOCALAPPDATA%/人生导师``。

    第 3、4 条指向"程序自己那一份"，好处是**拷贝即迁移**：把整个文件夹搬走，
    历史记录跟着走。但程序目录未必可写（放在 Program Files、或从只读介质
    运行），那种情况下写库会失败——最后那条兜底保证功能不至于直接没有。

    **会顺带把目录建出来**：这是刻意的，调用方（存储层）不需要再管"目录在不在"，
    而目录建不出来本身就是"该换下一个候选"的判据。

    打包态下如果选中的目录还没有库，会先试着从附近把上一次那一份接过来，见
    :func:`_adopt_previous_database`——**换一个新版本文件夹不再是换一个空库**。
    显式给了 ``RSDS_DATA_DIR`` 就跳过这一步：用户既然指定了地方，就别自作主张。
    """
    candidates: list[Path] = []
    explicit = False

    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        candidates.append(Path(override).expanduser())
        explicit = True

    if is_frozen():
        candidates.append(Path(sys.executable).resolve().parent / DATA_DIRNAME)
    else:
        deploy = deploy_data_dir()
        if deploy is not None:
            candidates.append(deploy)
        candidates.append(PROJECT_ROOT / DATA_DIRNAME)

    candidates.append(_user_data_dir())

    for candidate in candidates:
        if not _ensure_writable(candidate):
            continue
        if is_frozen() and not explicit:
            _adopt_previous_database(candidate)
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
