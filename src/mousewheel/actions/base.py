"""动作执行上下文与结果。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from ..platform.win.winapi import get_foreground_window, user32

__all__ = ["ActionContext", "ActionResult", "ensure_foreground"]


@dataclass
class ActionContext:
    """执行动作时需要的环境信息。"""

    foreground_hwnd: int = 0
    dry_run: bool = False


@dataclass
class ActionResult:
    ok: bool
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


def ensure_foreground(hwnd: int) -> bool:
    """确保按键能发到预期的窗口。

    我们的轮盘窗口不激活、不抢焦点，正常情况下前台窗口根本没变；
    所以这里的策略是**只补不抢**：
    - 前台还是那个窗口 → 什么都不做
    - 前台变成了"没有窗口"(0) → 把原窗口拉回来
    - 用户自己切到了别的窗口 → 尊重用户，把按键发给他当前用的窗口
    """
    if not hwnd:
        return False
    current = get_foreground_window()
    if current == hwnd:
        return True
    if current == 0:
        try:
            user32.SetForegroundWindow(hwnd)
        except Exception:
            return False
        return get_foreground_window() == hwnd
    return True


@contextmanager
def keep_foreground(ctx: ActionContext):
    ensure_foreground(ctx.foreground_hwnd)
    yield
