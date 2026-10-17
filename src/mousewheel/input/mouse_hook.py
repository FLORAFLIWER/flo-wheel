"""全局低级鼠标钩子（WH_MOUSE_LL）。

只做一件事：判断这个鼠标事件是不是触发键，是就吞掉并投递给主线程。
**任何耗时的逻辑都不许写在这里** —— 回调超过系统 LowLevelHooksTimeout
（默认 300ms）后 Windows 会静默摘掉钩子，表现出来就是"用着用着失效了"。
"""

from __future__ import annotations

import ctypes
import logging
import time

from PySide6.QtCore import QThread, Signal

from ..platform.win.winapi import (
    HOOKPROC,
    MAGIC_EXTRA_INFO,
    MSLLHOOKSTRUCT,
    MSG,
    VK,
    WH_MOUSE_LL,
    WM,
    kernel32,
    user32,
)

__all__ = ["MouseHookThread", "BUTTONS"]

log = logging.getLogger(__name__)

#: 我们支持的鼠标键名（与配置里的字符串一致）
BUTTONS = ("x1", "x2", "middle", "right", "left")

_DOWN_MSGS = {WM.LBUTTONDOWN, WM.RBUTTONDOWN, WM.MBUTTONDOWN, WM.XBUTTONDOWN}
_UP_MSGS = {WM.LBUTTONUP, WM.RBUTTONUP, WM.MBUTTONUP, WM.XBUTTONUP}

_DOWN_TO_BUTTON = {
    WM.LBUTTONDOWN: "left",
    WM.RBUTTONDOWN: "right",
    WM.MBUTTONDOWN: "middle",
}
_UP_TO_BUTTON = {
    WM.LBUTTONUP: "left",
    WM.RBUTTONUP: "right",
    WM.MBUTTONUP: "middle",
}


class MouseHookThread(QThread):
    """运行消息循环并持有 WH_MOUSE_LL 的线程。

    信号 ``mouse_event(kind, button)`` 只会为**触发键**发出，且该事件已经被
    吞掉（钩子返回 1），所以系统不会收到原始按键，需要时由上层重放。
    """

    mouse_event = Signal(str, str)  # ("down"|"up", "x1")
    diagnostic_event = Signal(str, str)  # 诊断模式：所有按钮事件都投递
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 主线程随时可改；钩子线程只读一个字符串，开销可忽略
        self.trigger_button: str = "x1"
        #: 诊断模式：投递**所有**鼠标键事件，且一个都不吞（不影响鼠标正常使用）
        self.diagnose: bool = False
        self._hook = None
        self._thread_id = 0
        self._proc = None
        self._last_err = 0
        # 回调耗时统计（秒），主线程可随时读
        self.max_callback_ms = 0.0
        self.callback_count = 0
        self.total_events = 0
        self._xbtn_logged = 0
        self._errors = 0

    # ---- Qt 线程入口 ------------------------------------------------------

    def run(self) -> None:  # noqa: D401 - QThread 约定
        self._thread_id = int(kernel32.GetCurrentThreadId())
        # 低级钩子要求线程有消息队列；GetMessage 会创建它，但显式先创建一次更稳
        user32.PeekMessageW(None, None, 0, 0, 0)
        self._proc = HOOKPROC(self._callback)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, hmod, 0)
        if not self._hook:
            self._last_err = ctypes.get_last_error()
            log.error("SetWindowsHookEx(WH_MOUSE_LL) 失败，错误码 %s", self._last_err)
            self.failed.emit(f"SetWindowsHookEx WH_MOUSE_LL 失败，错误码 {self._last_err}")
            return

        log.info("鼠标钩子已安装（线程 %s）", self._thread_id)
        msg = MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                log.info("钩子消息循环结束：GetMessage 返回 %s，错误 %s", ret, ctypes.get_last_error())
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            log.info("鼠标钩子已卸载")

    def stop(self, timeout_ms: int = 2000) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM.QUIT, 0, 0)
        self.wait(timeout_ms)

    # ---- 钩子回调（在钩子线程被系统调用） --------------------------------

    def _callback(self, n_code: int, wparam: int, lparam: int):
        started = time.perf_counter()
        try:
            if n_code < 0:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            self.total_events += 1
            data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            extra = int(data.dwExtraInfo)
            if extra == MAGIC_EXTRA_INFO:
                # 自己注入的事件，直接放行，否则会自吞/递归
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            msg = int(wparam)
            if msg in (WM.XBUTTONDOWN, WM.XBUTTONUP) and self._xbtn_logged < 6:
                self._xbtn_logged += 1
                log.info(
                    "收到 XButton 事件 msg=0x%X mouseData=0x%X trigger=%r",
                    msg,
                    int(data.mouseData),
                    self.trigger_button,
                )
            button = None
            kind = ""
            if msg in _DOWN_MSGS:
                kind = "down"
                if msg == WM.XBUTTONDOWN:
                    which = (int(data.mouseData) >> 16) & 0xFFFF
                    button = "x1" if which == 1 else ("x2" if which == 2 else None)
                else:
                    button = _DOWN_TO_BUTTON.get(msg)
            elif msg in _UP_MSGS:
                kind = "up"
                if msg == WM.XBUTTONUP:
                    which = (int(data.mouseData) >> 16) & 0xFFFF
                    button = "x1" if which == 1 else ("x2" if which == 2 else None)
                else:
                    button = _UP_TO_BUTTON.get(msg)

            if button is None:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            if self.diagnose:
                # 诊断模式：全部投递，且不吞任何键，保证鼠标功能不受影响
                self.diagnostic_event.emit(kind, button)
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            if button != self.trigger_button:
                return user32.CallNextHookEx(None, n_code, wparam, lparam)

            if self.callback_count < 6:
                log.debug("钩子命中 %s %s (trigger=%r)", kind, button, self.trigger_button)
            # 只投递，不在这里做任何判定/IO
            self.mouse_event.emit(kind, button)
            return 1  # 吞掉：需要的点击由上层用 SendInput 重放
        except Exception:
            # 回调里绝不能抛异常出去，否则钩子会被系统干掉。
            # 但也不能完全静默，否则出问题时无从排查。
            self._errors += 1
            if self._errors <= 3:
                log.exception("钩子回调异常（事件已放行，第 %s 次）", self._errors)
            return user32.CallNextHookEx(None, n_code, wparam, lparam)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.callback_count += 1
            if elapsed_ms > self.max_callback_ms:
                self.max_callback_ms = elapsed_ms
