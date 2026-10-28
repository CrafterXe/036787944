# 数学笔记整理助手 (Math Notes Assistant)

> 当前版本：**v1.1.4**（2026-10-28）

一个**完全本地运行**的数学课堂笔记整理工具。把课程材料（飞书妙记转写 txt、板书截图、老师发的 pdf/docx）丢进一个文件夹，它会自动整理成**可读的讲义式 Markdown 笔记**：

```
读取归一 → 清洗口语废话 → 提取章节级话题（语义归一）→ 逐章生成讲解 → 编号/目录/去重 → 存成笔记
```

- **本地私有**：模型与数据都在本机（Ollama），不联网也能跑，课堂内容不上传
- **讲义式组织**：章节级划分，定义/定理/证明按讲授顺序排列，证明紧跟定理
- **自动排版**：`## §N` 章节编号、`### 定义 1.1` 条目编号、文件开头自动生成目录
- **有依据地讲**：只写材料里有的内容；材料中没有推导过程的定理只写"证明思路"，不编造证明
- **例题不编造**：只收录原文/课件中真实出现的例题
- **纯文本数学符号**：不使用 LaTeX，公式用 Unicode 符号（∀ ∃ → ∫ Σ θ 等）
- **联网补全**：生成时可用必应搜索补充参考资料（默认关闭，失败自动降级）
- **Web 面板 + 项目管理**：Gradio 操作面板，支持按"项目"组织笔记与生成要求
- **后处理护栏**：公式清洗、假证完拦截、短段防碎片化、定理级去重（详见下节）

## 文本后处理（v1.1.3 起定型）

生成之后的排版阶段是一条确定性流水线，四类问题各有一组护栏函数：

| 维度 | 关键实现 | 作用 |
|---|---|---|
| 公式清洗 | `sanitize.sanitize_math` | 去 LaTeX、裸词 `nmid → ∤`、符号归位（含转写丢反斜杠的情况） |
| 假证明拦截 | `numbering.check_proof_integrity` | 证明过短 → 降级为「证明思路」；跳步 → 追加「推导过程略」提示 |
| 防碎片化 | `numbering.merge_short_paragraphs`、`_cap_notes` | 纯文本短段并入前段；限制注/说明密度，不碰公式与列表 |
| 去重 | `_dedupe`、`_dedupe_items_by_content`、`_dedupe_theorems_by_statement` | 跨节段落、同名条目、定理陈述句（LCS ≥ 0.8 + 否定护栏）三层去重 |
| 编号 | `_number_section`、`_resolve_theorem_refs`、`_filter_bad_refs` | `§N` + 条目编号 + 目录；先删重复定理再编号，占位解析为「（同上：见 §X 定理 Y）」，不留编号空洞 |

处理顺序：

```
逐节：去自带 H1 / 重复标题 → _demote_inner_h2 → check_proof_integrity
      → merge_short_paragraphs → _cap_notes
全局：_preprocess_items → _dedupe_theorems_by_statement
      → semantic_dedupe_theorems（默认关闭）→ _number_section
      → _dedupe_items_by_content → _resolve_theorem_refs
      → _filter_bad_refs → _dedupe
```

`semantic_dedupe_theorems` 是**可选的**语义去重（额外一次 LLM 调用）：模型只负责提名等价分组，删块前还要通过确定性的假设/结论双重复核，任何一环失败都整轮跳过。默认关闭，仅作为处理极长废话转录时的备用选项。

## 生成的笔记长什么样

```markdown
# 行列式的定义与按行展开

> 课程：高等代数　日期：20261028　类型：课堂整理
> 来源：课堂转写自动整理（共 3 节）

---

## 目录

- §1　行列式的定义与按行展开
- §2　余子式与代数余子式
- §3　行列式的性质

---

## §1　行列式的定义与按行展开

### 定义 1.1（行列式）
……

### 定理 1.1（按第一行展开）
……

### 证明
……

### 注（为什么展开式里没有重复项）
……

## 方法小结
1. ……
```

## 界面预览

操作面板有两个标签页：
- **整理**：填输入文件夹 → ① 判断（清洗 + 提取章节话题）→ 可编辑话题 → ② 生成并写入 vault
- **项目管理**：建/改项目（名称、背景、结构、要求），项目的笔记单独归档

## 系统要求

- Windows 10/11、macOS 或 Linux（64 位）
- **Python 3.10+**
- **内存建议 16GB+**（模型运行时较吃内存）
- 磁盘：模型约 10GB（2 个模型）
- 有 NVIDIA 显卡（≥6GB 显存）最好，没有也能跑（慢一些）

## 安装（一键）

需要联网，自动装依赖 + 下载 AI 模型（约 10GB）。

**Windows**：双击 `install.bat`

**macOS / Linux**：
```bash
python3 install.py
```

