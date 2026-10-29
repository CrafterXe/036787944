"""日志配置：在入口（panel.py / main.py）启动早期调用一次 configure_logging()。

设计要点：
- 路径全部基于 config.ROOT 解析为绝对路径，禁止相对路径，避免从不同 CWD 启动
  时日志文件落到意料之外的目录。
- dictConfig 一次性配置；disable_existing_loggers=False 保留第三方库 logger。
- app.flow / app.core → app.log（std formatter，10MB×5，轮转）
- app.guard → app.log（guard formatter，含 func=/action=/reason=，单独 guard_file handler）
- app.llm → llm.log（20MB×3，轮转，不进 app.log / 控制台）
- root 兜底 → 控制台（INFO 及以上）
- ContextFilter 从 contextvars 读取 run_id / stage 注入 LogRecord，缺省 "-"。
- configure_logging 幂等：再次调用前先清掉已有 handler，避免重复输出。
"""
import contextvars
import logging
import logging.config
import tempfile
from pathlib import Path

import config

# 上下文变量：run_id（一次整理任务的唯一标识）、stage（当前处理阶段）
_run_id_ctx = contextvars.ContextVar("run_id", default="-")
_stage_ctx = contextvars.ContextVar("stage", default="-")


def set_run_id(run_id):
    """设置当前任务 run_id（入口处调用）。"""
    _run_id_ctx.set(run_id)


def set_stage(stage):
    """设置当前处理阶段（judge / run / generate / ...）。"""
    _stage_ctx.set(stage)


def get_run_id():
    return _run_id_ctx.get()


def get_stage():
    return _stage_ctx.get()


class ContextFilter(logging.Filter):
    """把 contextvars 里的 run_id / stage 注入到每一条 LogRecord。"""

    def filter(self, record):
        record.run_id = _run_id_ctx.get()
        record.stage = _stage_ctx.get()
        return True


_FMT = "%(asctime)s %(levelname)-7s [%(run_id)s][%(stage)s][%(name)s] %(message)s"
_GUARD_FMT = ("%(asctime)s %(levelname)-7s [%(run_id)s][%(stage)s][%(name)s] "
              "func=%(func)s action=%(action)s reason=%(reason)s %(message)s")


def configure_logging():
    """用 dictConfig 一次性配置全部 logger / handler / filter。可重复调用。

    注意事项：
    (a) 本函数仅供进程启动早期调用一次，勿在回调内重复调用（清 handler 非原子）。
    (b) 过渡期控制台输出由现有 print 负责；全量替换 print 后，再把 console 挂回 app.*。
    (c) run_id 跨请求关联：panel 回调经 gr.State 回写复用（judge 新建、run 复用）；CLI 各命令独立生成。
    """
    log_dir = Path(config.LOG_DIR)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # 只读文件系统等场景：回退到系统临时目录，保证启动不崩
        log_dir = Path(tempfile.gettempdir()) / "app_operational_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"[logsetup] 日志目录不可写，已回退到：{log_dir}")

    # 清掉已有 handler，避免重复调用导致同一日志写多次
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    for name in ("app.flow", "app.core", "app.llm", "app.guard"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)

    level = getattr(config, "LOG_LEVEL", "INFO")
    llm_level = getattr(config, "LLM_LOG_LEVEL", "DEBUG")

    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "ctx": {"()": "core.logsetup.ContextFilter"},
        },
        "formatters": {
            "std": {"format": _FMT},
            "guard": {"format": _GUARD_FMT},
        },
        "handlers": {
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "app.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
                "formatter": "std",
                "filters": ["ctx"],
            },
            "guard_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "app.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
                "formatter": "guard",
                "filters": ["ctx"],
            },
            "llm_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "llm.log"),
                "maxBytes": 20 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
                "formatter": "std",
                "filters": ["ctx"],
            },
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "std",
                "filters": ["ctx"],
            },
        },
        "loggers": {
            "app.flow": {
                "level": level,
                "handlers": ["app_file"],
                "propagate": False,
            },
            "app.core": {
                "level": level,
                "handlers": ["app_file"],
                "propagate": False,
            },
            "app.guard": {
                "level": level,
                "handlers": ["guard_file"],
                "propagate": False,
            },
            "app.llm": {
                "level": llm_level,
                "handlers": ["llm_file"],
                "propagate": False,
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }
    logging.config.dictConfig(cfg)
