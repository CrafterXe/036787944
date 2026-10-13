"""逐话题生成 + 拼接。每次只展开一个话题（防停笔），联网补全，末尾汇总参考来源。"""
from pathlib import Path
from . import ollama_client
from . import search
from . import project as proj_mod
from .sanitize import sanitize_math
import config

_SYSTEM = (config.PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_GEN_TPL = (config.PROMPT_DIR / "generate.txt").read_text(encoding="utf-8")


def gen_single_topic(topic, full_text, project=None):
    """生成单个话题的讲解。返回 (正文, 参考url列表)。空则重试 GEN_RETRY 次。"""
    name = topic["name"]
    importance = topic.get("importance", "重要")
    summary = topic.get("summary", "")
    evidence = topic.get("evidence", "")

    # 联网补全
    wr = search.web_search(f"数学 {name}")
    web_block = search.format_web_block(wr)
    urls = [r["url"] for r in wr if r.get("url")]

    prompt = _GEN_TPL.format(
        topic=name, importance=importance, summary=summary,
        evidence=evidence or "(原文未定位到直接证据，请依据完整文本推断)",
        full_text=full_text[:6000], web_block=web_block,
    )
    system = _SYSTEM
    if project:
        system = proj_mod.project_prompt_block(project) + system
    for attempt in range(1, config.GEN_RETRY + 1):
        res = ollama_client.chat(config.GEN_MODEL, [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], timeout=config.GEN_TIMEOUT)
        if res and res.strip():
            # 去掉可能混入的全局标题（# 开头的顶层标题）
            lines = [l for l in res.split("\n") if not l.startswith("# ")]
            return "\n".join(lines).strip(), urls
        print(f"  [gen] 话题「{name}」第{attempt}次返回空，重试...")
    return f"> 该话题「{name}」未生成成功。\n", urls


def build_notes(topics, full_text, project=None):
    """逐话题生成，拼接成完整笔记。返回 (markdown, 全部参考url)。"""
    sections = []
    all_urls = []
    for i, t in enumerate(topics, 1):
        print(f"  [gen] ({i}/{len(topics)}) {t['name']}...")
        body, urls = gen_single_topic(t, full_text, project)
        sections.append(sanitize_math(body))
        all_urls.extend(urls)

    parts = []
    parts.append("\n\n".join(sections))
    # 汇总参考来源（去重）
    seen, uniq = set(), []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    if uniq:
        parts.append("\n\n## 参考来源\n" + "\n".join(f"- {u}" for u in uniq))
    return "\n".join(parts), uniq
