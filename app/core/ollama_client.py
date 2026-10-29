"""统一调用本地 Ollama。失败返回 None，不抛异常，由上层兜底。"""
import json
import base64
import logging
import time
import urllib.request
import urllib.error
from pathlib import Path

import config

_llm = logging.getLogger("app.llm")


def _post(path, payload, timeout):
    url = config.OLLAMA_HOST + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(model, messages, timeout=None, think=None, fmt=None, options=None):
    """messages: [{"role":"system"/"user"/"assistant","content":...}]。返回文本或 None。
    think=False 关闭 qwen3 系列的思考（避免思考耗尽 token）；fmt="json" 强制 JSON 输出；
    options 传 num_ctx / num_predict 等。"""
    timeout = timeout or config.CHAT_TIMEOUT
    t0 = time.perf_counter()
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    payload = {"model": model, "messages": messages, "stream": False}
    if think is not None:
        payload["think"] = think
    if fmt:
        payload["format"] = fmt
    if options:
        payload["options"] = options
    try:
        resp = _post("/api/chat", payload, timeout)
        text = resp.get("message", {}).get("content")
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=%d status=%s",
                   model, time.perf_counter() - t0, prompt_chars,
                   len(text) if text else 0, "ok" if text else "empty")
        return text
    except Exception:
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=0 status=error",
                   model, time.perf_counter() - t0, prompt_chars)
        _llm.exception("ollama chat failed: model=%s", model)
        return None


def chat_with_images(model, prompt, image_paths, timeout=None, options=None):
    """带图片的对话（用于 OCR）。image_paths: 本地图片路径列表（可只有1张）。返回文本或 None。"""
    timeout = timeout or config.OCR_TIMEOUT
    t0 = time.perf_counter()
    images = []
    for p in image_paths:
        try:
            images.append(base64.b64encode(Path(p).read_bytes()).decode())
        except Exception:
            _llm.exception("read image failed: path=%s", p)
    if not images:
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=0 image_count=0 status=empty",
                   model, time.perf_counter() - t0, len(prompt))
        return None
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": images}],
        "stream": False,
        "think": False,   # qwen3 系列思考会耗尽 token，OCR 必须关
    }
    if options:
        payload["options"] = options
    try:
        resp = _post("/api/chat", payload, timeout)
        text = resp.get("message", {}).get("content")
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=%d image_count=%d status=%s",
                   model, time.perf_counter() - t0, len(prompt),
                   len(text) if text else 0, len(images), "ok" if text else "empty")
        return text
    except Exception:
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=0 image_count=%d status=error",
                   model, time.perf_counter() - t0, len(prompt), len(images))
        _llm.exception("ollama vl failed: model=%s", model)
        return None


def generate(model, prompt, system=None, timeout=None):
    """单次生成。返回文本或 None。"""
    timeout = timeout or config.CHAT_TIMEOUT
    t0 = time.perf_counter()
    payload = {"model": model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    try:
        resp = _post("/api/generate", payload, timeout)
        text = resp.get("response")
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=%d status=%s",
                   model, time.perf_counter() - t0, len(prompt),
                   len(text) if text else 0, "ok" if text else "empty")
        return text
    except Exception:
        _llm.debug("model=%s elapsed=%.1fs prompt_chars=%d resp_chars=0 status=error",
                   model, time.perf_counter() - t0, len(prompt))
        _llm.exception("ollama generate failed: model=%s", model)
        return None
