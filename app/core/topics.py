"""话题提取：逐块提话题 → 跨块合并去重 → 带证据引用。"""
import json
import re
from pathlib import Path
from . import ollama_client
from . import project as proj_mod
import config

_SYSTEM = (config.PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_TOPICS = (config.PROMPT_DIR / "topics.txt").read_text(encoding="utf-8")


def _extract_one(chunk, project=None):
    """单块提话题，返回 list[{name,summary,importance}]。失败返回 []。"""
    system = _SYSTEM + "\n\n" + _TOPICS
    if project:
        system = proj_mod.project_prompt_block(project) + system
    res = ollama_client.chat(config.TOPIC_MODEL, [
        {"role": "system", "content": system},
        {"role": "user", "content": chunk},
    ])
    if not res:
        return []
    # 去掉 ``` 包裹
    s = res.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n", "", s)
        s = re.sub(r"\n```$", "", s).strip()
    data = None
    try:
        data = json.loads(s)
    except Exception:
        # 提取第一个 { 或 [  到最后一个 } 或 ]
        m = re.search(r"[\{\[].*[\}\]]", s, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                pass
    if data is None:
        print("  [topics] JSON 解析失败，本块话题跳过")
        return []
    raw = data.get("topics", data) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    # 兼容字段：summary/description；importance 中英文
    out = []
    imp_map = {"core": "核心", "important": "重要", "know": "了解", "understanding": "了解"}
    for t in raw:
        if not isinstance(t, dict):
            continue
        name = (t.get("name") or "").strip()
        if not name:
            continue
        imp = str(t.get("importance", "重要")).strip()
        imp = imp_map.get(imp.lower(), imp if imp in ("核心", "重要", "了解") else "重要")
        out.append({
            "name": name,
            "summary": t.get("summary") or t.get("description") or "",
            "importance": imp,
        })
    return out


def merge_topics(topic_lists):
    """跨块去重合并。简单策略：按 name 规范化后合并，重名取最长 summary。"""
    merged = {}
    for lst in topic_lists:
        for t in lst:
            name = (t.get("name") or "").strip()
            if not name:
                continue
            key = name.replace(" ", "")
            if key in merged:
                if len(t.get("summary", "")) > len(merged[key].get("summary", "")):
                    merged[key] = t
            else:
                merged[key] = t
    return list(merged.values())


def evidence_quote(topic_name, full_text, max_len=400):
    """在原文中定位话题证据句。找不到返回空串（不报错）。"""
    name = topic_name.replace(" ", "")
    # 取话题名的前几个字作为关键词搜索
    kw = topic_name[:4] if len(topic_name) >= 4 else topic_name
    idx = full_text.find(kw)
    if idx == -1:
        return ""
    start = max(0, idx - 100)
    snippet = full_text[start:start + max_len]
    return snippet.replace("\n", " ")


def propose_topics(chunks, full_text, project=None):
    """逐块提话题 → 合并 → 附加证据。返回 topics 列表。"""
    all_lists = []
    for i, c in enumerate(chunks, 1):
        print(f"  [topics] 块 {i}/{len(chunks)}...")
        all_lists.append(_extract_one(c, project))
    topics = merge_topics(all_lists)
    for t in topics:
        t["evidence"] = evidence_quote(t["name"], full_text)
    print(f"  [topics] 共提取 {len(topics)} 个话题")
    return topics
