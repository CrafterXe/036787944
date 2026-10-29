"""清洗口语化转写文本。带长度护栏：骤降<60% 回退原文，防止被总结掉。"""
import logging
from pathlib import Path
from . import ollama_client
import config

_log = logging.getLogger("app.core.clean")

_SYSTEM = (config.PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_CLEAN = (config.PROMPT_DIR / "clean.txt").read_text(encoding="utf-8")


def clean_chunk(text):
    """清洗单块。返回清洗后文本（失败/被总结则返回原文）。"""
    orig_len = len(text)
    res = ollama_client.chat(config.CLEAN_MODEL, [
        {"role": "system", "content": _SYSTEM + "\n\n" + _CLEAN},
        {"role": "user", "content": text},
    ])
    if not res:
        return text
    # 长度护栏：清洗后低于原文 60%，判定被总结，回退原文
    if len(res) < orig_len * config.CLEAN_MIN_RATIO:
        _log.info("清洗后 %d < %d，回退原文", len(res), int(orig_len * config.CLEAN_MIN_RATIO))
        return text
    return res


def clean_text(chunks):
    """对每块清洗，返回清洗后块列表。"""
    out = []
    for i, c in enumerate(chunks, 1):
        _log.info("块 %d/%d (%d 字)...", i, len(chunks), len(c))
        out.append(clean_chunk(c))
    return out
