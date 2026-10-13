"""长文分块：按字符切块，相邻重叠，避免上下文超限。"""
import config


def chunk_text(text, max_chars=None, overlap=None):
    max_chars = max_chars or config.CHUNK_MAX_CHARS
    overlap = overlap or config.CHUNK_OVERLAP
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        # 尽量在句号/换行处断开，避免切在句子中间
        if end < n:
            cut = text.rfind("\n", start, end)
            if cut == -1 or cut <= start:
                cut = text.rfind("。", start, end)
            if cut > start + max_chars // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c.strip()]
