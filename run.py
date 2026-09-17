#!/usr/bin/env python3
"""一键启动开发环境：后端 (uvicorn) + 前端 (vite)。

在项目根目录执行：

    python run.py                    # 后端 :8000，前端 :5173
    python run.py --reload           # 后端开热重载
    python run.py --backend-port 8011
    python run.py --backend-only     # 只起后端

按 Ctrl+C 会尝试一并结束后端与前端进程。
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173


def _port_free(port: int) -> bool:
    """探测端口是否可绑定（IPv4 与 IPv6 都试）。"""
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((addr, port))
        except OSError:
            return False
    return True


def _pick_port(preferred: int, label: str) -> int:
    """优先用 preferred；被占用时向后找第一个空闲端口并提示。"""
    if _port_free(preferred):
        return preferred
    for candidate in range(preferred + 1, preferred + 50):
        if _port_free(candidate):
            print(f"[提示] {label}端口 {preferred} 已被占用，改用 {candidate}")
            return candidate
    print(f"[错误] {label}端口 {preferred}–{preferred + 49} 均被占用", file=sys.stderr)
    raise SystemExit(1)


def _frontend_command(port: int) -> Optional[list[str]]:
    """构造前端启动命令；npm 缺失时返回 None。

    Windows 上 npm 是 ``npm.cmd``，必须经 ``cmd /c`` 调用，
    因此这里显式包装而不依赖 shell=True。
    """
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        return None
    script = [npm, "run", "dev", "--", "--port", str(port)]
    return ["cmd", "/c", *script] if os.name == "nt" else script


def _backend_command(port: int, reload: bool) -> list[str]:
    command = [
        sys.executable, "-m", "uvicorn", "server.main:app",
        "--host", "127.0.0.1", "--port", str(port),
    ]
    if reload:
        command.append("--reload")
    return command


def _check_prerequisites() -> Optional[str]:
    """返回首个阻塞性问题；无问题返回 None。"""
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        return "缺少后端依赖，请先执行：pip install -r server/requirements.txt"
    if not (WEB_DIR / "node_modules").is_dir():
        return "缺少前端依赖，请先执行：cd web && npm install"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="启动「人生导师」开发环境")
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--backend-only", action="store_true", help="只启动后端")
    parser.add_argument("--frontend-only", action="store_true", help="只启动前端")
    parser.add_argument("--reload", action="store_true", help="后端开启热重载")
    args = parser.parse_args()

    problem = _check_prerequisites()
    if problem and not args.backend_only:
        print(f"[错误] {problem}", file=sys.stderr)
        return 1

    children: list[tuple[str, subprocess.Popen]] = []

    backend_port = args.backend_port
    frontend_port = args.frontend_port

    if not args.backend_only:
        backend_port = _pick_port(args.backend_port, "后端")

    if not args.frontend_only:
        frontend_port = _pick_port(args.frontend_port, "前端")

    if not args.frontend_only:
        print(f"[后端] http://127.0.0.1:{backend_port}   (API 文档: /docs)")
        children.append((
            "后端",
            subprocess.Popen(_backend_command(backend_port, args.reload), cwd=ROOT),
        ))

    if not args.backend_only:
        command = _frontend_command(frontend_port)
        if command is None:
            print("[错误] 未找到 npm，请确认 Node.js 已安装", file=sys.stderr)
            return 1
        print(f"[前端] http://localhost:{frontend_port}")

        # 前端要把 /api 代理到后端；无条件注入目标地址，避免"仅当端口非默认才设置"的隐式耦合
        env = {**os.environ, "VITE_API_TARGET": f"http://127.0.0.1:{backend_port}"}
        children.append(("前端", subprocess.Popen(command, cwd=WEB_DIR, env=env)))

    print("\n按 Ctrl+C 停止。\n")
    try:
        for name, process in children:
            process.wait()
            code = process.returncode
            print(f"[{name}] 已退出（code={code}）")
            return code or 0
    except KeyboardInterrupt:
        print("\n正在停止…")
        return 0
    finally:
        for name, process in children:
            if process.poll() is None:
                process.terminate()
                print(f"[{name}] 已停止")


if __name__ == "__main__":
    raise SystemExit(main())
