"""可选功能：用键盘热键触发轮盘（RegisterHotKey）。

**当前版本未使用**：键盘触发键改为 `input.key_hook` + `input.key_combo`
（低级键盘钩子），因为 RegisterHotKey 只能通知"按下"、拿不到"松开"，
做不出「按住弹出、松开执行」的手感。这个实现保留下来，将来若要"单击开关"
模式可以直接用。

为什么用 RegisterHotKey 而不是键盘钩子：注册一个热键不会拖慢所有键盘输入，
而且不需要挂全局钩子。代价是这个组合会被本程序独占，注册失败时说明已被
别的软件占用（会提示用户换一个）。
"""

from __future__ import annotations

import ctypes
import logging

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
from PySide6.QtWidgets import QWidget

from .winapi import MSG, WM, user32, wintypes

__all__ = ["GlobalHotkey", "HotkeyError_", "HotkeyRegistrationError"]

log = logging.getLogger(__name__)

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

_MOD_BY_NAME = {
    "alt": _MOD_ALT,
    "ctrl": _MOD_CONTROL,
    "shift": _MOD_SHIFT,
    "win": _MOD_WIN,
}

_HOTKEY_ID = 0x4D57  # 'MW'

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL


class HotkeyRegistrationError(RuntimeError):
    pass


#: 兼容别名（旧名字带下划线，避免与 hotkey_spec.HotkeyError 混淆）
HotkeyError_ = HotkeyRegistrationError


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkey") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt 命名
        try:
            et = event_type.decode() if isinstance(event_type, (bytes, bytearray)) else str(event_type)
            if et == "windows_generic_MSG":
                msg = MSG.from_address(int(message))
                if msg.message == WM.HOTKEY and int(msg.wParam) == _HOTKEY_ID:
                    self._owner._fire()
                    return True, 0
        except Exception:  # pragma: no cover - 任何异常都不能影响输入
            log.exception("hotkey filter 异常")
        return False, 0


class GlobalHotkey:
    """注册一个系统级热键，触发时调用 ``callback``。"""

    def __init__(self, callback) -> None:
        self._callback = callback
        self._hwnd: int = 0
        self._registered = False
        self._window: QWidget | None = None
        self._filter: _Filter | None = None
        self._app = QCoreApplication.instance()

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self, spec) -> bool:
        """``spec`` 是 :class:`hotkey_spec.HotkeySpec`。返回是否注册成功。"""
        self.unregister()
        if self._window is None:
            self._window = QWidget()
            self._window.setWindowTitle("MouseWheelHotkeySink")
            self._window.resize(1, 1)
            self._hwnd = int(self._window.winId())
        if self._filter is None:
            self._filter = _Filter(self)
            if self._app is not None:
                self._app.installNativeEventFilter(self._filter)

        mods = _MOD_NOREPEAT
        for name in spec.mods:
            mods |= _MOD_BY_NAME.get(name, 0)
        ok = user32.RegisterHotKey(self._hwnd, _HOTKEY_ID, mods, spec.vk)
        if not ok:
            raise HotkeyRegistrationError(
                f"无法注册热键 {spec.source}，可能已被其它程序占用"
            )
        self._registered = True
        return True

    def unregister(self) -> None:
        if self._hwnd:
            user32.UnregisterHotKey(self._hwnd, _HOTKEY_ID)
        self._registered = False

    def _fire(self) -> None:
        try:
            self._callback()
        except Exception:  # pragma: no cover
            log.exception("热键回调异常")

    def dispose(self) -> None:
        self.unregister()
        if self._filter is not None and self._app is not None:
            try:
                self._app.removeNativeEventFilter(self._filter)
            except Exception:
                pass
            self._filter = None
        if self._window is not None:
            self._window.deleteLater()
            self._window = None
