"""测试工具：注入鼠标按键（模拟真实用户操作）。

**重要发现**：Windows 会过滤掉通过 SendInput 注入的 XBUTTON 事件 —— 注入的
X1/X2 不会经过 WH_MOUSE_LL 钩子。所以自动化测试侧键时走不通，改用中键验证
（代码路径完全相同，只是按钮名不同）。

本脚本的注入事件 ``dwExtraInfo = 0``，所以对被测试的程序来说与真实按键无异。

用法::

    python tools/inject_mouse.py --button middle --down
    python tools/inject_mouse.py --button middle --up
    python tools/inject_mouse.py --button middle --hold 2000
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time

from mousewheel.platform.win.winapi import (
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF,
    MOUSEINPUT,
    user32,
)

#: button -> (mouseData 高位, down flag, up flag)
BUTTONS = {
    "left": (0, MOUSEEVENTF.LEFTDOWN, MOUSEEVENTF.LEFTUP),
    "right": (0, MOUSEEVENTF.RIGHTDOWN, MOUSEEVENTF.RIGHTUP),
    "middle": (0, MOUSEEVENTF.MIDDLEDOWN, MOUSEEVENTF.MIDDLEUP),
    "x1": (1, MOUSEEVENTF.XDOWN, MOUSEEVENTF.XUP),
    "x2": (2, MOUSEEVENTF.XDOWN, MOUSEEVENTF.XUP),
}


def send(down: bool, button: str) -> None:
    xbutton, down_flag, up_flag = BUTTONS[button]
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(
        dx=0,
        dy=0,
        mouseData=(xbutton << 16),
        dwFlags=down_flag if down else up_flag,
        time=0,
        dwExtraInfo=0,
    )
    arr = (INPUT * 1)(inp)
    if int(user32.SendInput(1, arr, ctypes.sizeof(INPUT))) != 1:
        raise SystemExit(f"SendInput 失败，错误码 {ctypes.get_last_error()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--down", action="store_true")
    group.add_argument("--up", action="store_true")
    parser.add_argument("--button", default="middle", choices=sorted(BUTTONS))
    parser.add_argument("--hold", type=int, default=2500)
    args = parser.parse_args(argv)

    if args.down:
        send(True, args.button)
        print(f"按下 {args.button}", flush=True)
        return 0
    if args.up:
        send(False, args.button)
        print(f"松开 {args.button}", flush=True)
        return 0

    print(f"按下 {args.button} …", flush=True)
    send(True, args.button)
    try:
        time.sleep(max(0, args.hold) / 1000.0)
    finally:
        send(False, args.button)
        print("松开", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
