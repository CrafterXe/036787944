"""数学笔记整理 · CLI 入口。

用法：
  python main.py process <输入文件夹>          全流程：清洗→提话题→(确认)→生成→写库
  python main.py judge <输入文件夹>            只做判断（清洗+提话题），不生成不写库
  python main.py run <输入文件夹>              用已有 _topics.json/_cleaned.txt 直接生成写库

可选 --project <项目folder_name>：使用项目的背景/要求生成，并归档到项目目录。

输入文件夹内放：飞书妙计 txt、板书截图 jpg、老师资料 pdf/docx。
无项目时输出存 vault/，文件名 YYYYMMDD_课程_主题.md；有项目时存 vault/<项目归档>/。
"""
import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

import config
from core import ingest, clean, chunk, topics as topics_mod, generate, vault
from core import project as proj_mod
from core import logsetup

_log = logging.getLogger("app.flow")


def load_input(folder):
    folder = Path(folder)
    if not folder.is_dir():
        _log.error("输入文件夹不存在: %s", folder)
        sys.exit(1)
    _log.info("[1/4] 读取并归一化材料: %s", folder)
    text = ingest.ingest_folder(folder)
    if not text.strip():
        _log.error("未读取到任何文本内容。")
        sys.exit(1)
    _log.info("共 %d 字。", len(text))
    return text


def _load_project_or_exit(name):
    if not name:
        return None
    p = proj_mod.load_project(name)
    if not p:
        _log.error("项目不存在: %s（可用项目见 projects/ 目录）", name)
        sys.exit(1)
    _log.info("[项目] %s（归档：%s）", p.get('name'), p.get('vault_folder'))
    return p


def do_judge(folder, project=None):
    text = load_input(folder)
    _log.info("[2/4] 分块...")
    chunks = chunk.chunk_text(text)
    _log.info("分成 %d 块。", len(chunks))
    _log.info("[3/4] 清洗（去除口语废话，保留全部知识）...")
    cleaned = clean.clean_text(chunks)
    full = "\n\n".join(cleaned)
    _log.info("[4/4] 提取话题...")
    tops = topics_mod.propose_topics(cleaned, full, project)
    return full, tops


def show_topics(tops):
    print("\n========== 提取到的话题 ==========")
    for i, t in enumerate(tops, 1):
        print(f"  {i}. [{t.get('importance','?')}] {t['name']}")
        print(f"     {t.get('summary','')}")
    print("==================================\n")


def confirm_topics(tops):
    """CLI 确认/编辑话题。返回最终话题列表。"""
    while True:
        show_topics(tops)
        cmd = input("确认话题？回车=全部确认；输入编号删除（如 2,5）；a=新增；q=退出: ").strip()
        if cmd == "" or cmd.lower() == "y":
            return tops
        if cmd.lower() == "q":
            print("已取消。")
            sys.exit(0)
        if cmd.lower() == "a":
            name = input("新话题名: ").strip()
            if name:
                imp = input("重要度(核心/重要/了解，默认重要): ").strip() or "重要"
                tops.append({"name": name, "summary": "用户新增", "importance": imp, "evidence": ""})
            continue
        # 删除编号
        try:
            idxs = sorted({int(x) for x in cmd.replace("，", ",").split(",") if x.strip()}, reverse=True)
            for idx in idxs:
                if 1 <= idx <= len(tops):
                    print(f"  删除: {tops[idx-1]['name']}")
                    tops.pop(idx - 1)
        except ValueError:
            print("  输入无效，请重新输入。")


def cmd_process(args):
    try:
        project = _load_project_or_exit(args.project)
        full, tops = do_judge(args.folder, project)
        if not tops:
            _log.error("未提取到任何话题，终止。")
            sys.exit(1)
        tops = confirm_topics(tops)
        _log.info("[生成] 共 %d 个话题，开始逐话题生成...", len(tops))
        markdown, urls = generate.build_notes(tops, full, project, date=args.date)
        _log.info("[写库] 保存到 vault...")
        path = vault.write_to_vault(markdown, tops, full, date=args.date, project=project)
        _log.info("完成！笔记已保存：%s", path)
    except SystemExit:
        raise
    except Exception:
        _log.exception("process 子命令执行失败")
        raise


def cmd_judge(args):
    try:
        project = _load_project_or_exit(args.project)
        full, tops = do_judge(args.folder, project)
        show_topics(tops)
        out = Path(args.folder) / "_topics.json"
        out.write_text(json.dumps(tops, ensure_ascii=False, indent=2), encoding="utf-8")
        (Path(args.folder) / "_cleaned.txt").write_text(full, encoding="utf-8")
        _log.info("话题已存到 %s，清洗文本存到 _cleaned.txt。可用 run 继续生成。", out)
    except SystemExit:
        raise
    except Exception:
        _log.exception("judge 子命令执行失败")
        raise


def cmd_run(args):
    """用已有的 _topics.json 和 _cleaned.txt 直接生成写库。"""
    try:
        project = _load_project_or_exit(args.project)
        folder = Path(args.folder)
        tops = json.loads((folder / "_topics.json").read_text(encoding="utf-8"))
        full = (folder / "_cleaned.txt").read_text(encoding="utf-8")
        tops = confirm_topics(tops)
        markdown, urls = generate.build_notes(tops, full, project, date=args.date)
        path = vault.write_to_vault(markdown, tops, full, date=args.date, project=project)
        _log.info("完成！笔记已保存：%s", path)
    except SystemExit:
        raise
    except Exception:
        _log.exception("run 子命令执行失败")
        raise


def main():
    logsetup.configure_logging()
    logsetup.set_run_id(uuid.uuid4().hex[:12])
    ap = argparse.ArgumentParser(description="数学笔记整理助手（本地 Ollama）")
    ap.add_argument("cmd", choices=["process", "judge", "run"])
    ap.add_argument("folder")
    ap.add_argument("--date", default=None, help="输出文件名日期前缀 YYYYMMDD，默认今天")
    ap.add_argument("--project", default=None, help="项目 folder_name（见 projects/ 目录），生成并归档到该项目")
    args = ap.parse_args()
    logsetup.set_stage({"process": "process", "judge": "judge", "run": "run"}[args.cmd])
    {"process": cmd_process, "judge": cmd_judge, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
