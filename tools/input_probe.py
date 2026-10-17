"""输入能力探针：确认当前进程能否真的注入鼠标事件。

检查三件事：
1. 进程是否在 AppContainer 里（沙箱环境会让 SendInput 静默失效）
2. 注入"移动 10 像素"后光标是否真的动了
3. 同进程装 WH_MOUSE_LL + 注入 X1，钩子能否看到（验证注入事件是否经过钩子）
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mousewheel.platform.win.winapi import (  # noqa: E402
    HOOKPROC,
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF,
    MSG,
    MSLLHOOKSTRUCT,
    MOUSEINPUT,
    WH_MOUSE_LL,
    WM,
    cursor_pos,
    kernel32,
    user32,
)

hits: list[str] = []
all_msgs: list[str] = []


def _hook_proc(n_code: int, wparam: int, lparam: int):
    if n_code >= 0:
        data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        msg = int(wparam)
        flags = int(data.flags)
        all_msgs.append(f"0x{msg:X}")
        if msg in (WM.XBUTTONDOWN, WM.XBUTTONUP):
            hits.append(f"xbutton 0x{msg:X}/0x{int(data.mouseData):X} flags=0x{flags:X}")
        elif msg in (WM.MBUTTONDOWN, WM.MBUTTONUP):
            hits.append(f"middle  0x{msg:X} flags=0x{flags:X}")
    return user32.CallNextHookEx(None, n_code, wparam, lparam)


def _inject(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> int:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
    arr = (INPUT * 1)(inp)
    return int(user32.SendInput(1, arr, ctypes.sizeof(INPUT)))


def is_appcontainer() -> str:
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.OpenProcessToken.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        token = ctypes.c_void_p()
        if not kernel32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)  # TOKEN_QUERY
        ):
            return f"无法打开令牌（错误 {ctypes.get_last_error()}）"
        is_ac = ctypes.c_int(0)
        size = ctypes.c_uint32(0)
        ok = advapi32.GetTokenInformation(
            token, 29, ctypes.byref(is_ac), ctypes.sizeof(is_ac), ctypes.byref(size)  # TokenIsAppContainer
        )
        kernel32.CloseHandle(token)
        if not ok:
            return f"GetTokenInformation 失败（错误 {ctypes.get_last_error()}）"
        return "是 AppContainer（沙箱）" if is_ac.value else "否（普通进程）"
    except Exception as exc:  # pragma: no cover
        return f"检查失败: {exc}"


def main() -> int:
    print(f"AppContainer: {is_appcontainer()}")

    before = cursor_pos()
    sent = _inject(MOUSEEVENTF.MOVE, dx=10, dy=0)
    time.sleep(0.15)
    after = cursor_pos()
    print(f"注入移动：SendInput={sent} 光标 {before} -> {after} 变化={after[0] - before[0]}")
    _inject(MOUSEEVENTF.MOVE, dx=-10, dy=0)
    time.sleep(0.1)

    callback = HOOKPROC(_hook_proc)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, kernel32.GetModuleHandleW(None), 0)
    print(f"钩子句柄={hook}")
    if hook:
        msg = MSG()

        def pump(seconds: float) -> None:
            deadline = time.time() + seconds
            while time.time() < deadline:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.004)

        print("--- 注入 移动 ---")
        _inject(MOUSEEVENTF.MOVE, dx=6, dy=0)
        pump(0.25)
        print(f"  钩子消息数={len(all_msgs)}")

        print("--- 注入 中键 ---")
        print(f"  down send={_inject(MOUSEEVENTF.MIDDLEDOWN)}")
        pump(0.2)
        print(f"  up   send={_inject(MOUSEEVENTF.MIDDLEUP)}")
        pump(0.25)

        print("--- 注入 X1 ---")
        print(f"  down send={_inject(MOUSEEVENTF.XDOWN, data=1 << 16)}")
        pump(0.2)
        print(f"  up   send={_inject(MOUSEEVENTF.XUP, data=1 << 16)}")
        pump(0.25)

        user32.UnhookWindowsHookEx(hook)

    print(f"钩子收到的按钮事件：{hits if hits else '无'}")
    print(f"钩子消息总量：{len(all_msgs)} 条，类型：{sorted(set(all_msgs))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
