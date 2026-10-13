"""数学笔记整理 · CLI 入口。

用法：
  python main.py process <输入文件夹>          全流程：清洗→提话题→(确认)→生成→写库
  python main.py judge <输入文件夹>            只做判断（清洗+提话题），不生成不写库
  python main.py run <输入文件夹>              用已有 _topics.json/_cleaned.txt 直接生成写库

可选 --project <项目folder_name>：使用项目的背景/要求生成，并归档到项目目录。

输入文件夹内放：飞书妙计 txt、板书截图 jpg、老师资料 pdf/docx。
无项目时输出存 vault/，文件名 YYYYMMDD_课程_主题.md；有项目时存 vault/<项目归档>/。
"""
import sys
import json
import argparse
from pathlib import Path

import config
from core import ingest, clean, chunk, topics as topics_mod, generate, vault
from core import project as proj_mod


def load_input(folder):
    folder = Path(folder)
    if not folder.is_dir():
        print(f"[错误] 输入文件夹不存在: {folder}")
        sys.exit(1)
    print(f"[1/4] 读取并归一化材料: {folder}")
    text = ingest.ingest_folder(folder)
    if not text.strip():
        print("[错误] 未读取到任何文本内容。")
        sys.exit(1)
    print(f"      共 {len(text)} 字。")
    return text


def _load_project_or_exit(name):
    if not name:
        return None
    p = proj_mod.load_project(name)
    if not p:
        print(f"[错误] 项目不存在: {name}（可用项目见 projects/ 目录）")
        sys.exit(1)
    print(f"[项目] {p.get('name')}（归档：{p.get('vault_folder')}）")
    return p


def do_judge(folder, project=None):
    text = load_input(folder)
    print("[2/4] 分块...")
    chunks = chunk.chunk_text(text)
    print(f"      分成 {len(chunks)} 块。")
    print("[3/4] 清洗（去除口语废话，保留全部知识）...")
    cleaned = clean.clean_text(chunks)
    full = "\n\n".join(cleaned)
    print("[4/4] 提取话题...")
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
    project = _load_project_or_exit(args.project)
    full, tops = do_judge(args.folder, project)
    if not tops:
        print("[错误] 未提取到任何话题，终止。")
        sys.exit(1)
    tops = confirm_topics(tops)
    print(f"\n[生成] 共 {len(tops)} 个话题，开始逐话题生成...")
    markdown, urls = generate.build_notes(tops, full, project)
    print("[写库] 保存到 vault...")
    path = vault.write_to_vault(markdown, tops, full, date=args.date, project=project)
    print(f"\n完成！笔记已保存：{path}")


def cmd_judge(args):
    project = _load_project_or_exit(args.project)
    full, tops = do_judge(args.folder, project)
    show_topics(tops)
    out = Path(args.folder) / "_topics.json"
    out.write_text(json.dumps(tops, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(args.folder) / "_cleaned.txt").write_text(full, encoding="utf-8")
    print(f"话题已存到 {out}，清洗文本存到 _cleaned.txt。可用 run 继续生成。")


def cmd_run(args):
    """用已有的 _topics.json 和 _cleaned.txt 直接生成写库。"""
    project = _load_project_or_exit(args.project)
    folder = Path(args.folder)
    tops = json.loads((folder / "_topics.json").read_text(encoding="utf-8"))
    full = (folder / "_cleaned.txt").read_text(encoding="utf-8")
    tops = confirm_topics(tops)
    markdown, urls = generate.build_notes(tops, full, project)
    path = vault.write_to_vault(markdown, tops, full, date=args.date, project=project)
    print(f"\n完成！笔记已保存：{path}")


def main():
    ap = argparse.ArgumentParser(description="数学笔记整理助手（本地 Ollama）")
    ap.add_argument("cmd", choices=["process", "judge", "run"])
    ap.add_argument("folder")
    ap.add_argument("--date", default=None, help="输出文件名日期前缀 YYYYMMDD，默认今天")
    ap.add_argument("--project", default=None, help="项目 folder_name（见 projects/ 目录），生成并归档到该项目")
    args = ap.parse_args()
    {"process": cmd_process, "judge": cmd_judge, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
