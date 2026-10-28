"""排版后处理：章节编号、条目编号、目录、跨节去重。

模型自己编的编号在多章节拼接后会重复（实测「定理 2.1」出现 47 次），
因此编号统一由本模块按章节顺序重排，正文中的引用同步替换。
"""
import re
from difflib import SequenceMatcher

import config

# 需要编号的条目类型（"注"按参考文档惯例不编号）
NUMBERED = ("定义", "定理", "性质", "命题", "引理", "推论", "例")
_ITEM = re.compile(
    r"^(?P<hashes>#{2,4}\s*)?(?P<typ>定义|定理|性质|命题|引理|推论|注|例)"
    r"\s*(?P<num>[0-9]+(?:\.[0-9]+)*)?\s*(?P<rest>.*)$"
)


def _is_item_line(line, is_heading_ok=True):
    m = _ITEM.match(line)
    if not m:
        return None
    if m.group("hashes"):
        return m
    if not is_heading_ok:
        return None
    # 非标题行：只有"编号 + 至少 4 个字正文"才当作条目声明，避免把普通句子当条目
    if m.group("num") and len(m.group("rest").strip()) >= 4:
        return m
    return None


def _number_section(body, ch):
    """一节内的条目重编号：定义/定理/… → 类型 {ch}.{序号}，并同步正文引用。"""
    lines = body.split("\n")
    counters = {}
    mapping = {}          # 旧标签 → 新标签（仅带旧编号的条目）
    item_lines = {}       # 行号 → (hashes, typ, new_num, rest)
    for i, ln in enumerate(lines):
        m = _is_item_line(ln)
        if not m:
            continue
        typ = m.group("typ")
        if typ not in NUMBERED:
            continue
        counters[typ] = counters.get(typ, 0) + 1
        new_num = f"{ch}.{counters[typ]}"
        old_num = m.group("num")
        if old_num:
            mapping[f"{typ} {old_num}"] = f"{typ} {new_num}"
            mapping[f"{typ}{old_num}"] = f"{typ} {new_num}"
        item_lines[i] = (m.group("hashes") or "", typ, new_num, m.group("rest").strip())

    # 先用哨兵替换所有旧标签，避免新编号与旧编号互相污染
    text = "\n".join(lines)
    for old in sorted(mapping, key=len, reverse=True):
        pat = re.compile(r"(?<![0-9A-Za-z])" + re.escape(old) + r"(?![0-9])")
        text = pat.sub("\x00" + mapping[old] + "\x01", text)
    text = text.replace("\x00", "").replace("\x01", "")

    # 再改写条目行本身（标题 / 行首声明）
    lines = text.split("\n")
    for i, (hashes, typ, new_num, rest) in item_lines.items():
        if i >= len(lines):
            continue
        tail = ""
        if rest:
            tail = rest if rest.startswith(("（", "(")) else " " + rest
        lines[i] = f"{hashes}{typ} {new_num}{tail}"
    return "\n".join(lines)


def _demote_inner_h2(body):
    """节内的 ## （如"方法小结"）降为 ###，避免打乱章节层级。"""
    return re.sub(r"^##\s+", "### ", body, flags=re.MULTILINE)


_NOTE_HEAD = re.compile(r"^###\s*注\s*[（(]?(.*?)[）)]?\s*$")


def _cap_notes(body, limit=2):
    """一节内注的数量上限：超出的注改为正文里的加粗小标题（讲解保留、不再充当独立条目）。"""
    out, count, converted = [], 0, 0
    for ln in body.split("\n"):
        m = _NOTE_HEAD.match(ln.strip())
        if m:
            count += 1
            if count > limit:
                title = m.group(1).strip()
                out.append(f"**{title}**" if title else "")
                converted += 1
                continue
        out.append(ln)
    if converted:
        print(f"  [numbering] {converted} 条注超出每节上限，转为正文说明")
    return "\n".join(out)


def _norm_para(p):
    """段落归一：去空白与标点，只留文字/数字，用于相似度比较。"""
    return re.sub(r"[\W_]+", "", p)


