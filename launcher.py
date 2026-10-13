# -*- coding: utf-8 -*-
"""数学笔记整理助手 · 启动器（源码版）

使用系统环境运行（需先执行一次 install 完成安装）：
  Windows  ：双击 启动.bat
  mac/Linux：python3 launcher.py

流程：
  1. 检查 Python 依赖与 Ollama 是否就绪（未装则提示先运行 install）
  2. 启动 Ollama 服务（若未在运行）
  3. 启动 Gradio 操作面板（app/panel.py）
  4. 面板就绪后自动打开浏览器
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"

OLLAMA_HOST = "http://127.0.0.1:11434"
PANEL_PORT = 14000
PANEL_URL = f"http://127.0.0.1:{PANEL_PORT}/"
IS_WIN = os.name == "nt"


def log(msg=""):
    print(msg, flush=True)


def _port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _ollama_ready():
    try:
        urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _wait(pred, seconds, interval=1.0):
    for _ in range(max(1, int(seconds / interval))):
        if pred():
            return True
        time.sleep(interval)
    return False


def check_ready():
    """检查运行环境：依赖与 Ollama。返回是否就绪。"""
    ok = True

    if not (APP_DIR / "panel.py").exists():
        log("  [错误] 未找到 app/panel.py，目录结构不完整。")
        return False

    # Python 依赖
    try:
        import gradio, requests, pdfplumber, docx  # noqa
        log("  [OK] Python 依赖已安装")
    except ImportError as e:
        log(f"  [缺失] Python 依赖未装全：{e}")
        ok = False

    # Ollama
    if shutil.which("ollama"):
        log("  [OK] 已安装 Ollama")
    else:
        log("  [缺失] 未安装 Ollama")
        ok = False

    if not ok:
        log()
        log("  运行环境未准备好，请先执行安装：")
        if IS_WIN:
            log("    双击「install.bat」")
        else:
            log("    python3 install.py")
    return ok


def start_ollama():
    if _ollama_ready():
        log("  [跳过] Ollama 服务已在运行")
        return True
    env = os.environ.copy()
    env.setdefault("OLLAMA_KEEP_ALIVE", "-1")
    log("  正在启动 Ollama 服务...")
    try:
        subprocess.Popen(["ollama", "serve"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=(subprocess.CREATE_NO_WINDOW if IS_WIN else 0))
    except Exception as e:
        log(f"  [错误] 启动 Ollama 失败：{e}")
        return False
    if _wait(_ollama_ready, 60):
        log("  [完成] Ollama 就绪")
        return True
    log("  [失败] Ollama 60 秒内未就绪")
    return False


def start_panel():
    if _port_open(PANEL_PORT):
        log("  [跳过] 操作面板已在运行，直接打开浏览器")
        webbrowser.open(PANEL_URL)
        return True
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    log("  正在启动操作面板...")
    try:
        subprocess.Popen([sys.executable, str(APP_DIR / "panel.py")],
                         cwd=str(APP_DIR), env=env,
                         creationflags=(subprocess.CREATE_NEW_CONSOLE if IS_WIN else 0))
    except Exception as e:
        log(f"  [错误] 启动面板失败：{e}")
        return False
    if _wait(lambda: _port_open(PANEL_PORT), 60):
        log("  [完成] 面板就绪，即将打开浏览器")
        return True
    log("  [失败] 面板 60 秒内未就绪，请查看“面板”窗口中的错误信息")
    return False


def main():
    log("=" * 56)
    log("   数学笔记整理助手 · 启动")
    log("=" * 56)
    log()

    log("[1/3] 检查运行环境 ...")
    if not check_ready():
        return 1
    log()

    log("[2/3] 本地 AI 模型服务（Ollama）...")
    if not start_ollama():
        return 1
    log()

    log("[3/3] 操作面板 ...")
    if not start_panel():
        return 1
    log()

    log("=" * 56)
    log("   启动完成！")
    log("=" * 56)
    log(f"  面板地址：{PANEL_URL}")
    log("  面板在单独窗口运行，可最小化；本窗口可关闭。")
    log("  停止：关闭“面板”窗口即可（Ollama 服务常驻后台）。")
    log()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
