# -*- coding: utf-8 -*-
"""数学笔记整理助手 · 一键安装脚本

自动完成运行环境的准备（跨平台：Windows / macOS / Linux）：
  1. 检查 Python 版本（需 3.10+）
  2. 安装 Python 依赖（pip install -r app/requirements.txt）
  3. 检查 / 安装 Ollama（本地大模型服务）
  4. 下载所需 AI 模型（qwen3:8b 文本、qwen2.5vl:7b 图片 OCR）

用法：
  Windows  ：双击 install.bat   （或在终端执行  python install.py）
  mac/Linux：python3 install.py
"""
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "app" / "requirements.txt"

# 本程序实际用到的模型（须与 app/config.py 一致）
# qwen3:8b     → 文本：清洗 / 提话题 / 生成 / 总结
# qwen2.5vl:7b → 图片 OCR（qwen3-vl:8b 强制思考会耗尽 token 致 OCR 返回空，已弃用）
MODELS = ["qwen3:8b", "qwen2.5vl:7b"]

IS_WIN = os.name == "nt"


def log(msg=""):
    print(msg, flush=True)


def run(cmd, **kw):
    """运行命令，返回 (是否成功, 输出)。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", **kw)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return False, "命令不存在: " + (cmd[0] if isinstance(cmd, list) else str(cmd))
    except Exception as e:
        return False, str(e)


def which(name):
    return shutil.which(name) is not None


# ---------- 1. Python ----------

def check_python():
    v = sys.version_info
    log(f"  当前 Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        log("  [错误] 需要 Python 3.10 或更高版本，请先升级 Python。")
        return False
    log("  [OK] Python 版本满足要求（≥3.10）")
    return True


# ---------- 2. Python 依赖 ----------

def install_pydeps():
    if not REQUIREMENTS.exists():
        log("  [错误] 未找到 app/requirements.txt")
        return False
    log("  正在安装 Python 依赖（gradio / requests / pdfplumber / python-docx）...")
    ok, out = run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS),
                   "--upgrade", "--quiet"])
    if ok:
        log("  [OK] Python 依赖安装完成")
        return True
    log("  [失败] pip 安装出错：")
    log("  " + out.strip()[-500:])
    log("  提示：网络慢时可换国内源，例如：")
    log(f'        {sys.executable} -m pip install -r "{REQUIREMENTS}" -i https://pypi.tuna.tsinghua.edu.cn/simple')
    return False


# ---------- 3. Ollama ----------

def ollama_installed():
    return which("ollama")


def install_ollama():
    """按平台尝试自动安装 Ollama。无法自动装则给出指引。"""
    log("  未检测到 Ollama，尝试自动安装...")
    if IS_WIN:
        if which("winget"):
            log("  使用 winget 安装 Ollama（可能弹出授权窗口，请允许）...")
            ok, out = run(["winget", "install", "-e", "--id", "Ollama.Ollama",
                           "--accept-source-agreements", "--accept-package-agreements"])
            # 安装后当前进程 PATH 未刷新，提示用户重开
            if ok or "Successfully installed" in out or "已安装" in out:
                log("  [OK] Ollama 安装完成")
                log("  [重要] 请【关闭本窗口，重新双击 install.bat 或 启动.bat】让 PATH 生效。")
                return "restart"
        log("  [提示] 未找到 winget，无法自动安装。")
    else:
        log("  使用官方脚本安装 Ollama（curl | sh）...")
        if which("curl"):
            ok, out = run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
            if ok:
                log("  [OK] Ollama 安装完成")
                return True
        log("  [提示] 自动安装失败。")

    log("  请手动安装 Ollama：")
    log("    Windows  ：https://ollama.com/download/windows  下载 OllamaSetup.exe 安装")
    log("    mac      ：https://ollama.com/download/mac  或  brew install ollama")
    log("    Linux    ：curl -fsSL https://ollama.com/install.sh | sh")
    return False


def ensure_ollama():
    if ollama_installed():
        ok, out = run(["ollama", "--version"])
        log(f"  [OK] 已安装 Ollama（{out.strip().splitlines()[0] if out.strip() else '版本未知'}）")
        return True
    return install_ollama()


# ---------- 4. 模型 ----------

def ensure_ollama_running():
    """确保 Ollama 服务在线（pull 前需要）。返回是否就绪。"""
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        pass
    log("  正在启动 Ollama 服务以下载模型...")
    try:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=(subprocess.CREATE_NO_WINDOW if IS_WIN else 0))
    except Exception:
        return False
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
            return True
        except Exception:
            import time
            time.sleep(1)
    return False


def install_models():
    if not ensure_ollama_running():
        log("  [失败] Ollama 服务未能启动，无法下载模型。")
        log("         请手动运行  ollama serve  后，再执行各模型的 ollama pull。")
        return False
    all_ok = True
    for m in MODELS:
        # 已存在则跳过
        ok, out = run(["ollama", "list"])
        if ok and m in out:
            log(f"  [跳过] 模型已存在：{m}")
            continue
        log(f"  正在下载模型 {m}（体积较大，视网速需几分钟到更久）...")
        # pull 用实时输出，让用户看到进度
        try:
            code = subprocess.call(["ollama", "pull", m])
            if code == 0:
                log(f"  [OK] 模型就绪：{m}")
            else:
                log(f"  [失败] 下载失败：{m}（可稍后手动执行  ollama pull {m}）")
                all_ok = False
        except Exception as e:
            log(f"  [失败] 下载出错：{m}：{e}")
            all_ok = False

    # 收尾校验：确认所需模型都已出现在 ollama list 中
    ok, out = run(["ollama", "list"])
    if ok:
        missing = [m for m in MODELS if m not in out]
        for m in missing:
            log(f"  [校验] 未检测到模型：{m}")
        if missing:
            all_ok = False
    return all_ok


# ---------- main ----------

def main():
    log("=" * 60)
    log("   数学笔记整理助手 · 一键安装")
    log("=" * 60)
    log("说明：需要联网下载依赖和 AI 模型（模型共约 10GB），")
    log("      安装过程视网速可能需要几分钟到更久，请耐心等待。")
    log()

    log("[1/4] 检查 Python ...")
    if not check_python():
        return 1
    log()

    log("[2/4] 安装 Python 依赖 ...")
    if not install_pydeps():
        return 1
    log()

    log("[3/4] 检查 / 安装 Ollama ...")
    r = ensure_ollama()
    if r == "restart":
        log()
        log("=" * 60)
        log("  Ollama 刚装好，请【重新运行本安装或启动脚本】继续。")
        log("=" * 60)
        return 0
    if not r:
        log("  Ollama 未就绪，模型下载步骤跳过。装好 Ollama 后请重新运行本脚本。")
        return 1
    log()

    log("[4/4] 下载 AI 模型 ...")
    models_ok = install_models()
    log()

    log("=" * 60)
    if models_ok:
        log("   安装完成！🎉")
        log("=" * 60)
        log("  现在可以启动助手：")
        if IS_WIN:
            log("    双击「启动.bat」")
        else:
            log("    python3 launcher.py")
        log("  启动后浏览器会自动打开操作面板（http://127.0.0.1:14000/）")
    else:
        log("   安装基本完成，但部分模型下载失败。")
        log("=" * 60)
        log("  可稍后手动补齐缺失模型，例如：  ollama pull qwen3:8b")
        log("  然后运行启动脚本即可。")
    log()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已取消安装。")
        sys.exit(130)