def _same_para(a, b, threshold=0.75):
    """段落级相似判定（模型复述时措辞会变，不能只比全等）。"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if min(la, lb) / max(la, lb) < 0.6:
        return False
    sm = SequenceMatcher(None, a[:1500], b[:1500])
    if sm.quick_ratio() < threshold:
        return False
    return sm.ratio() >= threshold


def _dedupe(sections):
    """跨节去重：相同或高度相似的正文段落，只保留首次出现，其余标注交叉引用。"""
    seen = []          # [(归一文本, 章节号)]
    hit = 0
    for sec in sections:
        paras = sec["body"].split("\n\n")
        out = []
        for p in paras:
            key = _norm_para(p)
            bad = (not key) or key.startswith("#") or key.startswith("|") \
                or key.startswith(">") or key.startswith("-") or key.startswith("*")
            long_cn = len(key) >= 60 and len(re.findall(r"[\u4e00-\u9fff]", key)) >= 15
            if bad or not long_cn:
                out.append(p)
                continue
            matched = next((no for k, no in seen if _same_para(k, key)), None)
            if matched is not None:
                out.append(f"（此段与 §{matched} 内容相同，不再重复）")
                hit += 1
            else:
                seen.append((key, sec["no"]))
                out.append(p)
        sec["body"] = "\n\n".join(out)
    if hit:
        print(f"  [numbering] 跨节去重：合并 {hit} 段重复内容")
    return sections


_REF = re.compile(r"(定义|定理|性质|命题|引理|推论|例)\s*([0-9]+(?:\.[0-9]+)*)")
_ITEM_HEAD = re.compile(r"^#{2,4}\s*(定义|定理|性质|命题|引理|推论|例)\s*([0-9]+(?:\.[0-9]+)*)")
_SUMMARY_HEAD = re.compile(r"^#{2,4}\s*(方法小结|常见误区)")
_ANY_HEAD = re.compile(r"^#{1,4}\s")


def _filter_bad_refs(sections):
    """方法小结/常见误区里引用了不存在的条目号（模型实测会写「定理 6 的证明骨架」）
    → 删掉该条，并重新给列表编号，避免出现 1、3、4 的空号。"""
    existing = set()
    for sec in sections:
        for ln in sec["body"].split("\n"):
            m = _ITEM_HEAD.match(ln)
            if m:
                existing.add(f"{m.group(1)} {m.group(2)}")

    dropped = 0
    for sec in sections:
        out, in_summary, idx = [], False, 0
        for ln in sec["body"].split("\n"):
            if _SUMMARY_HEAD.match(ln):
                in_summary = True
                out.append(ln)
                continue
            if _ANY_HEAD.match(ln):
                in_summary = False
                out.append(ln)
                continue
            if in_summary and re.match(r"^\s*(?:[0-9]+[\.、)]|[-*])\s*", ln):
                bad = [f"{a} {b}" for a, b in _REF.findall(ln) if f"{a} {b}" not in existing]
                if bad:
                    dropped += 1
                    continue
                idx += 1
                out.append(re.sub(r"^\s*(?:[0-9]+[\.、)]|[-*])\s*", f"{idx}. ", ln))
                continue
            out.append(ln)
        sec["body"] = "\n".join(out)
    if dropped:
        print(f"  [numbering] 删除 {dropped} 条引用了不存在条目的说明")
    return sections


_BLOCK_HEAD = re.compile(r"^###\s+(.*)$")
_BLOCK_ITEM = re.compile(r"^(定义|定理|性质|命题|引理|推论|例)\s*[0-9.]*\s*(?:[（(](.+?)[）)])?\s*$")
_BLOCK_PROOF = re.compile(r"^证明")


def _split_blocks(body):
    """按 ### 标题把一节拆成若干块（每块含标题行及其正文）。"""
    blocks, cur = [], []
    for ln in body.split("\n"):
        if _BLOCK_HEAD.match(ln) and cur:
            blocks.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _preprocess_items(sections):
    """条目级整理：
    1) 定义后面紧跟的「证明」是模型硬凑的（定义不需要证明）→ 删除；
    2) 同名条目（类型+括号名全同，跨节或同节）→ 无条件合并：两部分正文取并集
       并入首次出现处（段落级去重），后续重复块整体删除。
       在编号之前执行，不会产生悬空引用。
    """
    # 第一遍：删"定义后硬凑的证明"，并收集各节的块
    dropped_proof = 0
    sec_blocks = []
    for sec in sections:
        out, last_type = [], None
        for b in _split_blocks(sec["body"]):
            head_line = b.split("\n", 1)[0].strip()
            m_head = _BLOCK_HEAD.match(head_line)
            if not m_head:
                out.append(b)
                continue
            head = m_head.group(1).strip()

            if _BLOCK_PROOF.match(head):
                if last_type == "定义":
                    dropped_proof += 1
                    continue
                out.append(b)
                continue

            if head.startswith("注"):
                out.append(b)       # 注不打断"上一条目是定义"的判断
                continue

            m = _BLOCK_ITEM.match(head)
            last_type = m.group(1) if m else None
            out.append(b)
        sec_blocks.append(out)

    # 第二遍：定位同名条目（首次出现 + 各重复块）
    first, dups = {}, {}
    for si, blocks in enumerate(sec_blocks):
        for bi, b in enumerate(blocks):
            mh = _BLOCK_HEAD.match(b.split("\n", 1)[0].strip())
            if not mh:
                continue
            m = _BLOCK_ITEM.match(mh.group(1).strip())
            if not m:
                continue
            typ, name = m.group(1), (m.group(2) or "").strip()
            if not name or typ == "例":
                continue
            key = (typ, name)
            if key in first:
                dups.setdefault(key, []).append((si, bi))
            else:
                first[key] = (si, bi)

    # 第三遍：正文并集并入首次出现处，重复块删除
    merged_cnt = 0
    drop_set = set()
    for key, ds in dups.items():
        fi, fj = first[key]
        base = sec_blocks[fi][fj]
        base_norms = [_norm_para(p) for p in base.split("\n\n")]
        added = []
        for si, bi in ds:
            blk = sec_blocks[si][bi]
            body = blk.split("\n", 1)[1] if "\n" in blk else ""
            for p in body.split("\n\n"):
                p = p.strip()
                if not p:
                    continue
                np_ = _norm_para(p)
                if len(np_) < 10:                      # 太短的碎片不搬
                    continue
                if any(_same_para(np_, bn) for bn in base_norms):
                    continue                           # 与已有段落重复的不搬
                added.append(p)
                base_norms.append(np_)
        if added:
            sec_blocks[fi][fj] = base.rstrip() + "\n\n" + "\n\n".join(added)
        for si, bi in ds:
            drop_set.add((si, bi))
        merged_cnt += len(ds)

    for si, blocks in enumerate(sec_blocks):
        sections[si]["body"] = "\n\n".join(
            b.strip("\n") for bi, b in enumerate(blocks) if (si, bi) not in drop_set)
    if dropped_proof:
        print(f"  [numbering] 删除 {dropped_proof} 个定义后面硬凑的证明")
    if merged_cnt:
        print(f"  [numbering] 同名条目合并 {merged_cnt} 个（正文并集已并入首次出现处）")
    return sections


