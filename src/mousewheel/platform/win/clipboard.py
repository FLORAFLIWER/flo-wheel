"""Win32 剪贴板读写（CF_UNICODETEXT）。

不用 Qt 的 QClipboard 是因为动作在线程池里执行，而 QClipboard 只能在 GUI
线程使用。Win32 版本在任意线程可用，代价是必须自己管理内存和重试。
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .winapi import kernel32, user32

__all__ = ["get_clipboard_text", "set_clipboard_text", "CF_UNICODETEXT"]

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
kernel32.GlobalSize.restype = ctypes.c_size_t


def _open(retries: int = 8, delay: float = 0.02) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def get_clipboard_text() -> str | None:
    """读取剪贴板文本；剪贴板里不是文本或打不开时返回 None。"""
    if not _open():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    """把文本写入剪贴板（失败会重试，Windows 剪贴板经常被别的程序占用）。"""
    if not _open():
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, buf, size)
        finally:
            kernel32.GlobalUnlock(handle)
        # SetClipboardData 成功后所有权移交系统，不能再 GlobalFree
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        return True
    finally:
        user32.CloseClipboard()
