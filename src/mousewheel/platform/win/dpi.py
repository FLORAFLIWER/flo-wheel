"""DPI 感知。

必须在 ``QApplication`` 创建之前调用 :func:`enable`，否则 Qt 已经按旧的
DPI 策略初始化完毕，再改就晚了（表现为轮盘大小 / 位置不对）。
"""

from __future__ import annotations

from .winapi import set_dpi_awareness

__all__ = ["enable"]

_enabled = False


def enable() -> None:
    global _enabled
    if _enabled:
        return
    set_dpi_awareness()
    _enabled = True
