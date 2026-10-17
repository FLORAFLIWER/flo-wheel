"""测试工具：注入键盘组合键（模拟真实按键）。

与 ``inject.send_hotkey`` 的区别：这里 ``dwExtraInfo = 0``，所以对被测试的
程序来说和真人按键没有区别（不会因为有 MAGIC 标记而被放行）。

只注入**修饰键 + 主键**这一组，例如 ``--combo "Ctrl+Alt+Q"``。

用法::

    python tools/inject_keys.py --combo "Ctrl+Alt+Q" --down
    python tools/inject_keys.py --combo "Ctrl+Alt+Q" --up
    python tools/inject_keys.py --combo "Ctrl+Alt+Q" --hold 2000
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time

from mousewheel.input.hotkey_spec import parse_hotkey
from mousewheel.platform.win.winapi import (
    INPUT,
    INPUT_KEYBOARD,
    KEYBDINPUT,
    KEYEVENTF,
    user32,
)

#: 需要 KEYEVENTF_EXTENDEDKEY 的键（方向键等），否则部分程序收不到
_EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x5B, 0x5C}


def send(vk: int, up: bool) -> None:
    flags = KEYEVENTF.KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= KEYEVENTF.EXTENDEDKEY
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    arr = (INPUT * 1)(inp)
    if int(user32.SendInput(1, arr, ctypes.sizeof(INPUT))) != 1:
        raise SystemExit(f"SendInput 失败，错误码 {ctypes.get_last_error()}")


def press_all(spec) -> None:
    for vk in spec.modifier_vks:
        send(vk, False)
        time.sleep(0.02)
    send(spec.vk, False)


def release_all(spec) -> None:
    send(spec.vk, True)
    time.sleep(0.02)
    for vk in reversed(spec.modifier_vks):
        send(vk, True)
        time.sleep(0.02)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combo", required=True, help='例如 "Ctrl+Alt+Q"')
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--down", action="store_true")
    group.add_argument("--up", action="store_true")
    parser.add_argument("--hold", type=int, default=2000)
    args = parser.parse_args(argv)

    spec = parse_hotkey(args.combo)

    if args.down:
        press_all(spec)
        print(f"按下 {args.combo}", flush=True)
        return 0
    if args.up:
        release_all(spec)
        print(f"松开 {args.combo}", flush=True)
        return 0

    print(f"按下 {args.combo} …", flush=True)
    press_all(spec)
    try:
        time.sleep(max(0, args.hold) / 1000.0)
    finally:
        release_all(spec)
        print("松开", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
