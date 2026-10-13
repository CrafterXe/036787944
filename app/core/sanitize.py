"""数学记号后处理：把模型偶发输出的 LaTeX 残留清理为纯文本+Unicode。
作为 prompt 之外的兜底安全网。幂等（清理多次结果一致）。
"""
import re

# 简单 LaTeX 命令 → 纯文本/Unicode（不带参数的）
_CMD_MAP = {
    r"\theta": "θ", r"\pi": "π", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ",
    r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ", r"\omega": "ω", r"\Delta": "Δ",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\forall": "∀", r"\exists": "∃",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆", r"\cup": "∪",
    r"\cap": "∩", r"\emptyset": "∅", r"\pm": "±", r"\mp": "∓", r"\times": "×",
    r"\div": "÷", r"\cdot": "·", r"\circ": "∘", r"\le": "≤", r"\ge": "≥", r"\neq": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\sum": "Σ", r"\prod": "Π", r"\int": "∫",
    r"\sqrt": "√", r"\to": "→", r"\Rightarrow": "⇒", r"\Leftrightarrow": "⇔",
    r"\mathbb": "",  # 后接 {C} 等会被花括号规则处理
    r"\mathrm": "", r"\text": "", r"\operatorname": "",
}


def _replace_cmds(s):
    # 按长度降序替换，避免 \cos 被 \c 之类抢先（这里没有前缀冲突，但稳妥）
    for cmd in sorted(_CMD_MAP, key=len, reverse=True):
        s = s.replace(cmd, _CMD_MAP[cmd])
    return s


def sanitize_math(text):
    if "$" not in text and "\\" not in text and "_{" not in text and "^{" not in text:
        return text
    s = text
    # 1. 去掉 $ 和 $$（成对或单独）
    s = s.replace("$$", "").replace("$", "")
    # 2. \frac{a}{b} → (a)/(b)；\sqrt{x} → √(x)
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", s)
    # 3. 花括号包裹的单字母 \mathbb{C} → C（在去命令前先处理 \mathbb{X}）
    s = re.sub(r"\\(?:mathbb|mathrm|text)\s*\{([A-Za-z])\}", r"\1", s)
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
