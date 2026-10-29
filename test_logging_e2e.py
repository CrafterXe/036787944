# -*- coding: utf-8 -*-
"""端到端日志验证脚本：python test_logging_e2e.py（项目根目录运行）

验证「启动面板 → 执行任务 → 日志必定生成」整条链路，分两阶段：
  A. 进程内：与 panel.py 完全相同的初始化路径（import panel → configure_logging），
     调用真实 do_judge / do_run 回调，断言 app/logs/app.log 增长且带 [run_id]。
  B. 真面板：另起 python app/panel.py 子进程，走 HTTP API 调一次「判断」，
     断言 app.log 新增 judge 日志行（这才是 launcher 实际跑的路径）。

前置自检：14000 端口被旧面板占用时，launcher 会跳过新面板导致新配置不生效，
脚本会明确报出该情况。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
PANEL_PORT = 14000
sys.path.insert(0, str(APP))

results = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    results.append(ok)


def port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_port(port, seconds):
    for _ in range(seconds):
        if port_open(port):
            return True
        time.sleep(1)
    return False


# ---------- 预检 ----------
if os.environ.get("APP_LOG_DIR"):
    print(f"[提示] 检测到 APP_LOG_DIR={os.environ['APP_LOG_DIR']}，测试中将临时清除以验证默认路径")
if port_open(PANEL_PORT):
    print("[警告] 14000 端口已被占用：存在旧面板进程，launcher 会跳过新面板，"
          "新日志配置不生效。请关闭旧面板窗口后重跑本脚本。")

os.environ.pop("APP_LOG_DIR", None)

# ---------- 阶段 A：进程内（同 panel.py 初始化路径） ----------
import logging

import config   # noqa: E402  （import panel 前须先定 APP_LOG_DIR）
import panel    # noqa: E402  模块级触发 configure_logging()
from core import logsetup  # noqa: E402

log_file = Path(config.LOG_DIR) / "app.log"
llm_file = Path(config.LOG_DIR) / "llm.log"
print(f"[阶段A] 日志目录：{config.LOG_DIR}")

size0 = log_file.stat().st_size if log_file.exists() else 0
rid = logsetup.get_run_id() if logsetup.get_run_id() != "-" else "e2e" + os.urandom(4).hex()
logsetup.set_run_id(rid)
logsetup.set_stage("e2e")
logging.getLogger("app.flow").info("e2e flow line")
logging.getLogger("app.llm").debug("e2e llm line")
logging.getLogger("app.guard").info("e2e guard line",
                                    extra={"func": "e2e", "action": "verify", "reason": "logging"})

r1 = panel.do_judge("", None)                      # 真实回调（早退分支，不触 LLM）
r2 = panel.do_run("", None, "[]", "", "", r1[3])   # 复用 judge 的 rid

time.sleep(0.5)
text = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
check("A1 日志目录被创建且 app.log 存在", log_file.exists(), str(log_file))
check("A2 app.log 写入增长", len(text) > size0)
check("A3 app.log 含本次 run_id 行", f"[{rid}]" in text and "stage=judge" in text)
check("A4 llm.log 存在且含 e2e 行", llm_file.exists() and "e2e llm line" in llm_file.read_text(encoding="utf-8"))
check("A5 do_judge/do_run 返回 4 值且 rid 串联", len(r1) == 4 and len(r2) == 4 and r1[3] == r2[3])

# ---------- 阶段 B：真实面板进程 + HTTP 调用 ----------
print("[阶段B] 启动真实面板子进程（python app/panel.py）...")
env = os.environ.copy()  # 已无 APP_LOG_DIR
proc = subprocess.Popen([sys.executable, str(APP / "panel.py")],
                        cwd=str(APP), env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
panel_out = b""
try:
    if not wait_port(PANEL_PORT, 60):
        check("B1 面板 60 秒内就绪", False)
    else:
        check("B1 面板 60 秒内就绪", True)

        # 探测 API base（Gradio 5+ 在 /gradio_api/ 前缀下，旧版在根路径）
        base, info = None, {}
        for cand in ("/gradio_api", ""):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PANEL_PORT}{cand}/info", timeout=10) as r:
                    info = json.loads(r.read().decode("utf-8"))
                base = cand
                break
            except Exception:
                continue
        check("B2 探测到 API base 并取到 /info", base is not None, f"base='{base}'")

        # 从 /info 动态找 judge 端点（兼容不同 Gradio 版本的 api_name）
        endpoints = list((info.get("named_endpoints") or {}).keys())
        api = next((e for e in endpoints if "judge" in e.lower()), None)
        check("B3 找到 judge API 端点", api is not None, f"{api} (全部: {endpoints})")

        if api:
            size1 = log_file.stat().st_size if log_file.exists() else 0
            body = json.dumps({"data": ["", None]}).encode("utf-8")  # folder="" → 早退分支，不触 LLM
            req = urllib.request.Request(f"http://127.0.0.1:{PANEL_PORT}{base}/call{api}",
                                         data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                event_id = json.loads(r.read().decode("utf-8"))["event_id"]
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PANEL_PORT}{base}/call{api}/{event_id}", timeout=30) as r:
                sse = r.read().decode("utf-8", "replace")
            ok_b4 = "event: complete" in sse
            check("B4 HTTP 调用「判断」成功返回（event: complete）", ok_b4,
                  "" if ok_b4 else f"响应片段: {sse[:300]!r}")

            time.sleep(1.0)
            text2 = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
            check("B5 面板进程写入 app.log（新增 judge 行）",
                  len(text2) > size1 and "run started: stage=judge" in text2[size1:])
finally:
    proc.terminate()
    try:
        panel_out = proc.communicate(timeout=10)[0] or b""
    except Exception:
        proc.kill()
        panel_out = proc.communicate()[0] or b""
    time.sleep(1)
    if not all(results[-5:]):  # B 阶段有失败项时打印面板输出帮助定位
        print("---- 面板子进程输出（尾部）----")
        print(panel_out.decode("utf-8", "replace")[-2000:])

print()
print("==== 端到端日志验证：" + ("全部通过" if all(results) else "存在失败项") + " ====")
sys.exit(0 if all(results) else 1)
