"""话题提取：逐块提章节级主题 → 名称合并 → LLM 语义归一 → 带证据引用。"""
import json
import re
from difflib import SequenceMatcher

from . import ollama_client
from . import project as proj_mod
import config

_SYSTEM = (config.PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_TOPICS = (config.PROMPT_DIR / "topics.txt").read_text(encoding="utf-8")
_MERGE = (config.PROMPT_DIR / "merge_topics.txt").read_text(encoding="utf-8")


def _loads_json(s):
    """尽量从模型输出里解析出 JSON。失败返回 None。"""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n", "", s)
        s = re.sub(r"\n```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"[\{\[].*[\}\]]", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _extract_one(chunk, project=None):
    """单块提话题，返回 list[{name,summary,importance,type}]。失败返回 []。"""
    system = _SYSTEM + "\n\n" + _TOPICS
    if project:
        system = proj_mod.project_prompt_block(project) + system
    user = chunk + "\n\n（请只输出 JSON，不要输出任何解释或数学解答。）"
    opts = {"num_ctx": 8192, "num_predict": 2048}
    for attempt in (1, 2):
        res = ollama_client.chat(config.TOPIC_MODEL, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], think=False, fmt="json", options=opts)
        if not res:
            continue
        data = _loads_json(res)
        if data is None:
            print(f"  [topics] JSON 解析失败（第{attempt}次），本块响应: {res[:120]!r}")
            continue
        raw = data.get("topics", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            continue
        out = []
        imp_map = {"core": "核心", "important": "重要", "know": "了解", "understanding": "了解"}
        type_map = {"knowledge": "knowledge", "exercise": "exercise", "知识": "knowledge",
                    "习题": "exercise", "例题": "exercise"}
        for t in raw:
            if not isinstance(t, dict):
                continue
            name = _clean_name((t.get("name") or "").strip())
            if not name or _NON_KNOWLEDGE.search(name):
                continue
            imp = str(t.get("importance", "重要")).strip()
            imp = imp_map.get(imp.lower(), imp if imp in ("核心", "重要", "了解") else "重要")
            tp = str(t.get("type", "knowledge")).strip()
            tp = type_map.get(tp.lower(), "knowledge")
            out.append({
                "name": name,
                "summary": t.get("summary") or t.get("description") or "",
                "importance": imp,
                "type": tp,
            })
        return out
    return []


def _norm_name(s):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s or "")


def _clean_name(s):
    """去掉模型自带的节号前缀（§2.1 / 第2章 / 第3讲），避免与系统 §N 编号重复。"""
    s = re.sub(r"^\s*§\s*[0-9]+(?:\.[0-9]+)*\s*", "", s or "")
    s = re.sub(r"^\s*第\s*[0-9一二三四五六七八九十]+\s*[章节讲]\s*", "", s)
    return s.strip()


def _similar(a, b):
    """名称相似判定：完全相同、互相包含、或字符序列相似度高。"""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    # 二元组重合率（避免引入 difflib 的长比较开销）
    ga = {a[i:i + 2] for i in range(max(len(a) - 1, 1))}
    gb = {b[i:i + 2] for i in range(max(len(b) - 1, 1))}
    if not ga or not gb:
        return False
    return len(ga & gb) / min(len(ga), len(gb)) >= 0.6


_IMP_ORDER = {"核心": 3, "重要": 2, "了解": 1}

# 课堂闲聊/学习建议不是数学知识（实测模型会把它当成一章"大学学习方法与做题策略"）
_NON_KNOWLEDGE = re.compile(
    r"学习方法|学习策略|做题策略|如何学习|学习建议|时间管理|绩点|考试安排|课程安排|"
    r"作业要求|课堂管理|闲聊|复习计划|复习方法|期末|考研")


def merge_topics(topic_lists):
    """跨块合并：先按名称全等合并，再做相似度合并（只做确定性合并，语义归一交给 normalize_topics）。"""
    flat = []
    for lst in topic_lists:
        flat.extend(lst)

    # 第一轮：名称全等
    merged = {}
    for t in flat:
        key = _norm_name(t.get("name", ""))
        if not key or _NON_KNOWLEDGE.search(t.get("name", "")):
            continue
        if key in merged:
            if len(t.get("summary", "")) > len(merged[key].get("summary", "")):
                merged[key] = t
        else:
            merged[key] = t
    uniq = list(merged.values())

    # 第二轮：相似度合并（保留名字更短、summary 更长的那个）
    out = []
    for t in uniq:
        hit = None
        for o in out:
            if _similar(_norm_name(t["name"]), _norm_name(o["name"])):
                hit = o
                break
        if hit is None:
            out.append(dict(t))
        else:
            if len(t.get("summary", "")) > len(hit.get("summary", "")):
                hit["summary"] = t["summary"]
            if _IMP_ORDER.get(t.get("importance", "重要"), 2) > _IMP_ORDER.get(hit.get("importance", "重要"), 2):
                hit["importance"] = t["importance"]
    return out


def normalize_topics(topics, project=None):
    """第二阶段：用一次 LLM 调用把碎片话题归并为章节级主题。
    返回 (归一后的话题列表, 归一前数量)。失败时返回 (入参, 入参数量)。"""
    n = len(topics)
    if not config.ENABLE_TOPIC_MERGE or n < config.TOPIC_MERGE_MIN:
        return topics, n

    brief = [{"name": t["name"], "summary": t.get("summary", ""),
              "importance": t.get("importance", "重要")} for t in topics]
    # 模板里有 JSON 花括号，不能用 str.format，改用定点替换
    prompt = (_MERGE
              .replace("{n}", str(n))
              .replace("{lo}", str(config.TOPIC_MIN))
              .replace("{hi}", str(config.TOPIC_MAX))
              .replace("{topics_json}", json.dumps(brief, ensure_ascii=False, indent=1)))
    system = _SYSTEM + "\n\n你是讲义的结构编辑，只输出 JSON。"
    if project:
        system = proj_mod.project_prompt_block(project) + system
    print(f"  [topics] 语义归并：{n} 个碎片话题 → 章节级主题...")
    res = ollama_client.chat(config.TOPIC_MERGE_MODEL, [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ], think=False, fmt="json", timeout=config.CHAT_TIMEOUT,
        options={"num_ctx": 8192, "num_predict": 2048})
    data = _loads_json(res) if res else None
    chapters = (data or {}).get("chapters") if isinstance(data, dict) else None
    if not isinstance(chapters, list) or not chapters:
        print("  [topics] 语义归并失败，保留原话题列表。")
        return topics, n

    # 建立 原话题名 → 话题 dict 的索引
    by_name = {}
    for t in topics:
        by_name[_norm_name(t["name"])] = t

    used = set()
    merged = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        cname = _clean_name((ch.get("name") or "").strip())
        members = ch.get("members") or []
        if not cname or _NON_KNOWLEDGE.search(cname) or not isinstance(members, list):
            continue
        picked = []
        for m in members:
            key = _norm_name(str(m))
            t = by_name.get(key)
            if t is None:
                # 成员名与原名不完全一致时做一次相似匹配
                for k, cand in by_name.items():
                    if k not in used and _similar(key, k):
                        t = cand
                        key = k
                        break
            if t is not None and key not in used:
                used.add(key)
                picked.append(t)
        if not picked:
            continue
        imp = ch.get("importance", "")
        if imp not in ("核心", "重要", "了解"):
            imp = max((t.get("importance", "重要") for t in picked),
                      key=lambda x: _IMP_ORDER.get(x, 2))
        tp = "exercise" if all(t.get("type") == "exercise" for t in picked) else "knowledge"
        merged.append({
            "name": cname,
            "summary": (ch.get("summary") or "").strip() or max((t.get("summary", "") for t in picked), key=len),
            "importance": imp,
            "type": tp,
            "members": [t["name"] for t in picked],
        })

    # 未能映射的原话题：保留为独立章节，避免内容丢失
    leftover = [t for k, t in by_name.items()
                if k not in used and not _NON_KNOWLEDGE.search(t.get("name", ""))]
    for t in leftover:
        merged.append({**t, "members": [t["name"]]})
    if leftover:
        print(f"  [topics] 有 {len(leftover)} 个话题未被归并，保留为独立章节。")

    print(f"  [topics] 归并结果：{n} → {len(merged)} 个章节")
    return merged, n


def keywords_of(topic, lo=3, hi=4):
    """话题名 → 检索关键词：整名 + 连接词切分 + 3–4 字滑窗（"行列式的展开符号规则"
    这类复合名整串在原文里查不到，靠滑窗才能命中"行列式""符号""展开"）。长词优先。"""
    names = topic.get("members") or [topic.get("name", "")]
    kws = []
    for nm in names:
        nm = re.sub(r"\s+", "", nm or "")
        if len(nm) >= 2:
            kws.append(nm)
        for part in re.split(r"[与和的及、/·]", nm):
            part = part.strip()
            if len(part) >= 2:
                kws.append(part)
        s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", nm)
        seen = set()
        for n in range(hi, lo - 1, -1):
            for i in range(max(len(s) - n + 1, 0)):
                g = s[i:i + n]
                if g not in seen:
                    seen.add(g)
                    kws.append(g)
    uniq = list(dict.fromkeys(kws))
    uniq.sort(key=len, reverse=True)
    return uniq


def evidence_quote(topic, full_text, max_len=1500):
    """按话题名（含滑窗关键词）在原文中定位证据段落，拼成一段引用。找不到返回空串。
    排序按"关键词稀有度"：原文里少见的长词（如"符号规则"）比高频通用词（如"行列式的"）
    更能代表这一话题，优先取它们的窗口，避免所有话题都截到全文开头。"""
    kws = keywords_of(topic)
    freq = {kw: full_text.count(kw) for kw in kws}
    ranges = []      # (出现次数, -词长, 起, 止)
    for kw in kws:
        start = 0
        while True:
            idx = full_text.find(kw, start)
            if idx == -1:
                break
            a, b = max(0, idx - 200), min(len(full_text), idx + 400)
            if not any(a < r[3] and b > r[2] for r in ranges):
                ranges.append((freq[kw], -len(kw), a, b))
            start = idx + len(kw)
            if len(ranges) > 40:
                break
        if len(ranges) > 40:
            break
    if not ranges:
        return ""
    ranges.sort(key=lambda r: (r[0], r[1], r[2]))
    parts = []
    for _, _, a, b in ranges[:12]:
        parts.append(full_text[a:b].replace("\n", " ").strip())
        if sum(len(p) for p in parts) >= max_len:
            break
    return "\n".join(parts)[:max_len]


def coalesce_by_evidence(topics):
    """证据高度重合的话题 = 同一段原文换了个说法 → 合并为一章（治"同一内容拆成 5 章"）。"""
    out, merged = [], 0
    for t in topics:
        ev = t.get("evidence", "")
        hit = None
        for o in out:
            oe = o.get("evidence", "")
            if len(ev) >= 200 and len(oe) >= 200 \
                    and SequenceMatcher(None, oe[:1500], ev[:1500]).ratio() >= 0.65:
                hit = o
                break
        if hit is None:
            out.append(dict(t))
            continue
        merged += 1
        hit["members"] = list(dict.fromkeys(
            (hit.get("members") or [hit["name"]]) + (t.get("members") or [t["name"]])))
        if len(t.get("summary", "")) > len(hit.get("summary", "")):
            hit["summary"] = t["summary"]
        if _IMP_ORDER.get(t.get("importance", "重要"), 2) > _IMP_ORDER.get(hit.get("importance", "重要"), 2):
            hit["importance"] = t["importance"]
        if len(ev) > len(hit.get("evidence", "")):
            hit["evidence"] = ev
    if merged:
        print(f"  [topics] 证据重合，合并 {merged} 个同源话题")
    return out


def _split_back_to_min(topics, full_text):
    """P2 回补下限：合并后章节数 < TOPIC_SPLIT_MIN 时，沿 members 边界拆最大的章。
    拆分判据：两组 members 名称之间无任何子串对才拆（不用证据相似度，否则永远不拆）；
    所有章都不可拆时接受现状，不硬凑。"""
    topics = list(topics)
    blocked = set()
    while len(topics) < config.TOPIC_SPLIT_MIN:
        cands = [(i, t) for i, t in enumerate(topics)
                 if i not in blocked and len(t.get("members") or []) >= 2]
        if not cands:
            break
        i, t = max(cands, key=lambda x: len(x[1]["members"]))
        mem = t["members"]
        g1, g2 = mem[:len(mem) // 2], mem[len(mem) // 2:]
        if any(a in b or b in a for a in g1 for b in g2):
            blocked.add(i)          # 名称纠缠，拆不干净，试下一章
            continue
        def _mk(ms):
            return {"name": max(ms, key=len),
                    "summary": t.get("summary", ""),
                    "importance": t.get("importance", "重要"),
                    "type": t.get("type", "knowledge"),
                    "members": list(ms)}
        t1, t2 = _mk(g1), _mk(g2)
        t1["evidence"] = evidence_quote(t1, full_text)
        t2["evidence"] = evidence_quote(t2, full_text)
        topics[i:i + 1] = [t1, t2]
        print(f"  [topics] 章节数低于下限 {config.TOPIC_SPLIT_MIN}，"
              f"拆分「{t['name']}」→「{t1['name']}」+「{t2['name']}」")
    return topics


def propose_topics(chunks, full_text, project=None):
    """逐块提话题 → 名称合并 → 语义归一 → 附加证据 → 证据重合合并 → 回补下限。返回话题列表。"""
    all_lists = []
    for i, c in enumerate(chunks, 1):
        print(f"  [topics] 块 {i}/{len(chunks)}...")
        all_lists.append(_extract_one(c, project))
    topics = merge_topics(all_lists)
    print(f"  [topics] 初步提取 {len(topics)} 个话题（已按名称合并）")
    topics, before = normalize_topics(topics, project)
    for t in topics:
        t["evidence"] = evidence_quote(t, full_text)
    topics = coalesce_by_evidence(topics)
    topics = _split_back_to_min(topics, full_text)
    print(f"  [topics] 共 {len(topics)} 个章节（归并前 {before} 个）")
    return topics
