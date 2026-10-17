"""最小验证：主线程装 WH_MOUSE_LL，子线程注入 X1，看回调是否被调用。

用来区分两种可能：
- 注入的 XBUTTON 根本没经过低级钩子
- 经过钩子，但 Qt 线程里的那套没跑起来
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mousewheel.platform.win.winapi import (  # noqa: E402
    HOOKPROC,
    MSG,
    MSLLHOOKSTRUCT,
    WH_MOUSE_LL,
    WM,
    kernel32,
    user32,
)

hits: list[tuple[int, int, int]] = []
all_events = 0


def proc(n_code: int, wparam: int, lparam: int):
    global all_events
    if n_code >= 0:
        all_events += 1
        data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        msg = int(wparam)
        if msg in (WM.XBUTTONDOWN, WM.XBUTTONUP):
            hits.append((msg, int(data.mouseData), int(data.dwExtraInfo)))
            print(f"HIT msg=0x{msg:X} mouseData=0x{int(data.mouseData):X} extra=0x{int(data.dwExtraInfo):X}", flush=True)
    return user32.CallNextHookEx(None, n_code, wparam, lparam)


def main() -> int:
    callback = HOOKPROC(proc)
    hmod = kernel32.GetModuleHandleW(None)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, hmod, 0)
    print(f"hook={hook} last_error={ctypes.get_last_error()}", flush=True)
    if not hook:
        return 1

    def injector() -> None:
        import os

        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
        time.sleep(1.0)
        py = sys.executable
        tool = str(ROOT / "tools" / "inject_mouse.py")
        subprocess.run([py, tool, "--button", "middle", "--down"], check=True,
                       stdout=subprocess.DEVNULL, env=env)
        time.sleep(0.4)
        subprocess.run([py, tool, "--button", "middle", "--up"], check=True,
                       stdout=subprocess.DEVNULL, env=env)

    threading.Thread(target=injector, daemon=True).start()

    msg = MSG()
    deadline = time.time() + 4.0
    while time.time() < deadline:
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        else:
            time.sleep(0.004)

    user32.UnhookWindowsHookEx(hook)
    print(f"总事件={all_events} X按钮事件={len(hits)}", flush=True)
    return 0 if hits else 2


if __name__ == "__main__":
    sys.exit(main())
