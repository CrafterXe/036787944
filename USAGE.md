# 数学知识整理助手 — 使用教程

> 版本：v1.1.1  ↩
> 更新日期：2026-10-26  ↩
> 适用于：Windows 10/11、macOS、Linux（64 位）

---

## 一、这是什么

一个完全本地运行的**数学课堂笔记整理助手**。把课程材料（飞书妙记转写 txt、板书截图、老师发的 pdf/docx）放进一个文件夹，它会自动：

```
读取 → 清洗口语废话 → 提取知识点话题 → 逐话题生成讲解 → 存成 Markdown 笔记
```

笔记风格：教材体（定义→定理→证明→注）、证明写全关键步骤、数学公式用纯文本+Unicode 符号（不使用 LaTeX）。生成时可联网补充参考资料（失败自动降级）。

**本地私有**：AI 模型与数据都在本机，不联网也能跑，课堂内容不上传。

---

## 二、环境要求

| 项      | 最低要求                                 | 推荐                       |
| ------ | ------------------------------------ | ------------------------ |
| 操作系统   | Windows 10 / macOS 11 / Ubuntu 20.04 | Windows 11               |
| Python | 3.10                                 | 3.12+                    |
| Ollama | 0.40.3                               | 0.40.3+                  |
| 内存     | 8 GB                                 | 16 GB+                   |
| 磁盘     | 模型约 10 GB + 依赖 1 GB                  | 留 25 GB+                 |
| 显卡     | 无（纯 CPU 能跑但慢）                        | NVIDIA ≥ 6 GB 显存（GPU 加速） |
| 安装时    | 需联网下载模型                              | 日常使用可离线                  |

---

## 三、安装

### 方式一：一键安装（Windows 推荐）

1. **装好 Python 3.10+**

   - 下载：<https://www.python.org/downloads/>
   - 安装时**务必勾选 "Add Python to PATH"**

2. **双击 `install.bat`**

   - 自动装 Python 依赖（约 1 GB）
   - 自动下载 Ollama 程序
   - 自动拉取 2 个模型（qwen3:8b 约 5 GB、qwen2.5vl:7b 约 5 GB）
   - 全程需联网，耐心等待

3. **装完后双击 `启动.bat`** → 浏览器自动打开面板

### 方式二：手动安装

```bash
# 1. 安装 Python 依赖
pip install -r app/requirements.txt

# 2. 安装 Ollama（如未装）
#    Windows：https://ollama.com/download
#    macOS/Linux：https://ollama.com/download

# 3. 拉取模型
ollama pull qwen3:8b
ollama pull qwen2.5vl:7b
```

### 方式三：macOS / Linux

```bash
python3 install.py     # 一键安装
python3 launcher.py    # 启动面板
```

> 刚装好 Ollama 后脚本提示找不到？**关闭终端重新打开**（让 PATH 生效），再运行。

---

## 四、目录结构

```
项目根目录/
├─ install.py / install.bat       ← 一键安装（首次运行）
├─ launcher.py / 启动.bat         ← 一键启动（日常使用）
├─ README.md                       ← GitHub 项目说明
├─ USAGE.md                        ← 本文件
├─ 发布说明.md                     ← 版本更新记录
└─ app/
    ├─ panel.py                    Web 操作面板（主入口）
    ├─ main.py                     命令行入口
    ├─ config.py                   全局配置（可调参数见第六节）
    ├─ requirements.txt            Python 依赖清单
    ├─ core/                       各功能模块
    │   ├─ ingest.py               多格式读取 + OCR
    │   ├─ clean.py                口语废话清洗
    │   ├─ chunk.py                分块
    │   ├─ topics.py               话题提取 + 去重
    │   ├─ generate.py             逐话题生成（两条路径）
    │   ├─ sanitize.py             LaTeX → Unicode + 量词替换
    │   ├─ ollama_client.py        统一 Ollama HTTP 客户端
    │   ├─ search.py               必应联网搜索
    │   ├─ project.py              项目管理
    │   └─ vault.py                笔记写库
    ├─ prompts/                    提示词模板
    │   ├─ system.txt              教材体风格总约束
    │   ├─ generate.txt            知识笔记模板
    │   ├─ exercise.txt            习题讲解模板
    │   ├─ topics.txt              话题提取提示
    │   └─ clean.txt               清洗提示
    ├─ inbox/                      ← 输入文件夹（把材料放这）
    ├─ projects/                   ← 【你的项目档案】自动建在这
    └─ vault/                      ← 【生成笔记的存放处】
```

