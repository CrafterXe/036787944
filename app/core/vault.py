"""写库：推断标题，命名 YYYYMMDD_课程_主题。
无项目时存入 vault/ 根目录；指定项目时存入 vault/<项目归档文件夹>/。
"""
import logging
import re
from datetime import datetime
from pathlib import Path
import config

_log = logging.getLogger("app.core.vault")


def _infer_course(text):
    if any(k in text for k in ("数分", "数学分析", "极限", "连续", "导数", "积分")):
        # 高代也可能出现"连续"，优先看强特征
        if any(k in text for k in ("多项式", "矩阵", "行列式", "线性", "向量空间", "高代")):
            return "高代"
        return "数分"
    if any(k in text for k in ("高代", "高等代数", "多项式", "矩阵", "行列式", "线性")):
        return "高代"
    return "笔记"


def _infer_title(topics):
    """从话题推断主题：取第一个【核心】话题，否则取第一个话题。"""
    for t in topics:
        if t.get("importance") == "核心":
            return t["name"]
    return topics[0]["name"] if topics else "未命名"


def _safe(name):
    """文件名去非法字符。"""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def _target_dir(project=None):
    """归档目录：有项目用 vault/<vault_folder>/，否则 vault/ 根目录。"""
    if project:
        from . import project as proj_mod
        vf = proj_mod.project_vault_folder(project)
        if vf:
            d = config.VAULT_DIR / vf
            d.mkdir(parents=True, exist_ok=True)
            return d
    return config.VAULT_DIR


def write_to_vault(markdown, topics, full_text, date=None, project=None):
    """落盘 vault。返回文件路径。文件名：YYYYMMDD_课程_主题.md
    project 非空时写入该项目的归档目录。
    """
    date = date or datetime.now().strftime(config.DATE_FMT)
    course = _infer_course(full_text)
    title = _infer_title(topics)
    folder = _target_dir(project)
    fname = f"{date}_{course}_{_safe(title)}.md"
    # 同名则追加序号
    path = folder / fname
    i = 2
    while path.exists():
        path = folder / f"{date}_{course}_{_safe(title)}_{i}.md"
        i += 1
    path.write_text(markdown, encoding="utf-8")
    _log.info("已写入: %s", path)
    return path
