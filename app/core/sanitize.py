"""数学记号后处理：把模型偶发输出的 LaTeX 残留清理为纯文本+Unicode，并把中文量词替换为符号。
作为 prompt 之外的兜底安全网。幂等（清理多次结果一致）。
"""
import re

# 简单 LaTeX 命令 → 纯文本/Unicode（不带参数的）
_CMD_MAP = {
    # 希腊字母
    r"\theta": "θ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\iota": "ι",
    r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ",
    r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ",
    r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ", r"\Xi": "Ξ",
    r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    # 函数与算子
    r"\sin": "sin", r"\cos": "cos", r"\tan": "tan", r"\cot": "cot", r"\sec": "sec", r"\csc": "csc",
    r"\lim": "lim", r"\ln": "ln", r"\log": "log", r"\exp": "exp", r"\max": "max", r"\min": "min",
    r"\sup": "sup", r"\inf": "inf", r"\det": "det", r"\dim": "dim", r"\ker": "ker", r"\deg": "deg",
    # 符号
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\forall": "∀", r"\exists": "∃",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆", r"\supset": "⊃",
    r"\supseteq": "⊇", r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅", r"\pm": "±", r"\mp": "∓",
    r"\times": "×", r"\div": "÷", r"\cdot": "·", r"\circ": "∘", r"\bullet": "•",
    r"\le": "≤", r"\leq": "≤", r"\ge": "≥", r"\geq": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\sim": "∼", r"\propto": "∝", r"\parallel": "∥",
    r"\perp": "⊥", r"\angle": "∠", r"\sum": "Σ", r"\prod": "Π", r"\int": "∫",
    r"\sqrt": "√", r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔",
    r"\mapsto": "↦", r"\uparrow": "↑", r"\downarrow": "↓",
    r"\mid": "|", r"\cdots": "⋯", r"\ldots": "…", r"\dots": "…", r"\vdots": "⋮", r"\ddots": "⋱",
    # 左右定界符
    r"\left": "", r"\right": "",
    r"\mathbb": "",  # 后接 {C} 等会被花括号规则处理
    r"\mathrm": "", r"\text": "", r"\operatorname": "", r"\quad": "  ", r"\qquad": "    ",
}


def _replace_cmds(s):
    # 按长度降序替换，避免 \cos 被 \c 之类抢先（这里没有前缀冲突，但稳妥）
    for cmd in sorted(_CMD_MAP, key=len, reverse=True):
        s = s.replace(cmd, _CMD_MAP[cmd])
    return s


def sanitize_math(text):
    s = text
    # 0. 转写丢反斜杠后的裸词 nmid → ∤（裸词不含 LaTeX 标记，须在提前返回之前处理）
    s = re.sub(r"(?<![A-Za-z])nmid(?![A-Za-z])", "∤", s)
    # 0.1 中文量词 → 符号（提前执行，因为输入可能不含 LaTeX 标记）
    s = re.sub(r"任意\s*([εδθλμπσφωαβγζηικνξρτυχψω])", r"∀\1", s)
    s = re.sub(r"存在\s*([εδθλμπσφωαβγζηικνξρτυχψω])", r"∃\1", s)
    s = re.sub(r"任意\s+([>≤≥=<|∀∃Σ∫√·])", r"∀\1", s)
    s = re.sub(r"存在\s+([>≤≥=<|∀∃Σ∫√·])", r"∃\1", s)
    s = re.sub(r"对于任意\s*([εδθλμπσφωαβγ])", r"∀\1", s)
    s = re.sub(r"对任意\s*([a-zA-Zεδθλμπσφωαβγ])", r"∀\1", s)
    s = re.sub(r"任意([a-zA-Z])", r"∀\1", s)
    s = re.sub(r"任意\s+([a-zA-Z])", r"∀\1", s)
    s = re.sub(r"存在\s*([nNxXa-zA-Z0-9])", r"∃\1", s)
    s = re.sub(r"(?:对任意|任意)(?:正整数|实数|整数|有理数|自然数|正数|常数)?\s*([a-zA-Z])", r"∀\1", s)
    s = re.sub(r"存在(?:正整数|实数|整数|有理数|自然数|正数|常数)?\s*([a-zA-Z])", r"∃\1", s)
    # 提前返回：无 LaTeX 标记时
    if "$" not in s and "\\" not in s and "_{" not in s and "^{" not in s:
        return s
    # 1. 去掉 $、$$、\[ \]、\( \)
    s = s.replace("$$", "").replace("$", "")
    s = s.replace(r"\[", "").replace(r"\]", "").replace(r"\(", "").replace(r"\)", "")
    # 2. 矩阵环境残留：\begin{vmatrix} … \end{vmatrix} → 方括号
    s = re.sub(r"\\?begin\s*\{(?:vmatrix|matrix|pmatrix|bmatrix|Vmatrix|array)\}", "[", s)
    s = re.sub(r"\\?end\s*\{(?:vmatrix|matrix|pmatrix|bmatrix|Vmatrix|array)\}", "]", s)
    s = re.sub(r"\\?begin\s*\{[^{}]*\}", "", s)
    s = re.sub(r"\\?end\s*\{[^{}]*\}", "", s)
    # 3. 递归处理嵌套 \frac{a}{b} → (a)/(b)；\sqrt[n]{x} → √[n](x)；\sqrt{x} → √(x)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", s)
        s = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}", r"√[\1](\2)", s)
        s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", s)
    # 3. \mathbb{R} / \mathbf{x} / \mathrm{d} 等花括号单内容 → 直接取内容
    s = re.sub(r"\\(?:mathbb|mathrm|mathbf|text|operatorname)\s*\{([^{}]*)\}", r"\1", s)
    # 4. 下标上标花括号：x_{n+1} → x_(n+1)；x^{2} → x^(2)
    s = re.sub(r"_\{([^{}]*)\}", r"_(\1)", s)
    s = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", s)
    # 5. 简单命令替换
    s = _replace_cmds(s)
    # 6. 去掉残留的反斜杠
    s = s.replace("\\", "")
    return s


if __name__ == "__main__":
    import sys
    f = sys.argv[1]
    t = open(f, encoding="utf-8").read()
    out = sanitize_math(t)
    n1 = t.count("$") + len(re.findall(r"\\[a-zA-Z]+", t))
    n2 = out.count("$") + len(re.findall(r"\\[a-zA-Z]+", out))
    print(f"清理前残留标记: {n1}, 清理后: {n2}")
    open(f, "w", encoding="utf-8").write(out)
    print("已写回", f)
