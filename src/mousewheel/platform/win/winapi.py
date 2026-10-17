"""Win32 API 的 ctypes 绑定（只包含本项目用到的部分）。

这个模块是全项目的底座：钩子、注入、窗口、自启动都依赖这里。
所有结构体布局按 64 位 Windows 定义，改动前务必核对 MSDN。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

__all__ = [
    "user32", "kernel32", "shcore",
    "POINT", "RECT", "MSG", "MSLLHOOKSTRUCT", "KBDLLHOOKSTRUCT", "INPUT",
    "MAGIC_EXTRA_INFO", "LRESULT", "ULONG_PTR", "HOOKPROC",
    "WM_", "VK", "MOUSEEVENTF", "KEYEVENTF", "XBUTTON",
]

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HHOOK = ctypes.c_void_p
HANDLE = ctypes.c_void_p

#: 注入事件统一携带的标记，钩子见到它就直接放行，避免自己吞掉自己发出的事件
MAGIC_EXTRA_INFO = 0x1CEB00DA
#: 本程序注入事件时用的第二个标记位（区分"用户按键"与"程序按键"）
INJECT_FLAG = 0x4D575748

POINT = wintypes.POINT
RECT = wintypes.RECT


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WM:
    """本项目用到的窗口消息"""

    MOUSEMOVE = 0x0200
    LBUTTONDOWN = 0x0201
    LBUTTONUP = 0x0202
    RBUTTONDOWN = 0x0204
    RBUTTONUP = 0x0205
    MBUTTONDOWN = 0x0207
    MBUTTONUP = 0x0208
    MOUSEWHEEL = 0x020A
    XBUTTONDOWN = 0x020B
    XBUTTONUP = 0x020C
    KEYDOWN = 0x0100
    KEYUP = 0x0101
    SYSKEYDOWN = 0x0104
    SYSKEYUP = 0x0105
    HOTKEY = 0x0312
    QUIT = 0x0012


WM_ = WM


class VK:
    """虚拟键码"""

    BACK = 0x08
    TAB = 0x09
    RETURN = 0x0D
    SHIFT = 0x10
    CONTROL = 0x11
    MENU = 0x12  # Alt
    PAUSE = 0x13
    CAPITAL = 0x14  # CapsLock
    ESCAPE = 0x1B
    SPACE = 0x20
    PRIOR = 0x21  # PageUp
    NEXT = 0x22  # PageDown
    END = 0x23
    HOME = 0x24
    LEFT = 0x25
    UP = 0x26
    RIGHT = 0x27
    DOWN = 0x28
    SNAPSHOT = 0x2C  # PrintScreen
    INSERT = 0x2D
    DELETE = 0x2E
    LWIN = 0x5B
    RWIN = 0x5C
    APPS = 0x5D
    NUMPAD0 = 0x60
    MULTIPLY = 0x6A
    ADD = 0x6B
    SUBTRACT = 0x6D
    DECIMAL = 0x6E
    DIVIDE = 0x6F
    F1 = 0x70
    F24 = 0x87
    NUMLOCK = 0x90
    SCROLL = 0x91
    LSHIFT = 0xA0
    RSHIFT = 0xA1
    LCONTROL = 0xA2
    RCONTROL = 0xA3
    LMENU = 0xA4
    RMENU = 0xA5
    OEM_1 = 0xBA  # ;
    OEM_PLUS = 0xBB  # =
    OEM_COMMA = 0xBC  # ,
    OEM_MINUS = 0xBD  # -
    OEM_PERIOD = 0xBE  # .
    OEM_2 = 0xBF  # /
    OEM_3 = 0xC0  # `
    OEM_4 = 0xDB  # [
    OEM_5 = 0xDC  # \
    OEM_6 = 0xDD  # ]
    OEM_7 = 0xDE  # '
    VOLUME_MUTE = 0xAD
    VOLUME_DOWN = 0xAE
    VOLUME_UP = 0xAF
    MEDIA_NEXT_TRACK = 0xB0
    MEDIA_PREV_TRACK = 0xB1
    MEDIA_STOP = 0xB2
    MEDIA_PLAY_PAUSE = 0xB3


VK = VK


class MOUSEEVENTF:
    MOVE = 0x0001
    LEFTDOWN = 0x0002
    LEFTUP = 0x0004
    RIGHTDOWN = 0x0008
    RIGHTUP = 0x0010
    MIDDLEDOWN = 0x0020
    MIDDLEUP = 0x0040
    XDOWN = 0x0080
    XUP = 0x0100
    WHEEL = 0x0800


MOUSEEVENTF = MOUSEEVENTF


class KEYEVENTF:
    EXTENDEDKEY = 0x0001
    KEYUP = 0x0002
    UNICODE = 0x0004
    SCANCODE = 0x0008


KEYEVENTF = KEYEVENTF


class XBUTTON:
    X1 = 1
    X2 = 2


XBUTTON = XBUTTON

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
MAPVK_VK_TO_VSC = 0
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

# ---- 函数原型 -------------------------------------------------------------

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = HHOOK

user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = HANDLE


def set_dpi_awareness() -> None:
    """Per-Monitor V2 DPI 感知。必须早于 QApplication 创建，否则失效。"""
    try:
        user32.SetProcessDpiAwarenessContext  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        ctx = ctypes.c_void_p(-4)
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctx)
    except Exception:  # pragma: no cover - 老系统兜底
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            pass


def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(hwnd, buf, n + 2)
    return buf.value


def cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y