---

## 五、两种使用方式

### 方式一：Web 面板（推荐）

启动后浏览器自动打开 `http://127.0.0.1:14000/`，两个 Tab：

#### Tab 1：项目管理（可选但推荐）

先建一个项目，后续整理笔记时选中它，笔记会自动归档到独立文件夹，并带上项目背景。

#### Tab 2：整理

1. **顶部下拉选项目**（可选）
2. **「输入文件夹路径」填要整理的文件夹**（放 txt / jpg / pdf / docx，支持多层子目录）
3. **点「① 判断」** → 自动清洗材料并列出知识点话题（含重要度分级、证据）
4. **可编辑话题 JSON**（增删/改重要度/改 type），然后点 **「② 生成并写入 vault」**
5. 右侧显示笔记预览和保存路径

> 话题 `type` 说明：`knowledge`（知识笔记，教材体）/ `exercise`（习题讲解，直给解）

### 方式二：命令行

```bash
cd app

# 全流程：读取 → 判断 → 生成 → 写库
python main.py process "D:\我的材料\20261012数分\输入"

# 带项目
python main.py process "D:\我的材料\20261012数分\输入" --project 高等代数_2026秋季

# 只跑判断（清洗+提话题）
python main.py judge "D:\我的材料\20261012数分\输入"

# 跳过判断，直接用已有话题生成
python main.py run "D:\我的材料\20261012数分\输入" --topics topics.json
```

---

## 六、配置微调

编辑 `app/config.py`，常用参数：

```python
# === 模型 ===
CLEAN_MODEL   = "qwen3:8b"         # 文本清洗
TOPIC_MODEL   = "qwen3:8b"         # 话题提取
GEN_MODEL     = "qwen3:8b"         # 逐话题生成（主用）
SUMMARY_MODEL = "qwen3:8b"         # 总结
VL_MODEL      = "qwen2.5vl:7b"     # 图片 OCR 模型
OCR_MAX_SIDE  = 1600               # OCR 前自动缩图最长边
OCR_JPEG_QUALITY = 85              # 缩图 JPEG 质量

# === 功能开关 ===
ENABLE_WEB_SEARCH = False          # 联网补充资料（默认关）

# === 生成风格 ===
GEN_STRUCTURE = ["定义", "定理", "证明", "注"]  # 板块顺序
GEN_PROOF_END = "证完"             # 证明结尾标记（或 "∎" / ""）
GEN_NUMBERING = "2.1"              # 编号格式（节.序号）
GEN_TONE      = "mixed"            # 语气：narrative / declarative / mixed
GEN_FORMULA   = "inline"           # 公式：inline / centered
GEN_NOTE      = "auto"             # 注的生成：auto / always / off
GEN_EXERCISE_MODE = "solution_first"  # 习题讲解：直给式
GEN_EXERCISE_NOTE = "auto"         # 习题讲解的注：auto / always / off

# === 护栏 ===
CLEAN_MIN_RATIO = 0.60             # 清洗后长度低于原文此比例则回退原文
GEN_RETRY = 3                      # 单话题生成失败重试次数

# === 路径（默认基于 __file__，可移植）===
ROOT          = Path(__file__).resolve().parent   # 即 app/ 目录
VAULT_DIR     = ROOT / "vault"
PROJECTS_DIR  = ROOT / "projects"
```

---

## 七、输入材料要求

| 格式              | 说明                                       |
| --------------- | ---------------------------------------- |
| `.txt` / `.md`  | 直接读取，最稳定                                 |
| `.pdf`          | pdfplumber 解析，尽量选"可复制文字"的 PDF（扫描版效果差）    |
| `.docx`         | python-docx 解析                           |
| `.jpg` / `.png` | OCR（qwen2.5vl:7b），建议：板书照片尽量清晰，最长边 ≤ 2048 |

**建议**：把不同课程材料分文件夹放，例如：

```
D:\我的材料\
├─ 20261012数分\输入\     ← 数分课材料
└─ 20261013高代\输入\     ← 高代课材料
```

直接选父目录 `20261012数分` 也能用——如果当前层没文件，会自动下钻子目录 `输入`。

