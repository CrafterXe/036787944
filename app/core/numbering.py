"""排版后处理：章节编号、条目编号、目录、跨节去重。

模型自己编的编号在多章节拼接后会重复（实测「定理 2.1」出现 47 次），
因此编号统一由本模块按章节顺序重排，正文中的引用同步替换。
"""
import json
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


_PROOF_END_ONLY = re.compile(r"^(证完[。．.]?|∎|Q\.?E\.?D\.?)$")


def _dedupe(sections):
    """去重：相同或高度相似的正文段落，跨 §N 章节时只保留首次出现并标注交叉引用；
    同节内（同一 ## §N，无论是否跨 ### 实例）保留两处原文——避免读者在节内反复翻找。"""
    seen = []          # [(归一文本, 章节号, 所属###标题实例序号)]
    hit = kept = 0
    for sec in sections:
        paras = sec["body"].split("\n\n")
        out, head_idx = [], -1
        for p in paras:
            first_line = p.split("\n", 1)[0].strip()
            if first_line.startswith("###"):
                head_idx += 1
            key = _norm_para(p)
            bad = (not key) or key.startswith("#") or key.startswith("|") \
                or key.startswith(">") or key.startswith("-") or key.startswith("*")
            long_cn = len(key) >= 60 and len(re.findall(r"[\u4e00-\u9fff]", key)) >= 15
            if bad or not long_cn:
                # 证完悬空：上一段刚被替换成交叉引用，独立的证完/∎段一并删除
                if _PROOF_END_ONLY.match(p.strip()) and out \
                        and out[-1].startswith("（此段与"):
                    hit += 1
                    continue
                out.append(p)
                continue
            matched = next((item for item in seen
                            if (item[1], item[2]) != (sec["no"], head_idx)
                            and _same_para(item[0], key)), None)
            if matched is not None:
                if matched[1] == sec["no"]:
                    kept += 1              # 同节 → 保留原文，不生成占位符
                    out.append(p)
                else:
                    out.append(f"（此段与 §{matched[1]} 内容相同，不再重复）")
                    hit += 1
            else:
                seen.append((key, sec["no"], head_idx))
                out.append(p)
        sec["body"] = "\n\n".join(out)
    if hit:
        print(f"  [numbering] 跨节去重：处理 {hit} 段重复/悬空内容")
    if kept:
        print(f"  [numbering] 同节重复 {kept} 段按原文保留（不生成占位符）")
    return sections


# ---- 段落合并防碎片化 / 假证完拦截 ----
_LIST_LINE = re.compile(r"^\s*(?:[0-9]+[.、)]|[-*+]|>)")


def _is_plain_para(p):
    """普通正文段落判定：非标题、非独立公式、非列表/引用、非交叉引用占位、非证完标记。"""
    s = p.strip()
    if not s or s.startswith("#"):
        return False
    if "$$" in s or "\\[" in s:
        return False
    if _LIST_LINE.match(s):
        return False
    if _PROOF_END_ONLY.match(s):
        return False
    if s.startswith("（") and s.rstrip("。").endswith("）"):
        return False
    return True


def merge_short_paragraphs(text, min_chars=30):
    """碎片化修复：正文短段（< min_chars 字）且下一段也是普通正文 → 向前合并成一段。
    标题、独立公式、列表项、引用、交叉引用占位、证完标记均不参与合并。"""
    paras = [p.strip() for p in text.split("\n\n")]
    out, i, merged = [], 0, 0
    while i < len(paras):
        p = paras[i]
        if _is_plain_para(p) and len(_norm_para(p)) < min_chars:
            buf, j = p, i + 1
            while j < len(paras) and _is_plain_para(paras[j]) \
                    and len(_norm_para(buf)) < min_chars:
                buf += paras[j]          # 中文拼接不加空格
                j += 1
                merged += 1
            out.append(buf)
            i = j
        else:
            out.append(p)
            i += 1
    if merged:
        print(f"  [numbering] 碎片化合并：{merged} 个短段并入前段")
    return "\n\n".join(out)


_PROOF_START = ("### 证明", "**证明**")
_PROOF_END = re.compile(r"证完|∎|Q\.?E\.?D", re.I)
_SKIP_WORDS = ("可以证明", "同理可得", "依此类推")


