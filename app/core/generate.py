"""逐章节生成 + 排版拼接。每次只展开一个章节（防停笔），联网补全，末尾汇总参考来源。"""
import re
from datetime import datetime

from . import ollama_client
from . import search
from . import numbering
from . import project as proj_mod
from . import vault as vault_mod
from .sanitize import sanitize_math
from .topics import keywords_of
import config

_SYSTEM = (config.PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_GEN_TPL = (config.PROMPT_DIR / "generate.txt").read_text(encoding="utf-8")
_EXERCISE_TPL = (config.PROMPT_DIR / "exercise.txt").read_text(encoding="utf-8")

_TONE_TEXT = {"mixed": "命题式陈述与叙述式讲解并用",
              "narrative": "以叙述式讲解为主",
              "declarative": "以短促命题式为主"}
_FORMULA_TEXT = {"inline": "随文书写", "centered": "单独成行并编号"}

# 实测模型反复出现的模板化句子（提示词已禁，仍会漏出，这里做兜底删除）
_BAN_SENT = (
    r"是为了解决",
    r"提供了直观的思路",
    r"奠定了[^。，]{0,4}基础",
    r"保证[^。，]{0,10}一致性",
    r"本质上是将",
    r"核心工具",
    r"为后续[^。，]{0,12}(提供|奠定)",
)


def _strip_boilerplate(body):
    """删除模板化套话句；整条注若只剩标题（说明全是废话）则整条移除。"""
    blocks, removed = [], 0
    for b in body.split("\n\n"):
        pieces = re.split(r"(?<=[。！？])", b)
        keep = []
        for s in pieces:
            if s.strip() and any(re.search(p, s) for p in _BAN_SENT):
                removed += 1
            else:
                keep.append(s)
        newb = "".join(keep).rstrip()
        is_note = bool(re.match(r"^#{2,4}\s*注", b))
        if is_note and len(re.sub(r"[\W_]+", "", newb)) < 25:
            continue                      # 整条注都是套话 → 删掉
        if not newb.strip() and b.strip():
            newb = b                      # 非注内容全被判为套话时保守保留
        blocks.append(newb)
    if removed:
        print(f"  [gen] 删除 {removed} 句模板化套话")
    return "\n\n".join(blocks)


def _example_rule(text):
    """例题规则：材料里没出现例题，就明令禁止写例题小节（模型爱自编）。"""
    if re.search(r"例题|例子|例\s*[0-9一二三四五六七八九十]", text):
        return ("本节材料中出现了例题：只收录其中**真实出现**的例题，标题标出处"
                "（如 `### 例 1（课件例 2）`）；严禁自编题、改数据、追加课后练习。"
                "若不能确定出处，就不要在标题里标来源，不得凭空写「板书」「课件」。")
    return ("本节材料中**没有出现任何例题**：**不得写任何 `### 例` 小节**，"
            "也不要把自编的例子伪装成例题。需要说明直观时，可以在注里写「例如…」作行内说明。")


# ---- P0 证明门控 ----
# 定理/命题/引理/推论陈述的位置：排除"由定理1得"这类引用（前面不能是由/按/用/据/个/这/那），
# 且关键词后必须紧跟编号、括号名或冒号（否则是"这个定理很重要"这类散文提及）
_THEOREM_KW = re.compile(r"(?<![由按用据个这那])(定理|命题|引理|推论)(?=\s*(?:[0-9一二三四五六七八九十]|[（(]|[:：]))")
_NEXT_ITEM = re.compile(r"(定义|定理|性质|命题|引理|推论|例|注)\s*[0-9一二三四五六七八九十]")
# 规则1：窗口内出现独立"证明/证："标志
_PROOF_HEAD = re.compile(r"(?:^|\n)\s*(?:证明|证)\s*[:：]|证明如下|下面证明|我们来证明")
# 规则2：五类证明标志词（同类多次只算一类），≥2 类即有证明
_PROOF_MARKS = (r"证明", r"反证", r"归纳", r"不妨设", r"假设[^。]{0,12}成立")
# 规则3：≥2 个数学符号且含「故/从而」
_MATH_SYM = re.compile(r"[=≠≤≥∈∀∃⇒→∑∏√]|det\s*\(|\(-?1\)\^|\|[A-Z]\|")
_CONCLUDE = re.compile(r"故|从而")


def _detect_proof_material(context, max_win=None):
    """逐定理判定材料中有无推导过程。
    窗口 = 定理陈述句结束 → 下一条目出现处，上限 PROOF_WINDOW_MAX 字。
    返回 [{typ, idx, stmt, has_proof, excerpt}]。"""
    max_win = max_win or config.PROOF_WINDOW_MAX
    out = []
    for i, m in enumerate(_THEOREM_KW.finditer(context), 1):
        end = context.find("。", m.end())
        if end == -1 or end - m.end() > 300:
            end = m.end()
        start = end + 1 if end != m.end() else m.end()
        nxt = _NEXT_ITEM.search(context, start)
        win_end = min(nxt.start() if nxt else len(context), start + max_win)
        win = context[start:win_end]

        has = bool(_PROOF_HEAD.search(win))
        if not has:
            has = sum(1 for p in _PROOF_MARKS if re.search(p, win)) >= 2
        if not has:
            has = len(_MATH_SYM.findall(win)) >= 2 and bool(_CONCLUDE.search(win))

        stmt = context[m.start():end + 1].strip()
        out.append({"typ": m.group(1), "idx": i, "stmt": stmt[:20],
                    "has_proof": has, "excerpt": win.strip()[:800]})
    return out


def _proof_gate_block(context):
    """把检测结果格式化为提示词段落：结论 + 原文定位片段（压制模型复述定义）。"""
    items = _detect_proof_material(context)
    if not items:
        return "（本节材料中未检测到定理陈述，按原文实际情况处理。）"
    lines = ["以下每条定理已按原文判定有无推导过程，**必须逐条遵守**："]
    for it in items:
        label = f"{it['typ']}{it['idx']}「{it['stmt']}…」"
        if it["has_proof"]:
            lines.append(f"- {label}：材料中**有**推导过程。可写 `### 证明`，但推导步骤不得超出下面片段的内容。")
        else:
            lines.append(f"- {label}：材料中**没有**推导过程。**只许写 `### 证明思路`**（2–3 句，注明「完整证明见教材」），**不得写 `### 证明`**。")
        if it["excerpt"]:
            lines.append(f"  【原文片段】{it['excerpt']}")
    return "\n".join(lines)


def _relevant_context(topic, full_text, max_chars=None):
    """按话题关键词从全文中检索相关段落（证据 + 命中窗口），控制在 max_chars 内。"""
    max_chars = max_chars or config.CONTEXT_MAX_CHARS
    parts = []
    evidence = topic.get("evidence", "")
    if evidence:
        parts.append(f"【相关原文证据】\n{evidence}")

    kws = keywords_of(topic)
    freq = {kw: full_text.count(kw) for kw in kws}
    ranges = []      # (出现次数, -词长, 起, 止)
    for kw in kws:
        start = 0
        while True:
            idx = full_text.find(kw, start)
            if idx == -1:
                break
            a, b = max(0, idx - 400), min(len(full_text), idx + 800)
            if not any(a < r[3] and b > r[2] for r in ranges):
                ranges.append((freq[kw], -len(kw), a, b))
            start = idx + len(kw)
            if len(ranges) > 30:
                break
        if len(ranges) > 30:
            break
    ranges.sort(key=lambda r: (r[0], r[1], r[2]))
    for _, _, a, b in ranges:
        parts.append(full_text[a:b])
        if len("\n\n".join(parts)) >= max_chars:
            break

    ctx = "\n\n".join(parts)
    if not ctx.strip():
        ctx = full_text[:max_chars]      # 兜底
    return ctx[:max_chars]


def gen_single_topic(topic, full_text, project=None, chunks=None):
    """生成单个章节的讲义。按 topic['type'] 路由到知识笔记或习题讲解。
    返回 (正文, 参考url列表)。空或过短（疑似截断）则重试 GEN_RETRY 次。"""
    name = topic["name"]
    importance = topic.get("importance", "重要")
    summary = topic.get("summary", "")
    evidence = topic.get("evidence", "")
    ttype = topic.get("type", "knowledge")

    # 联网补全（默认关闭，见 config.ENABLE_WEB_SEARCH）
    wr = search.web_search(f"数学 {name}")
    web_block = search.format_web_block(wr)
    urls = [r["url"] for r in wr if r.get("url")]

    context = _relevant_context(topic, full_text)

    members = topic.get("members") or []
    subtopics = ("、".join(members) if len(members) > 1
                 else "（本章围绕主题展开，按原文讲授顺序写）")

    tpl = _EXERCISE_TPL if ttype == "exercise" else _GEN_TPL
    prompt = tpl.format(
        topic=name, importance=importance, summary=summary, subtopics=subtopics,
        evidence=evidence or "(原文未定位到直接证据，请依据相关文本推断)",
        full_text=context, web_block=web_block or "（无）",
        structure="、".join(config.GEN_STRUCTURE),
        proof_end=config.GEN_PROOF_END or "（不写结尾标记）",
        tone=_TONE_TEXT.get(config.GEN_TONE, config.GEN_TONE),
        formula=_FORMULA_TEXT.get(config.GEN_FORMULA, config.GEN_FORMULA),
        example_rule=_example_rule(full_text),
        proof_gate=_proof_gate_block(context),
    )
    system = _SYSTEM
    if project:
        system = proj_mod.project_prompt_block(project) + system
    opts = {"num_ctx": 16384, "num_predict": config.GEN_MAX_TOKENS}
    for attempt in range(1, config.GEN_RETRY + 1):
        res = ollama_client.chat(config.GEN_MODEL, [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], timeout=config.GEN_TIMEOUT, think=False, options=opts)
        res = (res or "").strip()
        if res and len(res) >= config.GEN_MIN_CHARS:
            return res, urls
        if res:
            print(f"  [gen] 章节「{name}」第{attempt}次仅 {len(res)} 字（疑似截断），重试...")
            prompt += "\n\n（上一次输出被截断，请从头完整写出本节，务必包含方法小结。）"
        else:
            print(f"  [gen] 章节「{name}」第{attempt}次返回空，重试...")
    return f"> 该章节「{name}」未生成成功。\n", urls


def _strip_section_heading(body, name):
    """去掉模型自带的章节标题行（## 名称 / # 名称）。"""
    lines = body.strip().split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        return "\n".join(lines[1:]).strip()
    return body.strip()


def _split_long_sections(sections):
    """P2③ 单章过长（> SECTION_SPLIT_CHARS）时按 ### 条目拆回两节。
    拆分点三条同时满足：条目标题名在本节首次出现 + 前置累计 ≥ SECTION_SPLIT_MIN_PREFIX
    + 拆分后两段各含至少一个 ### 条目。找不到合法拆分点则保持原样。"""
    out, split_cnt = [], 0
    for sec in sections:
        body = sec["body"]
        if len(body) <= config.SECTION_SPLIT_CHARS:
            out.append(sec)
            continue
        blocks = numbering._split_blocks(body)
        names = []          # 每块的条目名（非条目块为 ""）
        for b in blocks:
            mh = numbering._BLOCK_HEAD.match(b.split("\n", 1)[0].strip())
            nm = ""
            if mh:
                mi = re.match(
                    r"^(定义|定理|性质|命题|引理|推论|例)\s*[0-9.]*\s*(?:[（(](.+?)[）)])?\s*$",
                    mh.group(1).strip())
                if mi:
                    nm = (mi.group(2) or "").strip()
            names.append(nm)
        prefix, earlier, split_at = 0, "", None
        for i, b in enumerate(blocks):
            nm = names[i]
            if (i > 0 and nm and prefix >= config.SECTION_SPLIT_MIN_PREFIX
                    and nm not in earlier and any(names[:i])):
                split_at = i
                break
            prefix += len(b) + 2
            earlier += b + "\n"
        if split_at is None:
            out.append(sec)
            continue
        title1 = next((n for n in names[:split_at] if n), sec["title"])
        out.append({"no": 0, "title": title1, "body": "\n\n".join(blocks[:split_at])})
        out.append({"no": 0, "title": names[split_at], "body": "\n\n".join(blocks[split_at:])})
        split_cnt += 1
    for i, s in enumerate(out, 1):
        s["no"] = i
    if split_cnt:
        print(f"  [gen] {split_cnt} 个超长章节已按条目拆回两节")
    return out


def build_notes(topics, full_text, project=None, chunks=None, date=None):
    """逐章节生成，拼成完整讲义（含标题、元信息、目录、全局编号）。
    返回 (markdown, 全部参考url)。"""
    sections, all_urls = [], []
    for i, t in enumerate(topics, 1):
        print(f"  [gen] ({i}/{len(topics)}) {t['name']}...")
        body, urls = gen_single_topic(t, full_text, project, chunks)
        sections.append({
            "no": i,
            "title": t["name"],
            "body": _strip_boilerplate(sanitize_math(_strip_section_heading(body, t["name"]))),
        })
        all_urls.extend(urls)

    sections = _split_long_sections(sections)

    # 标题：取第一个【核心】章节名，否则取第一节
    title = next((t["name"] for t in topics if t.get("importance") == "核心"),
                 topics[0]["name"] if topics else "未命名")
    course = vault_mod._infer_course(full_text)
    date = date or datetime.now().strftime(config.DATE_FMT)
    meta = [
        f"> 课程：{course}　日期：{date}　类型：课堂整理",
        f"> 来源：课堂转写自动整理（共 {len(sections)} 节）",
    ]

    markdown = numbering.finalize(sections, title, meta)

    # 汇总参考来源（去重）
    seen, uniq = set(), []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    if uniq:
        markdown = markdown.rstrip() + "\n\n## 参考来源\n" + "\n".join(f"- {u}" for u in uniq) + "\n"
    return markdown, uniq
