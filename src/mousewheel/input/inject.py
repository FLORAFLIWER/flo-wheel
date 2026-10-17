"""SendInput 注入：按键序列、鼠标点击重放。

所有注入事件都带 :data:`MAGIC_EXTRA_INFO` 标记，钩子看到标记直接放行，
所以本程序不会把自己的注入当成用户输入（避免自触发与递归）。

**不要在钩子回调线程里调用这里的函数**：SendInput 会同步触发钩子，
重入容易卡死。全部经由主线程/线程池调度。
"""

from __future__ import annotations

import ctypes
import time

from ..platform.win.winapi import (
    INPUT,
    KEYBDINPUT,
    KEYEVENTF,
    MAGIC_EXTRA_INFO,
    MAPVK_VK_TO_VSC,
    MOUSEEVENTF,
    MOUSEINPUT,
    INPUT_KEYBOARD,
    INPUT_MOUSE,
    XBUTTON,
    user32,
)
from .hotkey_spec import EXTENDED_VKS, HotkeySpec, parse_hotkey

__all__ = [
    "send_hotkey",
    "send_hotkey_text",
    "send_mouse_click",
    "send_vk_tap",
]

_MOUSE_EXTRA = MAGIC_EXTRA_INFO


def _key_input(vk: int, up: bool, extended: bool) -> INPUT:
    flags = 0
    if up:
        flags |= KEYEVENTF.KEYUP
    if extended:
        flags |= KEYEVENTF.EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=MAGIC_EXTRA_INFO)
    return inp


def _mouse_input(flags: int, mouse_data: int = 0) -> INPUT:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx=0, dy=0, mouseData=mouse_data, dwFlags=flags, time=0, dwExtraInfo=_MOUSE_EXTRA)
    return inp


def _send(inputs: list[INPUT]) -> int:
    if not inputs:
        return 0
    arr = (INPUT * len(inputs))(*inputs)
    return int(user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)))


def send_vk_tap(vk: int, hold_ms: int = 15) -> None:
    """按一下单个虚拟键。"""
    extended = vk in EXTENDED_VKS
    _send([_key_input(vk, False, extended)])
    time.sleep(max(0, hold_ms) / 1000.0)
    _send([_key_input(vk, True, extended)])


def send_hotkey(spec: HotkeySpec, hold_ms: int = 15, repeat: int = 1) -> None:
    """发送一个组合键，例如 Ctrl+Shift+S。

    按下顺序：修饰键 → 主键；松开顺序相反。修饰键与主键之间留 ``hold_ms``，
    部分程序（尤其游戏和远程桌面）需要这个间隔才认得出。
    """
    mods = spec.modifier_vks
    main_ext = spec.is_extended
    repeat = max(1, int(repeat))
    hold_ms = max(0, int(hold_ms))

    for i in range(repeat):
        downs = [_key_input(vk, False, vk in EXTENDED_VKS) for vk in mods]
        downs.append(_key_input(spec.vk, False, main_ext))
        _send(downs)
        time.sleep(hold_ms / 1000.0)
        ups = [_key_input(spec.vk, True, main_ext)]
        ups.extend(_key_input(vk, True, vk in EXTENDED_VKS) for vk in reversed(mods))
        _send(ups)
        if i + 1 < repeat:
            time.sleep(max(hold_ms, 20) / 1000.0)


def send_hotkey_text(text: str, hold_ms: int = 15, repeat: int = 1) -> None:
    send_hotkey(parse_hotkey(text), hold_ms=hold_ms, repeat=repeat)


_XBUTTON_FLAG = {
    "x1": (XBUTTON.X1, MOUSEEVENTF.XDOWN, MOUSEEVENTF.XUP),
    "x2": (XBUTTON.X2, MOUSEEVENTF.XDOWN, MOUSEEVENTF.XUP),
    "middle": (0, MOUSEEVENTF.MIDDLEDOWN, MOUSEEVENTF.MIDDLEUP),
    "right": (0, MOUSEEVENTF.RIGHTDOWN, MOUSEEVENTF.RIGHTUP),
    "left": (0, MOUSEEVENTF.LEFTDOWN, MOUSEEVENTF.LEFTUP),
}


def send_mouse_click(button: str, hold_ms: int = 0) -> None:
    """重放一次真实的鼠标点击（用于"快击保留原功能"）。"""
    entry = _XBUTTON_FLAG.get(button)
    if entry is None:
        return
    xbtn, down_flag, up_flag = entry
    data = (xbtn << 16) if xbtn else 0
    _send([_mouse_input(down_flag, data)])
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
    _send([_mouse_input(up_flag, data)])
