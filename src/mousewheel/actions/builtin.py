"""内置动作实现。

每个函数签名统一为 ``(params: dict, ctx: ActionContext) -> ActionResult``，
由 :mod:`registry` 按 ``action.type`` 分派。加新动作只需要：
1. 写一个函数
2. 在 registry 的 ``HANDLERS`` 里登记
3. 在设置界面里加一个编辑面板
"""

from __future__ import annotations

import os
import subprocess
import time

from ..input.hotkey_spec import parse_hotkey
from ..input.inject import send_hotkey, send_vk_tap
from ..platform.win.clipboard import get_clipboard_text, set_clipboard_text
from ..platform.win.winapi import VK, user32
from .base import ActionContext, ActionResult, ensure_foreground

__all__ = [
    "run_hotkey",
    "run_text",
    "run_launch",
    "run_url",
    "run_media",
    "run_system",
    "run_script",
    "run_none",
    "MEDIA_KEYS",
]

MEDIA_KEYS = {
    "VOLUME_UP": VK.VOLUME_UP,
    "VOLUME_DOWN": VK.VOLUME_DOWN,
    "VOLUME_MUTE": VK.VOLUME_MUTE,
    "PLAY_PAUSE": VK.MEDIA_PLAY_PAUSE,
    "NEXT": VK.MEDIA_NEXT_TRACK,
    "PREV": VK.MEDIA_PREV_TRACK,
    "STOP": VK.MEDIA_STOP,
}

_CREATE_NO_WINDOW = 0x08000000


# ---- 快捷键 --------------------------------------------------------------


def run_hotkey(params: dict, ctx: ActionContext) -> ActionResult:
    keys = str(params.get("keys") or "").strip()
    if not keys:
        return ActionResult(False, "没有设置快捷键")
    repeat = int(params.get("repeat") or 1)
    delay_ms = int(params.get("delay_ms") or 15)
    spec = parse_hotkey(keys)
    if ctx.dry_run:
        return ActionResult(True, f"[演练] {keys}")
    ensure_foreground(ctx.foreground_hwnd)
    send_hotkey(spec, hold_ms=delay_ms, repeat=repeat)
    return ActionResult(True, keys)


# ---- 文本 ----------------------------------------------------------------


def run_text(params: dict, ctx: ActionContext) -> ActionResult:
    text = str(params.get("text") or "")
    if not text:
        return ActionResult(False, "没有设置文本")
    if ctx.dry_run:
        return ActionResult(True, f"[演练] 输入 {len(text)} 字")
    ensure_foreground(ctx.foreground_hwnd)
    restore = bool(params.get("restore_clipboard", True))
    previous = get_clipboard_text() if restore else None
    if not set_clipboard_text(text):
        return ActionResult(False, "写入剪贴板失败")
    time.sleep(0.03)
    send_hotkey(parse_hotkey("Ctrl+V"), hold_ms=15)
    if restore:
        time.sleep(0.15)  # 等目标程序真的取走剪贴板内容
        if previous is not None:
            set_clipboard_text(previous)
    return ActionResult(True, f"输入 {len(text)} 字")


# ---- 启动程序 / 网址 -----------------------------------------------------


def run_launch(params: dict, ctx: ActionContext) -> ActionResult:
    path = str(params.get("path") or "").strip()
    if not path:
        return ActionResult(False, "没有设置路径")
    args = [str(a) for a in (params.get("args") or []) if str(a)]
    cwd = params.get("cwd") or None
    if ctx.dry_run:
        return ActionResult(True, f"[演练] 启动 {path}")
    if args or cwd:
        if not os.path.exists(path):
            return ActionResult(False, f"路径不存在：{path}")
        subprocess.Popen([path, *args], cwd=cwd, close_fds=True)
    else:
        if not os.path.exists(path):
            return ActionResult(False, f"路径不存在：{path}")
        os.startfile(path)  # type: ignore[attr-defined]
    return ActionResult(True, path)


def run_url(params: dict, ctx: ActionContext) -> ActionResult:
    url = str(params.get("url") or "").strip()
    if not url:
        return ActionResult(False, "没有设置网址")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    if ctx.dry_run:
        return ActionResult(True, f"[演练] 打开 {url}")
    os.startfile(url)  # type: ignore[attr-defined]
    return ActionResult(True, url)


# ---- 媒体键 --------------------------------------------------------------


def run_media(params: dict, ctx: ActionContext) -> ActionResult:
    key = str(params.get("key") or "").strip().upper()
    vk = MEDIA_KEYS.get(key)
    if vk is None:
        return ActionResult(False, f"未知媒体键：{key}")
    repeat = max(1, int(params.get("repeat") or 1))
    if ctx.dry_run:
        return ActionResult(True, f"[演练] {key} ×{repeat}")
    for i in range(repeat):
        send_vk_tap(vk, hold_ms=15)
        if i + 1 < repeat:
            time.sleep(0.12)  # 音量键连发太快系统会丢
    return ActionResult(True, key)


# ---- 系统动作 ------------------------------------------------------------

_SYSTEM_COMMANDS = {
    "lock": "锁定屏幕",
    "showdesktop": "显示桌面",
    "taskmgr": "任务管理器",
    "explorer": "文件资源管理器",
    "screenshot": "截图",
    "sleep": "睡眠",
}


def run_system(params: dict, ctx: ActionContext) -> ActionResult:
    cmd = str(params.get("cmd") or "").strip().lower()
    if cmd not in _SYSTEM_COMMANDS:
        return ActionResult(False, f"未知系统动作：{cmd}")
    if ctx.dry_run:
        return ActionResult(True, f"[演练] {_SYSTEM_COMMANDS[cmd]}")

    if cmd == "lock":
        user32.LockWorkStation()
        return ActionResult(True, "锁屏")
    if cmd == "showdesktop":
        send_hotkey(parse_hotkey("Win+D"))
        return ActionResult(True, "显示桌面")
    if cmd == "screenshot":
        send_hotkey(parse_hotkey("Win+Shift+S"))
        return ActionResult(True, "截图")
    if cmd == "taskmgr":
        subprocess.Popen(["taskmgr.exe"], close_fds=True)
        return ActionResult(True, "任务管理器")
    if cmd == "explorer":
        subprocess.Popen(["explorer.exe"], close_fds=True)
        return ActionResult(True, "资源管理器")
    if cmd == "sleep":
        import ctypes

        powrprof = ctypes.WinDLL("powrprof")
        powrprof.SetSuspendState.argtypes = [ctypes.c_bool, ctypes.c_bool, ctypes.c_bool]
        powrprof.SetSuspendState(False, False, False)
        return ActionResult(True, "睡眠")
    return ActionResult(False, "未实现")


# ---- 脚本 ----------------------------------------------------------------


def run_script(params: dict, ctx: ActionContext) -> ActionResult:
    command = str(params.get("command") or "").strip()
    if not command:
        return ActionResult(False, "没有设置命令")
    shell = str(params.get("shell") or "cmd").lower()
    hidden = bool(params.get("hidden", True))
    if ctx.dry_run:
        return ActionResult(True, f"[演练] {shell}: {command}")
    flags = _CREATE_NO_WINDOW if hidden else 0
    if shell == "pwsh":
        argv = ["pwsh", "-NoProfile", "-Command", command]
        subprocess.Popen(argv, close_fds=True, creationflags=flags)
    else:
        subprocess.Popen(command, shell=True, creationflags=flags)
    return ActionResult(True, command)


# ---- 空 ------------------------------------------------------------------


def run_none(params: dict, ctx: ActionContext) -> ActionResult:
    return ActionResult(True, "")