脚本会依次：
1. 检查 Python 版本（≥3.10）
2. 安装 Python 依赖（gradio / requests / pdfplumber / python-docx）
3. 检查并安装 [Ollama](https://ollama.com)
4. 下载模型 `qwen3:8b`（文本）和 `qwen2.5vl:7b`（图片 OCR）
5. 打印 `ollama list`，确认两个模型都在

> Ollama 若刚装好，可能需重新运行一次脚本让 PATH 生效。

## 启动

**Windows**：双击 `启动.bat`

**macOS / Linux**：
```bash
python3 launcher.py
```

启动后浏览器自动打开面板：**http://127.0.0.1:14000/**

## 使用

1. 在 **项目管理** 标签页建一个项目（如"高等代数"，填背景/要求）
2. 切到 **整理** 标签页：
   - （可选）选择项目
   - 填**输入文件夹路径**（放飞书妙记 txt、板书截图 jpg/png、资料 pdf/docx）
   - 点 **① 判断** → 自动清洗并列出章节话题
   - 可编辑话题 JSON（`type` 填 `knowledge` 走知识笔记，填 `exercise` 走习题讲解）
   - 点 **② 生成并写入 vault**
3. 笔记保存到 `app/vault/`（选了项目则存到对应项目子目录）

## 命令行用法（进阶）

```bash
cd app
python main.py process "<输入文件夹>"            # 全流程
python main.py process "<输入文件夹>" --project <项目folder_name>
python main.py process "<输入文件夹>" --date 20261028
python main.py judge "<输入文件夹>"              # 只清洗 + 提话题
python main.py run "<输入文件夹>"                # 用已有话题生成
```

## 常改的配置（`app/config.py`）

| 参数 | 默认 | 作用 |
|---|---|---|
| `OLLAMA_HOST` | http://localhost:11434 | Ollama 服务地址 |
| `GEN_MODEL` | qwen3:8b | 生成用文本模型 |
| `VL_MODEL` | qwen2.5vl:7b | 图片 OCR 模型 |
| `CHUNK_MAX_CHARS` | 6000 | 分块长度 |
| `TOPIC_MIN` / `TOPIC_MAX` | 6 / 12 | 一次处理期望的章节数（软引导） |
| `TOPIC_MERGE_MIN` | 3 | 话题数达到该值即做语义归一 |
| `TOPIC_SPLIT_MIN` | 2 | 章节数硬下限，低于则拆回 |
| `PROOF_WINDOW_MAX` | 1200 | 定理证明检测窗口（字） |
| `ITEM_DEDUP_THRESHOLD` | 0.7 | 跨节条目正文相似度阈值 |
| `SECTION_SPLIT_CHARS` | 5000 | 单章过长拆分阈值 |
| `GEN_MAX_TOKENS` | 4000 | 单节生成 token 上限 |
| `ENABLE_WEB_SEARCH` | False | 是否联网补充资料 |
| `ENABLE_SEMANTIC_DEDUPE` | False | 定理语义去重（额外一次 LLM 调用，备用） |

## 项目结构

```
├─ install.py / install.bat   一键安装
├─ launcher.py / 启动.bat     一键启动
├─ app/
│   ├─ panel.py               Gradio 操作面板（主入口）
│   ├─ main.py                命令行入口
│   ├─ config.py              全局配置（模型、路径、粒度、容量等）
│   ├─ requirements.txt       Python 依赖
│   ├─ core/                  功能模块
│   │   ├─ ingest.py          多格式读取归一（txt/md/pdf/docx/图片OCR）
│   │   ├─ clean.py           清洗口语废话
│   │   ├─ chunk.py           分块
│   │   ├─ topics.py          提取章节话题 + 语义归一 + 证据
│   │   ├─ search.py          联网搜索（必应，失败降级）
│   │   ├─ generate.py        逐章生成（含证明门控）+ 拼接
│   │   ├─ numbering.py       编号 / 目录 / 跨节去重 / 过长拆分
│   │   ├─ sanitize.py        数学符号规范化（去 LaTeX）
│   │   ├─ project.py         项目管理
│   │   ├─ vault.py           写库归档
│   │   └─ ollama_client.py   Ollama 调用封装
│   ├─ prompts/               提示词模板
│   ├─ projects/              【你的项目档案】
│   └─ vault/                 【生成的笔记】
```

## 技术组成

| 组件 | 说明 |
|------|------|
| Gradio | Web 操作面板 |
| Ollama | 本地大模型推理服务 |
| qwen3:8b | 文本清洗 / 提话题 / 生成 |
| qwen2.5vl:7b | 图片 OCR（板书截图→文字） |
| pdfplumber / python-docx | PDF / Word 解析 |

## 常见问题

**Q: 启动时提示"依赖未装全"？**
先运行一次 `install.bat` / `python3 install.py`。

**Q: Ollama 装好后脚本找不到？**
关闭终端重新打开（让 PATH 生效），再运行。

**Q: 模型下载慢？**
`ollama pull` 需联网，网速慢时耐心等；也可稍后手动 `ollama pull qwen3:8b`。

**Q: 生成很慢？**
首次需加载模型（几十秒），之后常驻内存会快。无独显会更慢。

**Q: 一章内容太少 / 章节数偏少？**
合并偏激进时可下调 `TOPIC_MERGE_MIN` 或上调 `TOPIC_MIN`，让提取阶段多留几章。

**Q: 笔记里出现公式乱码？**
本项目不使用 LaTeX，`sanitize.py` 会把残留的 LaTeX 命令转为 Unicode 符号；若仍有个别符号异常，可反馈具体片段。

## 数据与隐私

- 项目档案在 `app/projects/`，生成的笔记在 `app/vault/`，均在你本机
- 除"联网补充资料"（需手动开启）会访问搜索引擎外，其余处理全部本机完成，课堂原文不上传
