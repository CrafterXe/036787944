"""多格式输入归一为纯文本：txt/md/pdf/docx/图片(OCR)。"""
from pathlib import Path
from . import ollama_client
import config

TEXT_EXTS = {".txt", ".md"}


def read_plain(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return Path(path).read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def pdf_to_text(path):
    try:
        import pdfplumber
    except ImportError:
        return "[缺少 pdfplumber，无法解析 PDF，请 pip install pdfplumber]"
    parts = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            parts.append(f"\n--- 第{i}页 ---\n{t}")
    return "\n".join(parts)


def docx_to_text(path):
    try:
        import docx
    except ImportError:
        return "[缺少 python-docx，无法解析 docx，请 pip install python-docx]"
    d = docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs)


def ocr_images(image_paths):
    """板书截图 → 文字。一次最多送 3 张，多批处理。"""
    if not image_paths:
        return ""
    prompt = ("请把这些板书/教材图片中的全部文字内容转写出来，"
              "保留数学公式（用纯文本+Unicode符号，不要LaTeX），按页面顺序输出。"
              "只输出文字，不要解释。")
    out = []
    batch = 3
    for i in range(0, len(image_paths), batch):
        chunk = image_paths[i:i + batch]
        res = ollama_client.chat_with_images(config.VL_MODEL, prompt, chunk)
        if res:
            out.append(res)
    return "\n\n".join(out)


def ingest_folder(folder):
    """读取一个输入文件夹下所有材料，拼接成一份纯文本。返回 (text, meta)。"""
    folder = Path(folder)
    texts = []
    images = []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if p.name in ("提示词.txt",):
            continue
        if ext in TEXT_EXTS:
            texts.append(f"### 文件 {p.name}\n" + read_plain(p))
        elif ext == ".pdf":
            texts.append(f"### 文件 {p.name}\n" + pdf_to_text(p))
        elif ext == ".docx":
            texts.append(f"### 文件 {p.name}\n" + docx_to_text(p))
        elif ext in (".jpg", ".jpeg", ".png", ".webp"):
            images.append(p)
    if images:
        print(f"  [OCR] 处理 {len(images)} 张图片...")
        ocr = ocr_images(images)
        if ocr:
            texts.append("### 图片 OCR 内容\n" + ocr)
    return "\n\n".join(texts)
