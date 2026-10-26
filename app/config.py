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
# 注：qwen3-vl:8b 强制思考会耗尽 token 致 OCR 超时/返回空，实测 qwen2.5vl:7b 更快更稳
VL_MODEL = "qwen2.5vl:7b"    # 图片 OCR（板书截图→文字）
CLEAN_MODEL = "qwen3:8b"     # 文本清洗
TOPIC_MODEL = "qwen3:8b"     # 话题提取
GEN_MODEL = "qwen3:8b"       # 逐话题生成（主用）
SUMMARY_MODEL = "qwen3:8b"   # 总结

# OCR：发送前把图片缩放到最长边不超过该值（大图原始 10MB+ 易超时），JPEG 质量
OCR_MAX_SIDE = 1600
OCR_JPEG_QUALITY = 85

# 超时（秒）
CHAT_TIMEOUT = 300        # 普通对话
GEN_TIMEOUT = 900         # 生成（可能较慢，给长超时）
OCR_TIMEOUT = 300

# 分块
CHUNK_MAX_CHARS = 6000
CHUNK_OVERLAP = 500

# 清洗护栏：清洗后长度低于原文此比例 → 判定被总结 → 回退原文
CLEAN_MIN_RATIO = 0.60

# 联网搜索：默认关闭（泛化搜索结果会把生成拉向科普腔）；需要时改 True
ENABLE_WEB_SEARCH = False
SEARCH_MAX_RESULTS = 6
SEARCH_TIMEOUT = 25

# 生成重试：单话题返回空时重试次数
GEN_RETRY = 3

# ---- 生成风格参数（参数化，便于后续调风格而不重写提示词）----
# 知识笔记结构板块（顺序即生成顺序，可增删）
GEN_STRUCTURE = ["定义", "定理", "证明", "注"]
# 证明结尾标记："证完" / "∎" / ""（不写）
GEN_PROOF_END = "证完"
# 编号格式："2.1" / "2.1.1" / ""（不编号）
GEN_NUMBERING = "2.1"
# 语气："mixed"（命题+叙述）/ "narrative"（叙述式）/ "declarative"（命题式）
GEN_TONE = "mixed"
# 公式排版："inline"（随文）/ "centered"（居中编号）
GEN_FORMULA = "inline"
# 习题讲解模式："solution_first"（直给式，默认）
GEN_EXERCISE_MODE = "solution_first"
# 注（知识笔记）："auto"（模型自主判断）/ "off" / "always"
GEN_NOTE = "auto"
# 注（习题讲解）："auto" / "off" / "always"
GEN_EXERCISE_NOTE = "auto"

# 输出文件命名日期格式：YYYYMMDD
DATE_FMT = "%Y%m%d"

for _d in (VAULT_DIR, INBOX_DIR, PROJECTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