def check_proof_integrity(text, min_proof=40, skip_limit=150):
    """假证完/跳步拦截：
    规则A：证明正文 < min_proof 字 → 删证完/∎，整段降级为「### 证明思路」；
    规则B：含跳步词（可以证明/同理可得/依此类推）且正文 < skip_limit 字
           → 删证完，末尾追加「（注：此处推导过程略，请结合板书或教材补充）」。"""
    paras = text.split("\n\n")
    out, i, cnt_a, cnt_b = [], 0, 0, 0
    while i < len(paras):
        p = paras[i]
        first = p.split("\n", 1)[0].strip()
        if first not in _PROOF_START:
            out.append(p)
            i += 1
            continue
        # 收集证明正文：本段余下部分 + 后续段，直到结束标记或下一个标题段
        body_parts = []
        rest = p.split("\n", 1)[1] if "\n" in p else ""
        if rest.strip():
            body_parts.append(rest.strip())
        j = i + 1
        while j < len(paras):
            q = paras[j].strip()
            if q.startswith("#"):
                break
            body_parts.append(q)
            j += 1
            if _PROOF_END.search(q):
                break
        body = "\n\n".join(body_parts)
        core_n = len(_norm_para(_PROOF_END.sub("", body)))
        if core_n < min_proof:
            new_body = _PROOF_END.sub("", body).strip()
            out.append("### 证明思路" + ("\n" + new_body if new_body else ""))
            cnt_a += 1
            i = j
        elif core_n < skip_limit and any(w in body for w in _SKIP_WORDS):
            new_body = _PROOF_END.sub("", body).strip()
            new_body += "（注：此处推导过程略，请结合板书或教材补充）"
            out.append("### 证明\n" + new_body)
            cnt_b += 1
            i = j
        else:
            out.append(p)                # 合格证明：只追加首段，正文段按原样逐个处理
            i += 1
    if cnt_a or cnt_b:
        print(f"  [numbering] 证明校验：{cnt_a} 个降级为思路，{cnt_b} 个标记推导略")
    return "\n\n".join(out)


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
                idx = 0            # 每个列表标题（方法小结/常见误区）各自从 1 开始
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
_BLOCK_PROOF = re.compile(r"^证明\s*$")   # 精确匹配；「证明思路」不算证明（避免降级后被误删）


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


# ---- 定理陈述句去重 ----
THEOREM_STMT_THRESHOLD = 0.8
_STMT_TYPES = ("定理", "推论", "引理")
_NEG_WORDS = ("无", "不", "非", "没有")
# 修饰性复合词：含否定字但不对命题取反，检查前先剥离
_NEG_SAFE_WORDS = ("非常数", "非零", "非空", "非平凡", "非负", "不同")
_MARK = "\x02THM:%d:%d\x03"


def _conclusion_sentence(body):
    """从定理块正文抽结论句：优先含「则/当且仅当/等价/充要」的长句，其次含「是/为」的长句。
    句子再按「，则」切分，只留结论部分（前面是假设从句，会拉低相似度）。"""
    sents = [s.strip() for s in re.split(r"[。！？；\n]", body) if s.strip()]
    cands = [s for s in sents if len(_norm_para(s)) >= 10]
    if not cands:
        return ""
    chosen = ""
    for key in ("则", "当且仅当", "等价", "充要"):
        hit = [s for s in cands if key in s]
        if hit:
            chosen = max(hit, key=len)
            break
    if not chosen:
        hit = [s for s in cands if "是" in s or "为" in s]
        chosen = max(hit, key=len) if hit else cands[0]
    parts = chosen.rsplit("，则", 1)
    if len(parts) == 2 and len(_norm_para(parts[1])) >= 6:
        return parts[1]
    return chosen


def _lcs_ratio(a, b):
    """最长公共子序列占较长串的比例（0–1）。长度差过大时直接判 0。"""
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    if min(la, lb) / max(la, lb) < 0.6:
        return 0.0
    if lb > la:
        a, b, la, lb = b, a, lb, la
    prev = [0] * (lb + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(cur[j - 1], prev[j]))
        prev = cur
    return prev[-1] / la


def _lcs_len(a, b):
    """最长公共子序列的长度。"""
    if not a or not b:
        return 0
    if len(b) > len(a):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(cur[j - 1], prev[j]))
        prev = cur
    return prev[-1]


def _overlap_ratio(a, b):
    """LCS 占较短串的比例：容忍「一句话包含另一句」式改写，用于假设/结论分段比对。"""
    if not a or not b:
        return 0.0
    return _lcs_len(a, b) / min(len(a), len(b))


