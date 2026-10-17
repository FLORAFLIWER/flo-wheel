"""测试工具：模拟真实鼠标侧键 X1。

注意这里**故意不用** ``inject.send_mouse_click`` —— 那个函数带 MAGIC 标记，
会被钩子当成"自己注入的"直接放行，起不到模拟用户操作的作用。

用法::

    python tools/inject_x1.py --hold 2500   # 按住 2.5 秒再松开
    python tools/inject_x1.py --down        # 只按下
    python tools/inject_x1.py --up          # 只松开
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

XBUTTON1 = 1


def _send(down: bool, xbutton: int = XBUTTON1) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(
        dx=0,
        dy=0,
        mouseData=(xbutton << 16),
        dwFlags=MOUSEEVENTF.XDOWN if down else MOUSEEVENTF.XUP,
        time=0,
        dwExtraInfo=0,  # 0 = 看起来像真实用户输入
    )
    arr = (INPUT * 1)(inp)
    sent = user32.SendInput(1, arr, ctypes.sizeof(INPUT))
    if sent != 1:
        raise SystemExit(f"SendInput 失败，错误码 {ctypes.get_last_error()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--down", action="store_true", help="只按下，不松开")
    group.add_argument("--up", action="store_true", help="只松开")
    parser.add_argument("--hold", type=int, default=2500, help="按住多少毫秒（默认模式）")
    parser.add_argument("--xbutton", type=int, default=1, choices=(1, 2))
    args = parser.parse_args(argv)

    if args.down:
        _send(True, args.xbutton)
        print(f"按下 X{args.xbutton}", flush=True)
        return 0
    if args.up:
        _send(False, args.xbutton)
        print(f"松开 X{args.xbutton}", flush=True)
        return 0

    print(f"按下 X{args.xbutton} …", flush=True)
    _send(True, args.xbutton)
    try:
        time.sleep(max(0, args.hold) / 1000.0)
    finally:
        _send(False, args.xbutton)
        print("松开", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
