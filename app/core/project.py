"""项目管理：项目档案存于 projects/<项目名>_<日期>/project.json，
归档目录为 vault/项目_<项目名>_<日期>/。
设计参考原项目 assistant.py，全部基于 config.ROOT 相对路径，可移植。
"""
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

import config

_log = logging.getLogger("app.core.project")


def _sanitize(name):
    """项目名去非法字符。"""
    name = re.sub(r'[\\/:*?"<>|]+', "_", name or "")
    name = re.sub(r"\s+", " ", name).strip()
    return name or "未命名项目"


def create_project(name, background="", structure="", requirements=""):
    """建项目：
    - projects 文件夹：<项目名>_<YYYYMMDD>
    - vault 文件夹    ：项目_<项目名>_<YYYYMMDD>
    返回项目 dict；失败抛异常。
    """
    base = _sanitize(name)
    today = datetime.now().strftime(config.DATE_FMT)
    folder_name = f"{base}_{today}"
    vault_folder = f"项目_{base}_{today}"

    proj_dir = config.PROJECTS_DIR / folder_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": base,
        "folder_name": folder_name,
        "vault_folder": vault_folder,
        "background": (background or "").strip(),
        "structure": (structure or "").strip(),
        "requirements": (requirements or "").strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (proj_dir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.VAULT_DIR / vault_folder).mkdir(parents=True, exist_ok=True)
    _log.info("已建项目：%s，vault：%s", folder_name, vault_folder)
    return data


def project_vault_folder(project):
    """归档定位：取 vault_folder；缺失回退 name。"""
    if not project:
        return None
    return project.get("vault_folder") or project.get("name")


def load_project(folder_name):
    """按 projects 下的文件夹名读项目档案；不存在返回 None。"""
    if not folder_name:
        return None
    path = config.PROJECTS_DIR / folder_name / "project.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def update_project(folder_name, new_name=None, background="",
                   structure="", requirements=""):
    """更新项目。new_name 与当前 name 不同则改名（同步挪 projects/ 与 vault/）。
    项目不存在返回 None；新名重名抛 FileExistsError；成功返回更新后的 dict。
    """
    data = load_project(folder_name)
    if not data:
        return None

    old_folder = data.get("folder_name") or _sanitize(folder_name)
    old_vault = data.get("vault_folder") or f"项目_{old_folder}"

    cur_base = data.get("name") or ""
    new_base = _sanitize(new_name) if new_name else cur_base
    renamed = (new_base != cur_base)

    if renamed:
        date_part = old_folder.rsplit("_", 1)[1] if "_" in old_folder \
            else datetime.now().strftime(config.DATE_FMT)
        new_folder = f"{new_base}_{date_part}"
        new_vault = f"项目_{new_base}_{date_part}"

        if (config.PROJECTS_DIR / new_folder).exists():
            raise FileExistsError(f"项目名已存在：{new_base}，未覆盖")

        old_proj_dir = config.PROJECTS_DIR / old_folder
        new_proj_dir = config.PROJECTS_DIR / new_folder
        if old_proj_dir.is_dir():
            shutil.move(str(old_proj_dir), str(new_proj_dir))
        else:
            new_proj_dir.mkdir(parents=True, exist_ok=True)

        old_vault_dir = config.VAULT_DIR / old_vault
        new_vault_dir = config.VAULT_DIR / new_vault
        if old_vault_dir.is_dir():
            shutil.move(str(old_vault_dir), str(new_vault_dir))
        else:
            new_vault_dir.mkdir(parents=True, exist_ok=True)

        data["name"] = new_base
        data["folder_name"] = new_folder
        data["vault_folder"] = new_vault
        proj_dir = new_proj_dir
    else:
        proj_dir = config.PROJECTS_DIR / old_folder

    data["background"] = (background or "").strip()
    data["structure"] = (structure or "").strip()
    data["requirements"] = (requirements or "").strip()
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (proj_dir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("已保存项目：%s", data.get('folder_name'))
    return data


def list_projects():
    """列出所有项目（projects/ 下含 project.json 的子目录名，即 folder_name）。"""
    out = []
    if config.PROJECTS_DIR.is_dir():
        for d in sorted(p.name for p in config.PROJECTS_DIR.iterdir() if p.is_dir()):
            if (config.PROJECTS_DIR / d / "project.json").is_file():
                out.append(d)
    return out


def project_prompt_block(project):
    """把项目背景/结构/要求拼成临时提示块，注入到模型请求最前面。
    project 为 None/空时返回空串。
    """
    if not project:
        return ""
    name = project.get("name") or ""
    bg = (project.get("background") or "").strip()
    struct = (project.get("structure") or "").strip()
    req = (project.get("requirements") or "").strip()
    if not (name or bg or struct or req):
        return ""
    lines = ["【项目信息】以下为当前项目的背景与要求，请优先遵守："]
    if name:
        lines.append(f"- 项目：{name}")
    if bg:
        lines.append(f"- 背景：{bg}")
    if struct:
        lines.append(f"- 结构：{struct}")
    if req:
        lines.append(f"- 要求：{req}")
    lines.append("【项目信息结束】")
    return "\n".join(lines) + "\n\n"


def inject_project(text, project):
    """把项目提示块临时拼到文本最前面（无项目则原样返回）。"""
    block = project_prompt_block(project)
    if not block:
        return text
    return block + (text or "")