def _neg_conflict(a, b):
    """否定/不等号不一致 → 视为不同命题（防「有重因式」与「无重因式」误并）。
    先剥离「非常数/非零/不同」这类修饰性复合词，它们不是命题层面的否定。"""
    aa, bb = a, b
    for w in _NEG_SAFE_WORDS:
        aa = aa.replace(w, "")
        bb = bb.replace(w, "")
    if any(w in aa for w in _NEG_WORDS) != any(w in bb for w in _NEG_WORDS):
        return True
    return ("≠" in aa) != ("≠" in bb)


def _dedupe_theorems_by_statement(sections):
    """按定理陈述句去重（在编号之前执行，保证不留编号空洞）：
    定理/推论/引理的结论句 LCS 占比 ≥ 0.8 → 保留首次出现的完整块（含证明），
    后续重复块连同其证明整体删除，原位置留占位标记，编号后解析为「（同上：见 §X 定理 Y）」。
    名字相近但结论句相似度不足 0.8 时绝不合并。"""
    sec_blocks = [_split_blocks(sec["body"]) for sec in sections]
    items = []
    for si, blocks in enumerate(sec_blocks):
        for bi, b in enumerate(blocks):
            first = b.split("\n", 1)[0].strip()
            mh = _BLOCK_HEAD.match(first)
            if not mh:
                continue
            mi = _DEDUP_ITEM_HEAD.match(mh.group(1).strip())
            if not mi:
                continue
            typ, num = mi.group(1), mi.group(2) or ""
            if typ not in _STMT_TYPES or not num:
                continue
            body = b.split("\n", 1)[1] if "\n" in b else ""
            if body.strip().startswith(("（内容与", "（同上")):
                continue
            key = _norm_para(_conclusion_sentence(body))
            if len(key) < 6:
                continue
            items.append({"si": si, "bi": bi, "typ": typ, "num": num, "key": key})

    replaced, drop, merged = {}, set(), 0
    for j in range(len(items)):
        cur = items[j]
        if (cur["si"], cur["bi"]) in replaced:
            continue
        for i in range(j):
            prev = items[i]
            if (prev["si"], prev["bi"]) in replaced:
                continue
            if _neg_conflict(prev["key"], cur["key"]):
                continue
            if _lcs_ratio(prev["key"], cur["key"]) < THEOREM_STMT_THRESHOLD:
                continue
            replaced[(cur["si"], cur["bi"])] = _MARK % (prev["si"], prev["bi"])
            # 连带删除其后的证明块（含"证明思路"）
            k = cur["bi"] + 1
            while k < len(sec_blocks[cur["si"]]):
                h = sec_blocks[cur["si"]][k].split("\n", 1)[0].strip()
                mh = _BLOCK_HEAD.match(h)
                if not mh or not mh.group(1).strip().startswith("证明"):
                    break
                drop.add((cur["si"], k))
                k += 1
            merged += 1
            break

    if not merged:
        return sections
    for si, blocks in enumerate(sec_blocks):
        new = []
        for bi, b in enumerate(blocks):
            if (si, bi) in replaced:
                new.append(replaced[(si, bi)])
            elif (si, bi) in drop:
                continue
            else:
                new.append(b)
        sections[si]["body"] = "\n\n".join(x.strip("\n") for x in new)
    print(f"  [numbering] 定理陈述句去重：合并 {merged} 个重复定理（含其证明）")
    return sections


_SEM_PROMPT = """你是一个高代专家。下面是一些定理的结论句。
请找出语义完全等价的定理（只改变措辞，数学命题完全一致）。
只返回等价的分组，格式为：[["§1 定理 1.1", "§8 定理 8.2"], ["§2 定理 2.2", "§3 定理 3.3"]]
如果不确定等价，绝对不要把它们分在一组。只输出 JSON，不要解释。
单个定理不需要列出。

定理列表：
%s
"""


def _statement_text(body, limit=400):
    """抽取定理块正文中的命题全文（截止到「证明/证明思路」子块），供语义判定使用。
    只取结论句会丢假设从句，容易把「A⟹B」与「B⟹A」判成等价。"""
    out = []
    for ln in body.split("\n"):
        s = ln.strip()
        if not s or s.startswith(("（内容与", "（同上", "（参见", "（此段与")):
            continue
        if s.startswith(("证完", "∎")):
            continue
        if re.match(r"^\*{0,2}\s*(证明|讲解)", s):
            break
        out.append(s)
        if sum(len(x) for x in out) > limit:
            break
    return " ".join(out)