# ---- P1 类型内去重 ----
_DEDUP_ITEM_HEAD = re.compile(
    r"^(定义|定理|性质|命题|引理|推论|例)\s*([0-9]+(?:\.[0-9]+)*)?\s*(?:[（(](.+?)[）)])?\s*$")
# 多出段纯虚词才允许合并（实词如"代数""递归" → 不合并，只加参见）
_FUNCTION_WORDS = set("的与和及或其对由按为之并、·/ ")
# 允许跨类型比较的组合：定义 ↔ 定理（同一内容被一次写成定义、一次写成定理）
_CROSS_PAIRS = {frozenset(("定义", "定理"))}


def _extra_ok(extra):
    """标题互为子串时，多出段是否允许合并：整体是白名单结构性后缀，或纯虚词。"""
    extra = extra.strip()
    if not extra:
        return True
    wl = {w.lstrip("的") for w in config.ITEM_MERGE_SUFFIX_WHITELIST}
    if extra.lstrip("的") in wl:
        return True
    return all(ch in _FUNCTION_WORDS for ch in extra)


def _dedupe_items_by_content(sections):
    """P1：跨节比较条目（同类型 + 定义↔定理），在编号之后运行（可引用 §k 定义 j）。
    - 标题互为子串 + 多出段过白名单/纯虚词 + 正文相似 ≥ 阈值 → 合并：保留两条标题，
      后者正文替换为交叉引用（不取首次名称做规范名）。
    - 标题互为子串但多出段含实词（如"代数余子式"多出"代数"）→ 不合并，
      只在后者正文末尾加「（参见 §k 定义 j）」。
    - 同节内不比较；例除外；目录只含 §N 章标题，被合并条目本就不进目录。"""
    threshold = config.ITEM_DEDUP_THRESHOLD
    sec_blocks = [_split_blocks(sec["body"]) for sec in sections]
    items = []          # [sec_i, block_i, typ, num, name]
    for si, blocks in enumerate(sec_blocks):
        for bi, b in enumerate(blocks):
            mh = _BLOCK_HEAD.match(b.split("\n", 1)[0].strip())
            if not mh:
                continue
            mi = _DEDUP_ITEM_HEAD.match(mh.group(1).strip())
            if not mi:
                continue
            typ, num, name = mi.group(1), mi.group(2) or "", (mi.group(3) or "").strip()
            if typ == "例" or not name:
                continue
            items.append([si, bi, typ, num, name])

    def _pair_ok(t1, t2):
        return t1 == t2 or frozenset((t1, t2)) in _CROSS_PAIRS

    replaced, appended = {}, {}
    merged_cnt = ref_cnt = 0
    for j in range(len(items)):
        si2, bi2, typ2, num2, name2 = items[j]
        if (si2, bi2) in replaced:
            continue
        # 第一遍：找可合并的先行者
        for i in range(j):
            si1, bi1, typ1, num1, name1 = items[i]
            if si1 == si2 or not _pair_ok(typ1, typ2):
                continue
            short, long_ = (name1, name2) if len(name1) <= len(name2) else (name2, name1)
            if short not in long_:
                continue
            if not _extra_ok(long_.replace(short, "", 1)):
                continue
            if _same_para(_norm_para(sec_blocks[si1][bi1]),
                          _norm_para(sec_blocks[si2][bi2]), threshold=threshold):
                head2 = sec_blocks[si2][bi2].split("\n", 1)[0]
                no1 = sections[si1]["no"]
                replaced[(si2, bi2)] = (head2 +
                    f"\n\n（内容与 §{no1} 的 {typ1} {num1}（{name1}）相同，见前文。）")
                merged_cnt += 1
                break
        if (si2, bi2) in replaced:
            continue
        # 第二遍：不可合并但标题相关 → 加参见
        for i in range(j):
            si1, bi1, typ1, num1, name1 = items[i]
            if si1 == si2 or not _pair_ok(typ1, typ2):
                continue
            short, long_ = (name1, name2) if len(name1) <= len(name2) else (name2, name1)
            if short in long_ and not _extra_ok(long_.replace(short, "", 1)):
                no1 = sections[si1]["no"]
                appended[(si2, bi2)] = f"（参见 §{no1} {typ1} {num1}）"
                ref_cnt += 1
                break

    for si, blocks in enumerate(sec_blocks):
        new = []
        for bi, b in enumerate(blocks):
            if (si, bi) in replaced:
                new.append(replaced[(si, bi)])
            elif (si, bi) in appended:
                new.append(b.rstrip() + "\n\n" + appended[(si, bi)])
            else:
                new.append(b)
        sections[si]["body"] = "\n\n".join(x.strip("\n") for x in new)
    if merged_cnt:
        print(f"  [numbering] 类型内去重：合并 {merged_cnt} 个跨节重复条目")
    if ref_cnt:
        print(f"  [numbering] {ref_cnt} 个相关条目加注「参见」")
    return sections


