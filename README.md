# 数学笔记整理助手 (Math Notes Assistant)

一个**完全本地运行**的数学课堂笔记整理工具。把课程材料（飞书妙记转写 txt、板书截图、老师发的 pdf/docx）丢进一个文件夹，它会自动完成：

```
读取归一 → 清洗口语废话 → 提取知识点话题 → 逐话题生成讲解 → 存成 Markdown 笔记
```

- **本地私有**：AI 模型与数据都在本机（Ollama），不联网也能跑，课堂内容不上传
- **先直觉后严格**：证明写全关键步骤，不跳步
- **纯文本数学符号**：不使用 LaTeX，公式用 Unicode 符号（∀ ∃ → ∫ Σ θ 等）
- **联网补全**：生成时可用必应搜索补充参考资料（失败自动降级，不影响生成）
- **Web 面板 + 项目管理**：Gradio 操作面板，支持按"项目"组织笔记与生成要求

## 界面预览

操作面板有两个标签页：
- **整理**：填输入文件夹 → ① 判断（清洗+提取话题）→ 可编辑话题 → ② 生成并写入 vault
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
4. 下载模型 `qwen3:8b`（文本）和 `qwen3-vl:8b`（图片 OCR）

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
   - 点 **① 判断** → 自动清洗并列出知识点话题
   - 可编辑话题 JSON
   - 点 **② 生成并写入 vault**
3. 笔记保存到 `app/vault/`（选了项目则存到对应项目子目录）

## 命令行用法（进阶）

```bash
cd app
python main.py process "<输入文件夹>"            # 全流程
python main.py process "<输入文件夹>" --project <项目folder_name>
python main.py judge "<输入文件夹>"              # 只清洗+提话题
python main.py run "<输入文件夹>"                # 用已有话题生成
```

## 项目结构

```
├─ install.py / install.bat   一键安装
├─ launcher.py / 启动.bat     一键启动
├─ app/
│   ├─ panel.py               Gradio 操作面板（主入口）
│   ├─ main.py                命令行入口
│   ├─ config.py              全局配置（模型、路径、超时等）
│   ├─ requirements.txt       Python 依赖
│   ├─ core/                  功能模块
│   │   ├─ ingest.py          多格式读取归一（txt/md/pdf/docx/图片OCR）
│   │   ├─ clean.py           清洗口语废话
│   │   ├─ chunk.py           分块
│   │   ├─ topics.py          提取话题+证据
│   │   ├─ search.py          联网搜索（必应，失败降级）
│   │   ├─ generate.py        逐话题生成+拼接
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
| qwen3-vl:8b | 图片 OCR（板书截图→文字） |
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

## 数据与隐私

- 项目档案在 `app/projects/`，生成的笔记在 `app/vault/`，均在你本机
- 除"联网补充资料"会访问搜索引擎外，其余处理全部本机完成，课堂原文不上传
