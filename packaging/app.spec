# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把「人生导师」打成免安装的桌面应用。

产物形态：**目录式**（onedir），不是单文件
--------------------------------------------------------------------------
单文件 exe 每次启动都要把上百 MB 解压到临时目录，冷启动十秒起步，而且国产
杀软对"自解压 exe"的误报率明显更高。目录式启动是秒级，代价只是多一层文件夹——
而语料本来就要作为可增补的数据放在 exe 之外，单文件也躲不掉这层文件夹。

目录结构（由 build_app.py 在打包后补齐语料与配置）::

    人生导师/
        人生导师.exe        入口
        _internal/          运行时与依赖（PyInstaller 管理）
        .env                模型配置，放在 exe 旁边便于用户替换
        corpus/             语料，用户可自行增补
            理解笔记/ books/ MaoZeDongAnthology/ WangYangMing/
        启动说明.txt

为什么语料不进包
--------------------------------------------------------------------------
语料是**可增补的数据**：用户会往里加笔记、扩感悟池。塞进包内则每次启动多解压
一份，也堵死了用户自己扩充的路。解析规则见 ``server/paths.py::resolve_root``。
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

#: 仓库根 = 本 spec 所在目录的上一级
ROOT = os.path.dirname(os.path.abspath(SPECPATH))

datas = [
    # 前端构建产物随包分发：用户在浏览器里看不到 dist，也不会去改它
    (os.path.join(ROOT, "web", "dist"), os.path.join("web", "dist")),
    # 窗口图标：EXE 的图标资源由下面的 icon= 指定，但 pywebview 创建窗口时
    # 还要按路径读一次，所以要作为数据文件一并带上
    (os.path.join(ROOT, "assets", "app.ico"), os.path.join("assets")),
]
# jieba 的词典是数据文件。漏掉不会报错，只会让分词退化成逐字切分——
# 检索质量悄悄变差，属于最难发现的那类故障。
datas += collect_data_files("jieba")

hiddenimports = [
    # uvicorn 的协议/事件循环/lifespan 实现是按名字符串动态导入的，
    # 静态分析看不见。漏掉的表现是"服务起不来，但日志里什么都没有"。
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # 纯 API 调试时可能关掉前端托管，这条路径也要能用
    "server.routers.ask",
    "server.routers.books",
    "server.routers.insight",
    "server.routers.search",
]
# 窗口层：Windows 上 pywebview 走 WebView2，宿主是 .NET WinForms（pythonnet）
hiddenimports += collect_submodules("webview")

excludes = [
    # 全是本应用用不到的重型依赖，剔掉能显著缩小体积、也少一堆杀软误报面
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "httpx",
]

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="人生导师",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 桌面应用不该弹出黑色控制台窗口；启动信息与异常写进「启动日志.txt」
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="人生导师",
)