def _imp_parts(key):
    """把命题拆成（假设, 结论）：以「则」为分界；无「则」时假设为空。"""
    idx = key.find("则")
    if idx <= 0:
        return "", key
    return _norm_para(key[:idx]), _norm_para(key[idx + 1:])


_SEM_FULL_MIN = 0.55     # 全句词面相似度下限（模型提名的硬前提）
_SEM_CONS_MIN = 0.55     # 结论部分覆盖度下限


def _equiv_ok(a, b):
    """LLM 判定之后的确定性复核：全句要足够像，且结论部分高度重合，否定/不等号一致。
    实测 8B 会把「A⟹B」与「B⟹A」、乃至毫无关系的定理判成等价，故不能只信模型。"""
    if _neg_conflict(a, b):
        return False, "否定不一致"
    rf = _lcs_ratio(a, b)
    aa, ac = _imp_parts(a)
    ba, bc = _imp_parts(b)
    if not aa or not ba:
        return rf >= 0.8, f"无假设从句，全句 {rf:.2f}"
    rc = _overlap_ratio(ac, bc)
    lr = min(len(ac), len(bc)) / max(len(ac), len(bc))
    return (rf >= _SEM_FULL_MIN and rc >= _SEM_CONS_MIN and lr >= 0.7,
            f"全句 {rf:.2f}／结论 {rc:.2f}／长度比 {lr:.2f}")


def _collect_statement_items(sections):
    """收集定理/推论/引理的（编号, 标题, 命题全文），供语义去重使用。"""
    sec_blocks = [_split_blocks(sec["body"]) for sec in sections]
    items = []
    for si, blocks in enumerate(sec_blocks):
        for bi, b in enumerate(blocks):
            first = b.split("\n", 1)[0].strip()
            mh = _BLOCK_HEAD.match(first)
            if not mh:
                continue
            mi = _DEDUP_ITEM_HEAD.match(mh.group(1).strip())
            if not mi:
                continue
            typ, num = mi.group(1), mi.group(2) or ""
            if typ not in _STMT_TYPES or not num:
                continue
            body = b.split("\n", 1)[1] if "\n" in b else ""
            if body.strip().startswith(("（内容与", "（同上")):
                continue
            stmt = _statement_text(body)
            key = _norm_para(stmt)
            if len(key) < 6:
                continue
            items.append({
                "si": si, "bi": bi, "typ": typ, "num": num,
                "id": f"§{sections[si]['no']} {typ} {num}",
                "title": (mi.group(3) or "").strip(),
                "stmt": stmt, "key": key,
            })
    return sec_blocks, items


def _parse_groups(text):
    """解析 LLM 返回的分组 JSON；容错处理代码块围栏与多余文字。失败返回 None。"""
    if not text:
        return None
    data = None
    for cand in (text, (re.search(r"\[[\s\S]*\]", text) or [None])[0]):
        if not cand:
            continue
        try:
            data = json.loads(cand)
            break
        except Exception:
            continue
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if not isinstance(data, list):
        return None
    groups = []
    for g in data:
        if isinstance(g, list) and len(g) >= 2 and all(isinstance(x, str) for x in g):
            groups.append(list(dict.fromkeys(x.strip() for x in g)))
    return groups


