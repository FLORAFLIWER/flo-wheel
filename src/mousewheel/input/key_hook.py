"""全局低级键盘钩子（WH_KEYBOARD_LL），只用于"键盘触发键"。

为什么不用 ``RegisterHotKey``：它只能通知"按下了"，拿不到"松开了"，
而我们要的是「按住弹出、松开执行」，必须成对知道按下和松开。

这个钩子**从不吞键**（永远 CallNextHookEx）：只观察，不改变任何程序的输入行为。
为了把开销压到最低，只投递用户配置里那几个键的事件，其余直接放行。
"""

from __future__ import annotations

import ctypes
import logging
import time

from PySide6.QtCore import QThread, Signal

from ..platform.win.winapi import (
    HOOKPROC,
    KBDLLHOOKSTRUCT,
    MAGIC_EXTRA_INFO,
    MSG,
    WH_KEYBOARD_LL,
    WM,
    kernel32,
    user32,
)
from .hotkey_spec import normalize_vk

__all__ = ["KeyHookThread"]

log = logging.getLogger(__name__)


class KeyHookThread(QThread):
    """持有 WH_KEYBOARD_LL 的线程。信号 ``key_event(kind, vk)``，vk 已归一化。"""

    key_event = Signal(str, int)  # ("down"|"up", vk)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        #: 只关心这些键（主线程更新）；空集合表示啥也不投递
        self.interest: frozenset[int] = frozenset()
        self._hook = None
        self._thread_id = 0
        self._proc = None
        self._down: set[int] = set()
        self._errors = 0
        self.max_callback_ms = 0.0

    # ---- 生命周期 --------------------------------------------------------

    def run(self) -> None:  # noqa: D401
        self._thread_id = int(kernel32.GetCurrentThreadId())
        user32.PeekMessageW(None, None, 0, 0, 0)
        self._proc = HOOKPROC(self._callback)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hmod, 0)
        if not self._hook:
            err = ctypes.get_last_error()
            log.error("SetWindowsHookEx(WH_KEYBOARD_LL) 失败，错误码 %s", err)
            self.failed.emit(f"键盘钩子安装失败，错误码 {err}")
            return

        log.info("键盘钩子已安装（线程 %s）", self._thread_id)
        msg = MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            log.info("键盘钩子已卸载")

    def stop(self, timeout_ms: int = 2000) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM.QUIT, 0, 0)
        self.wait(timeout_ms)
        self._down.clear()

    # ---- 回调 ------------------------------------------------------------

    def _callback(self, n_code: int, wparam: int, lparam: int):
        started = time.perf_counter()
        try:
            if n_code < 0:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if int(data.dwExtraInfo) == MAGIC_EXTRA_INFO:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            vk = normalize_vk(int(data.vkCode))
            if vk not in self.interest:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            msg = int(wparam)
            if msg in (WM.KEYDOWN, WM.SYSKEYDOWN):
                if vk in self._down:
                    # 按住不放时系统会不断重发 keydown，这里直接忽略
                    return user32.CallNextHookEx(None, n_code, wparam, lparam)
                self._down.add(vk)
                self.key_event.emit("down", vk)
            elif msg in (WM.KEYUP, WM.SYSKEYUP):
                self._down.discard(vk)
                self.key_event.emit("up", vk)
        except Exception:
            self._errors += 1
            if self._errors <= 3:
                log.exception("键盘钩子回调异常（第 %s 次）", self._errors)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if elapsed_ms > self.max_callback_ms:
                self.max_callback_ms = elapsed_ms

        # 永远放行：我们只是观察，不改变键盘行为
        return user32.CallNextHookEx(None, n_code, wparam, lparam)