def finalize(sections, title, meta_lines):
    """sections: [{"no": 1, "title": str, "body": str}]（body 不含章节标题行）。
    返回完整 markdown（含 H1、元信息、目录、章节编号）。"""
    for sec in sections:
        body = sec["body"]
        body = re.sub(r"^(#\s+.*\n)+", "", body)          # 去掉模型自带的 H1
        # 去掉与章节名重复的首行标题
        body = re.sub(r"^\s*#{1,6}\s*" + re.escape(sec["title"]) + r"\s*\n+", "", body)
        body = _demote_inner_h2(body).strip()
        sec["body"] = _cap_notes(body)

    _preprocess_items(sections)
    for sec in sections:
        sec["body"] = _number_section(sec["body"], sec["no"])
    _dedupe_items_by_content(sections)
    _filter_bad_refs(sections)
    _dedupe(sections)

    parts = [f"# {title}", ""]
    if meta_lines:
        parts.extend(meta_lines)
        parts.extend(["", "---", ""])

    if len(sections) > 1:
        parts.append("## 目录")
        parts.append("")
        for sec in sections:
            parts.append(f"- §{sec['no']}　{sec['title']}")
        parts.extend(["", "---", ""])

    for sec in sections:
        parts.append(f"## §{sec['no']}　{sec['title']}")
        parts.append("")
        parts.append(sec["body"])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