def semantic_dedupe_theorems(sections):
    """P3 语义去重（可选，config.ENABLE_SEMANTIC_DEDUPE）：
    把定理结论句交给 LLM 判定语义等价分组，保留首次出现，其余块及其证明整体删除，
    原位置留占位标记（编号后解析为「（同上：见 §X 定理 Y）」）。
    任一环节失败（开关关闭/无响应/JSON 解析失败/ID 找不到）→ 整轮跳过，绝不崩溃。"""
    if not getattr(config, "ENABLE_SEMANTIC_DEDUPE", False):
        return sections
    sec_blocks, items = _collect_statement_items(sections)
    if len(items) < 2:
        return sections

    payload = [{"id": it["id"], "title": it["title"], "statement": it["stmt"]} for it in items]
    prompt = _SEM_PROMPT % json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        from . import ollama_client
        res = ollama_client.chat(
            config.SEMANTIC_DEDUPE_MODEL,
            [{"role": "user", "content": prompt}],
            timeout=getattr(config, "SEMANTIC_DEDUPE_TIMEOUT", 300),
            think=False, fmt="json",
            options={"num_ctx": 8192, "num_predict": 1200},
        )
    except Exception as e:
        print(f"  [numbering] 语义去重跳过：调用异常（{e}）")
        return sections
    if not res:
        print("  [numbering] 语义去重跳过：模型无响应")
        return sections
    groups = _parse_groups(res)
    if groups is None:
        print("  [numbering] 语义去重跳过：JSON 解析失败")
        return sections

    by_id = {it["id"]: it for it in items}
    unknown = [g for g in groups if any(x not in by_id for x in g)]
    if unknown:
        print(f"  [numbering] 语义去重跳过：分组含原文找不到的编号 {unknown[0]}")
        return sections

    replaced, drop, merged, skipped = {}, set(), 0, 0
    for g in groups:
        its = sorted((by_id[x] for x in g), key=lambda t: (t["si"], t["bi"]))
        keep = its[0]
        if (keep["si"], keep["bi"]) in replaced:
            skipped += 1
            continue
        kept_pairs = []
        for cur in its[1:]:
            if (cur["si"], cur["bi"]) in replaced or (cur["si"], cur["bi"]) in drop:
                continue
            # 护栏：模型只负责提名，删块前必须通过确定性复核（假设+结论双相似）
            ok, why = _equiv_ok(keep["key"], cur["key"])
            if not ok:
                skipped += 1
                print(f"  [numbering] 语义去重否决：{keep['id']} × {cur['id']}（{why}）")
                continue
            replaced[(cur["si"], cur["bi"])] = _MARK % (keep["si"], keep["bi"])
            k = cur["bi"] + 1
            while k < len(sec_blocks[cur["si"]]):
                h = sec_blocks[cur["si"]][k].split("\n", 1)[0].strip()
                mh = _BLOCK_HEAD.match(h)
                if not mh or not mh.group(1).strip().startswith("证明"):
                    break
                drop.add((cur["si"], k))
                k += 1
            kept_pairs.append((cur["id"], keep["id"]))
            merged += 1
        if kept_pairs:
            print(f"  [numbering] 语义去重：{'、'.join(a for a, _ in kept_pairs)} → 并入 {keep['id']}")

    if not merged:
        print("  [numbering] 语义去重：无可合并项")
        return sections
    for si, blocks in enumerate(sec_blocks):
        new = []
        for bi, b in enumerate(blocks):
            if (si, bi) in replaced:
                new.append(replaced[(si, bi)])
            elif (si, bi) in drop:
                continue
            else:
                new.append(b)
        sections[si]["body"] = "\n\n".join(x.strip("\n") for x in new)
    print(f"  [numbering] 语义去重：合并 {merged} 个重复定理（含其证明）"
          + (f"，否决 {skipped} 组" if skipped else ""))
    return sections


def _resolve_theorem_refs(sections):
    """编号完成后把占位标记解析为「（同上：见 §X 定理 Y）」。"""
    if not any(_MARK[:5] in sec["body"] for sec in sections):
        return sections
    blocks_cache = [_split_blocks(sec["body"]) for sec in sections]
    cnt = 0

    def repl(m):
        nonlocal cnt
        si, bi = int(m.group(1)), int(m.group(2))
        if si >= len(blocks_cache) or bi >= len(blocks_cache[si]):
            print("  [numbering] 警告：定理引用目标已不存在，降级为「（同上）」")
            return "（同上）"
        h = blocks_cache[si][bi].split("\n", 1)[0].strip()
        mh = _BLOCK_HEAD.match(h)
        mi = _DEDUP_ITEM_HEAD.match(mh.group(1).strip()) if mh else None
        if not mi:
            print("  [numbering] 警告：定理引用目标已非定理块，降级为「（同上）」")
            return "（同上）"
        cnt += 1
        return f"（同上：见 §{sections[si]['no']} {mi.group(1)} {mi.group(2)}）"

    for sec in sections:
        sec["body"] = re.sub(r"\x02THM:(\d+):(\d+)\x03", repl, sec["body"])
    if cnt:
        print(f"  [numbering] 解析定理交叉引用 {cnt} 处")
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
        body = check_proof_integrity(body)      # 假证完/跳步拦截（在合并前，结构还完整）
        body = merge_short_paragraphs(body)     # 短段防碎片化（在去重前，避免粘走占位段）
        sec["body"] = _cap_notes(body)

    _preprocess_items(sections)
    _dedupe_theorems_by_statement(sections)      # 编号前删重复定理，避免编号空洞
    semantic_dedupe_theorems(sections)           # 可选：LLM 语义去重（默认关闭）
    for sec in sections:
        sec["body"] = _number_section(sec["body"], sec["no"])
    _dedupe_items_by_content(sections)
    _resolve_theorem_refs(sections)
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
