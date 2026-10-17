"""动作分派与校验。"""

from __future__ import annotations

import logging

from ..config.model import Action
from .base import ActionContext, ActionResult
from . import builtin

__all__ = ["ACTION_TYPES", "ACTION_LABELS", "execute", "validate"]

log = logging.getLogger(__name__)

ACTION_TYPES = (
    "hotkey",
    "text",
    "launch",
    "url",
    "media",
    "system",
    "script",
    "none",
)

ACTION_LABELS = {
    "hotkey": "快捷键",
    "text": "输入文本",
    "launch": "启动程序",
    "url": "打开网址",
    "media": "媒体键",
    "system": "系统动作",
    "script": "运行命令",
    "none": "空",
}

_HANDLERS = {
    "hotkey": builtin.run_hotkey,
    "text": builtin.run_text,
    "launch": builtin.run_launch,
    "url": builtin.run_url,
    "media": builtin.run_media,
    "system": builtin.run_system,
    "script": builtin.run_script,
    "none": builtin.run_none,
}


def validate(action: Action) -> str | None:
    """返回错误提示，None 表示配置合法。"""
    if action.type not in _HANDLERS:
        return f"未知动作类型：{action.type}"
    t = action.type
    p = action.params
    if t == "hotkey":
        from ..input.hotkey_spec import HotkeyError, parse_hotkey

        keys = str(p.get("keys") or "").strip()
        if not keys:
            return "快捷键不能为空"
        try:
            parse_hotkey(keys)
        except HotkeyError as exc:
            return str(exc)
    elif t == "text" and not str(p.get("text") or "").strip():
        return "文本不能为空"
    elif t == "launch" and not str(p.get("path") or "").strip():
        return "路径不能为空"
    elif t == "url" and not str(p.get("url") or "").strip():
        return "网址不能为空"
    elif t == "media" and str(p.get("key") or "").upper() not in builtin.MEDIA_KEYS:
        return "请选择一个媒体键"
    elif t == "system" and str(p.get("cmd") or "").lower() not in builtin._SYSTEM_COMMANDS:
        return "请选择一个系统动作"
    elif t == "script" and not str(p.get("command") or "").strip():
        return "命令不能为空"
    return None


def execute(action: Action, ctx: ActionContext) -> ActionResult:
    handler = _HANDLERS.get(action.type)
    if handler is None:
        return ActionResult(False, f"未知动作类型：{action.type}")
    try:
        return handler(action.params, ctx)
    except Exception as exc:  # 动作失败不能影响常驻进程
        log.exception("动作执行失败: %s", action.type)
        return ActionResult(False, f"{type(exc).__name__}: {exc}")
