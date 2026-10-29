"""Gradio 操作面板：整理 Tab（判断 → 确认话题 → 生成写库）+ 项目管理 Tab。
启动：python panel.py  （或由 start-all.bat 拉起）
"""
import json
import logging
import uuid
from pathlib import Path

import gradio as gr

import config
from core import ingest, chunk, clean, topics as topics_mod, generate, vault
from core import project as proj_mod
from core import logsetup

logsetup.configure_logging()
_flow = logging.getLogger("app.flow")

_NONE = "（不使用项目）"


# ---------- 整理流水线 ----------

def _resolve_project(project_sel):
    """下拉值 → 项目 dict；'（不使用项目）' → None。"""
    if not project_sel or project_sel == _NONE:
        return None
    return proj_mod.load_project(project_sel)


def do_judge(folder, project_sel):
    """第一步：读取 → 清洗 → 提话题。返回 (状态文本, 话题JSON文本, full_text, run_id)。"""
    # 每次「判断」都开新 run_id，经回写 state 供 do_run 复用（judge→run 串联）
    rid = uuid.uuid4().hex[:12]
    logsetup.set_run_id(rid)
    logsetup.set_stage("judge")
    _flow.info("run started: stage=judge run_id=%s folder=%s project=%s",
               rid, folder, project_sel)
    folder = (folder or "").strip()
    if not folder:
        return "请先填写输入文件夹路径。", "", "", rid
    if not Path(folder).is_dir():
        return f"文件夹不存在：{folder}", "", "", rid
    project = _resolve_project(project_sel)
    try:
        logs = []
        if project:
            logs.append(f"[项目] {project.get('name')}（归档：{project.get('vault_folder')}）")
        logs.append("[1/4] 读取并归一化材料...")
        text = ingest.ingest_folder(folder)
        logs.append(f"      共 {len(text)} 字。")
        logs.append("[2/4] 分块...")
        cs = chunk.chunk_text(text)
        logs.append(f"      分成 {len(cs)} 块。")
        logs.append("[3/4] 清洗（去除口语废话，保留全部知识）...")
        cl = clean.clean_text(cs)
        full = "\n\n".join(cl)
        logs.append("[4/4] 提取话题...")
        tops = topics_mod.propose_topics(cl, full, project)
        logs.append(f"      共 {len(tops)} 个话题。")
        if not tops:
            return "\n".join(logs) + "\n未提取到话题。", "", full, rid
        topics_json = json.dumps(tops, ensure_ascii=False, indent=2)
        status = "\n".join(logs) + f"\n\n已提取 {len(tops)} 个话题，可在下方编辑后生成。"
        return status, topics_json, full, rid
    except Exception as e:
        _flow.exception("judge stage failed: folder=%s", folder)
        return f"判断阶段出错：{e}", "", "", rid


def do_run(folder, project_sel, topics_json, full, date, run_id_state):
    """第二步：用话题生成笔记并写入 vault。返回 (状态, 笔记预览, 输出路径, run_id)。"""
    # run_id 跨请求关联：state 已有值则复用（没先点判断就点生成时新建）
    prev = (run_id_state or "").strip()
    rid = prev or uuid.uuid4().hex[:12]
    logsetup.set_run_id(rid)
    logsetup.set_stage("run")
    _flow.info("run started: stage=run run_id=%s(%s) folder=%s project=%s",
               rid, "reused" if prev else "new", folder, project_sel)
    if not full:
        return "请先执行第一步「判断」。", "", "", rid
    try:
        tops = json.loads(topics_json)
        if not isinstance(tops, list) or not tops:
            return "话题为空或格式错误，请先判断。", "", "", rid
    except Exception as e:
        _flow.exception("run stage failed: topics json parse error")
        return f"话题 JSON 解析失败：{e}", "", "", rid
    project = _resolve_project(project_sel)
    try:
        date = (date or "").strip() or None
        md, urls = generate.build_notes(tops, full, project, date=date)
        path = vault.write_to_vault(md, tops, full, date=date, project=project)
        status = f"生成完成！{len(tops)} 个章节，参考来源 {len(urls)} 条。\n已保存：{path}"
        return status, md, str(path), rid
    except Exception as e:
        _flow.exception("run stage failed: folder=%s", folder)
        return f"生成阶段出错：{e}", "", "", rid


# ---------- 项目管理 ----------

def refresh_projects():
    """刷新项目下拉。返回 (整理Tab下拉, 管理Tab下拉)。"""
    choices = [_NONE] + proj_mod.list_projects()
    mgmt_choices = proj_mod.list_projects()
    return (gr.update(choices=choices, value=_NONE),
            gr.update(choices=mgmt_choices, value=mgmt_choices[0] if mgmt_choices else None))


def load_project_to_form(folder_name):
    """把选中项目的信息填入管理表单。"""
    p = proj_mod.load_project(folder_name)
    if not p:
        return "", "", "", "", "项目不存在。"
    return (p.get("name", ""), p.get("background", ""),
            p.get("structure", ""), p.get("requirements", ""),
            f"已加载：{p.get('folder_name')}")


