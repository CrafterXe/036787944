"""全局配置。所有路径基于项目根目录动态计算，保证可移植。"""
from pathlib import Path

# 项目根目录：本文件所在目录（math-notes/）
ROOT = Path(__file__).resolve().parent

# 目录（全部相对 ROOT）
VAULT_DIR = ROOT / "vault"        # 笔记落盘处
INBOX_DIR = ROOT / "inbox"        # 每次处理的临时工作目录
PROMPT_DIR = ROOT / "prompts"     # 提示词模板
PROJECTS_DIR = ROOT / "projects"  # 项目档案（每个项目一个子文件夹，内含 project.json）

# 本地 Ollama 服务
OLLAMA_HOST = "http://localhost:11434"

# 模型（按需在 Ollama 里 pull 对应模型）
VL_MODEL = "qwen3-vl:8b"       # 图片 OCR（板书截图→文字）
CLEAN_MODEL = "qwen3:8b"       # 文本清洗
TOPIC_MODEL = "qwen3:8b"       # 话题提取
GEN_MODEL = "qwen3:8b"         # 逐话题生成（主用）
SUMMARY_MODEL = "qwen3:8b"     # 总结

# 超时（秒）
CHAT_TIMEOUT = 300        # 普通对话
GEN_TIMEOUT = 900         # 生成（可能较慢，给长超时）
OCR_TIMEOUT = 300

# 分块
CHUNK_MAX_CHARS = 6000
CHUNK_OVERLAP = 500

# 清洗护栏：清洗后长度低于原文此比例 → 判定被总结 → 回退原文
CLEAN_MIN_RATIO = 0.60

# 联网搜索：是否启用（失败自动降级，不影响生成）
ENABLE_WEB_SEARCH = True
SEARCH_MAX_RESULTS = 6
SEARCH_TIMEOUT = 25

# 生成重试：单话题返回空时重试次数
GEN_RETRY = 3

# 输出文件命名日期格式：YYYYMMDD
DATE_FMT = "%Y%m%d"

for _d in (VAULT_DIR, INBOX_DIR, PROJECTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