---

## 八、输出在哪里

| 情况   | 输出路径                |
| ---- | ------------------- |
| 未选项目 | `app/vault/.md`     |
| 选了项目 | `app/vault/项目./.md` |

文件命名规则：`YYYYMMDD_课程_话题名.md`，自动生成。

---

## 九、常见问题

**Q1. 启动提示"依赖未装全 / 未安装 Ollama"？**  
→ 先运行 `install.bat`（或 `python3 install.py`）。

**Q2. Ollama 刚装好，脚本却提示找不到？**  
→ 关闭终端/窗口重新打开（让 PATH 生效），再运行。

**Q3. 模型下载慢或失败？**  
→ `ollama pull` 需联网。可手动执行：

```bash
ollama pull qwen3:8b
ollama pull qwen2.5vl:7b
```

**Q4. 生成很慢？**  
→ 首次需加载模型（约几十秒），之后常驻内存会快。无独显会更慢（CPU 约 5–15 tok/s，GPU 约 40–60 tok/s）。

**Q5. 端口 14000 被占用？**  
→ 说明面板已在运行，直接开 `http://127.0.0.1:14000/` 即可。

**Q6. 如何停止？**  
→ 关闭"面板"窗口即可；Ollama 服务在后台常驻，重启电脑后停止。

**Q7. 笔记里出现 LaTeX？**  
→ 正常会被 sanitize 自动清除并转 Unicode。如果还有残留，可能是极端写法，反馈给开发者。

**Q8. 笔记里出现"任意/存在"而不是 ∀∃？**  
→ sanitize 有严格边界：只当后面紧跟变量/符号时才替换。中文量词如"任意性""存在唯一"不动是正确行为。

**Q9. 换一台电脑怎么用？**  
→ 源码版：重新跑 `install.bat`（联网下载模型）。
→ 便携版：整个文件夹复制过去，双击启动.bat 即可（无需安装）。

---

## 十、数据与隐私

- 项目档案在 `app/projects/`，生成的笔记在 `app/vault/`。
- 除"联网补充资料"会访问必应外，其余处理**全部本机完成**，课堂原文不上传任何服务器。
- 即使开启联网搜索，也只发送**话题名**到搜索引擎，不发送材料原文。

---

## 十一、技术组成

| 组件           | 版本      | 作用          |
| ------------ | ------- | ----------- |
| Python       | 3.10+   | 运行时         |
| Gradio       | 6.x     | Web 操作面板    |
| Ollama       | 0.40.3+ | 本地大模型推理     |
| qwen3:8b     | —       | 文本生成（教材体笔记） |
| qwen2.5vl:7b | —       | 图片 OCR      |
| pdfplumber   | —       | PDF 解析      |
| python-docx  | —       | Word 解析     |
| requests     | —       | HTTP + 必应搜索 |

---

## 十二、升级指南

当发布新版本时：

```bash
# 1. 备份你的 app/vault/ 和 app/projects/
# 2. 用新版本的 app/ 覆盖旧的（不要覆盖 vault/ 和 projects/）
# 3. 运行 install.bat 确认依赖和模型是最新的
# 4. 启动使用
```

或直接在 git 仓库里 pull + rebase：

```bash
git pull origin main --rebase
```

---

## 十三、故障排查速查

| 症状                          | 先查这个                                        |
| --------------------------- | ------------------------------------------- |
| 启动面板报端口占用                   | 面板已开，直接访问 http://127.0.0.1:14000/           |
| Ollama 报 connection refused | `ollama serve` 是否在后台运行？模型目录是否对？             |
| 话题提取 0 话题                   | 输入文件夹里是否有可处理的文件？是否在子目录？                     |
| OCR 返回空                     | 换用 qwen2.5vl:7b（config.py 已默认），或手动缩图        |
| 生成只有几句话                     | 材料内容太短？或 topics.py 提取失败，看日志                 |
| 笔记有 LaTeX                   | 看 sanitize.py 是否需要补充新规则                     |
| 笔记像科普                       | system.txt 约束被模型绕过？看 prompt                 |
| 内存爆满                        | 物理内存偏小（15GB），关闭其他程序；或换更小模型                  |
| CPU 低、GPU 显示 0%             | RTX 50 系 + Ollama 0.40.3 以下驱动追踪不准，升级 Ollama |