def save_project(folder_name, name, background, structure, requirements):
    """保存项目（改字段/改名）。"""
    if not folder_name:
        return "请先选择项目。", *refresh_projects()
    try:
        p = proj_mod.update_project(folder_name, new_name=name,
                                    background=background, structure=structure,
                                    requirements=requirements)
        if not p:
            return "项目不存在。", *refresh_projects()
        msg = f"已保存：{p.get('folder_name')}（vault：{p.get('vault_folder')}）"
        return (msg, *refresh_projects())
    except FileExistsError as e:
        return (str(e), *refresh_projects())
    except Exception as e:
        return (f"保存失败：{e}", *refresh_projects())


def create_project_ui(name, background, structure, requirements):
    """新建项目。"""
    if not (name or "").strip():
        return "请填写项目名称。", *refresh_projects()
    try:
        p = proj_mod.create_project(name, background, structure, requirements)
        msg = f"已创建项目：{p.get('folder_name')}（vault：{p.get('vault_folder')}）"
        return (msg, *refresh_projects())
    except Exception as e:
        return (f"创建失败：{e}", *refresh_projects())


# ---------- 界面 ----------

# 项目 logo（app/assets/logo.png）
_LOGO_PATH = str(Path(__file__).parent / "assets" / "logo.png")


def build_demo():
    with gr.Blocks(title="数学笔记整理助手") as demo:
        with gr.Row():
            gr.Markdown("# 数学笔记整理助手\n输入文件夹放：飞书妙计 txt、板书截图、老师资料 pdf/docx。可用项目来组织笔记归档与生成要求。", scale=4)
            gr.Image(value=_LOGO_PATH, show_label=False, interactive=False,
                     height=120, width=102, scale=1)
        full_state = gr.State("")

        with gr.Tabs():
            # ===== Tab 1：整理 =====
            with gr.Tab("整理"):
                run_id_state = gr.State("")  # judge→run 跨请求共用的 run_id
                proj_dd = gr.Dropdown(label="选择项目（可选）", choices=[_NONE],
                                      value=_NONE, interactive=True)
                with gr.Row():
                    folder_tb = gr.Textbox(label="输入文件夹路径", scale=4,
                                           placeholder=r"D:\_MyWork\...\20261005高代_复数\输入")
                    date_tb = gr.Textbox(label="日期前缀(可选)", scale=1, placeholder="YYYYMMDD")

                judge_btn = gr.Button("① 判断：清洗 + 提取话题", variant="primary")
                status_box = gr.Textbox(label="状态 / 进度", lines=8, interactive=False)

                gr.Markdown("### 话题清单（可编辑：增删话题、改名称/重要度/类型，JSON 格式。type: knowledge=知识笔记，exercise=习题讲解）")
                topics_tb = gr.Textbox(label="topics JSON", lines=12, interactive=True)

                run_btn = gr.Button("② 生成并写入 vault", variant="primary")
                out_path = gr.Textbox(label="输出文件", interactive=False)
                preview = gr.Markdown(label="笔记预览")

                judge_btn.click(do_judge, inputs=[folder_tb, proj_dd],
                                outputs=[status_box, topics_tb, full_state, run_id_state])
                run_btn.click(do_run, inputs=[folder_tb, proj_dd, topics_tb, full_state, date_tb, run_id_state],
                              outputs=[status_box, preview, out_path, run_id_state])

            # ===== Tab 2：项目管理 =====
            with gr.Tab("项目管理"):
                with gr.Row():
                    refresh_btn = gr.Button("刷新项目列表", scale=1)
                    mgmt_dd = gr.Dropdown(label="选择项目", choices=[], interactive=True, scale=3)

                mgmt_status = gr.Textbox(label="状态", interactive=False)

                gr.Markdown("#### 编辑 / 改名 / 保存选中项目")
                p_name = gr.Textbox(label="项目名称")
                p_bg = gr.Textbox(label="背景（课程/教材/学期等）", lines=3)
                p_struct = gr.Textbox(label="结构（笔记的章节组织偏好）", lines=3)
                p_req = gr.Textbox(label="要求（生成风格/深度/格式要求）", lines=3)
                save_btn = gr.Button("保存项目", variant="primary")

                gr.Markdown("#### 新建项目")
                n_name = gr.Textbox(label="新项目名称")
                n_bg = gr.Textbox(label="背景", lines=2)
                n_struct = gr.Textbox(label="结构", lines=2)
                n_req = gr.Textbox(label="要求", lines=2)
                create_btn = gr.Button("创建项目", variant="primary")

                # 事件
                refresh_btn.click(refresh_projects, outputs=[proj_dd, mgmt_dd])
                mgmt_dd.change(load_project_to_form, inputs=[mgmt_dd],
                               outputs=[p_name, p_bg, p_struct, p_req, mgmt_status])
                save_btn.click(save_project,
                               inputs=[mgmt_dd, p_name, p_bg, p_struct, p_req],
                               outputs=[mgmt_status, proj_dd, mgmt_dd])
                create_btn.click(create_project_ui,
                                 inputs=[n_name, n_bg, n_struct, n_req],
                                 outputs=[mgmt_status, proj_dd, mgmt_dd])

        # 启动时装载项目列表
        demo.load(refresh_projects, outputs=[proj_dd, mgmt_dd])

    return demo


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(inbrowser=True, server_name="127.0.0.1",
                server_port=14000, show_error=True, theme=gr.themes.Soft())
