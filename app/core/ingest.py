"""多格式输入归一为纯文本：txt/md/pdf/docx/图片(OCR)。"""
import os
import tempfile
from pathlib import Path
from . import ollama_client, sanitize
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


def _prepare_image(path):
    """把图片缩放到最长边 OCR_MAX_SIDE、转 JPEG，写入临时文件并返回路径。
    大图原始 10MB+ 会让 OCR 超时/返回空；缩放后识别质量不降且更快。
    失败或 PIL 缺失时返回原路径。"""
    try:
        from PIL import Image
    except ImportError:
        return str(path)
    try:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        m = config.OCR_MAX_SIDE
        if max(w, h) > m:
            im.thumbnail((m, m))
        tmp = os.path.join(tempfile.gettempdir(), f"mn_ocr_{Path(path).stem}.jpg")
        im.save(tmp, "JPEG", quality=config.OCR_JPEG_QUALITY)
        return tmp
    except Exception as e:
        print(f"  [image resize skip] {path}: {e}")
        return str(path)


def ocr_images(image_paths):
    """板书截图 → 文字。一次只送 1 张（避免多张+思考耗尽 token），逐张处理。"""
    if not image_paths:
        return ""
    prompt = ("请把这张板书/教材图片中的全部文字内容转写出来，"
              "保留数学公式（用纯文本+Unicode符号，不要LaTeX）。"
              "只输出文字，不要解释。")
    out = []
    opts = {"num_ctx": 8192, "num_predict": 2048}
    for p in image_paths:
        tmp = _prepare_image(p)
        res = ollama_client.chat_with_images(config.VL_MODEL, prompt, [tmp], options=opts)
        if res:
            out.append(sanitize.sanitize_math(res))
    return "\n\n".join(out)


def ingest_folder(folder):
    """读取一个输入文件夹下所有材料，拼接成一份纯文本。
    若当前目录没有可处理文件，自动下钻子目录“输入”（用户常选到父目录）。"""
    folder = Path(folder)
    # 自动下钻：若当前目录没有任何 txt/md/pdf/docx/图片，优先用子目录“输入”
    has_direct = any(
        p.is_file() and p.suffix.lower() in TEXT_EXTS | {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
        for p in folder.iterdir()
    ) if folder.is_dir() else False
    if not has_direct:
        for sub in sorted(folder.iterdir()) if folder.is_dir() else []:
            if sub.is_dir() and sub.name == "输入":
                print(f"  [ingest] 当前目录无材料，自动下钻到子目录：{sub}")
                folder = sub
                break
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
