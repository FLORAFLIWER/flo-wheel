"""组合键跟踪：判断"整组键是否按住"，用来做按住弹出、松开执行。

与 :class:`input.trigger.TriggerController` 的区别：
- TriggerController 管的是**轮盘的生命周期**（还没到长按阈值、已弹出、取消…）
- KeyComboTracker 只管**这一组键现在是不是全按着**

把两者分开的好处是都可以单独测试 —— 组合键判定最容易出错的地方
（提前松开某个修饰键、按键自动重复、左右 Ctrl 混用）在纯逻辑里就能覆盖。
"""

from __future__ import annotations

from .hotkey_spec import normalize_vk

__all__ = ["KeyComboTracker"]


class KeyComboTracker:
    """跟踪一组虚拟键是否同时按下。

    用法::

        tracker = KeyComboTracker(spec.modifier_vks, spec.vk)
        if tracker.on_down(vk):   # 整组刚刚按下 → 开始
            ...
        if tracker.on_up(vk):     # 任一键松开 → 结束
            ...
    """

    def __init__(self, mods: list[int] | tuple[int, ...], main_vk: int) -> None:
        self._needed = {normalize_vk(vk) for vk in mods} | {normalize_vk(main_vk)}
        self._pressed: set[int] = set()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def needed(self) -> frozenset[int]:
        """关心的键集合（钩子线程用它做过滤，避免为每个按键都投递一次）。"""
        return frozenset(self._needed)

    def reset(self) -> None:
        self._pressed.clear()
        self._active = False

    def on_down(self, vk: int, recurring: bool = False) -> bool:
        """处理按下。返回 True 表示**整组键刚刚凑齐**（只在那一刻返回一次）。

        ``recurring=True`` 表示系统自动重复（按住不放时不断发 keydown），
        这种情况绝不能再触发一次。
        """
        vk = normalize_vk(vk)
        if vk not in self._needed:
            return False
        if recurring:
            return False
        self._pressed.add(vk)
        if self._active:
            return False
        if self._needed <= self._pressed:
            self._active = True
            return True
        return False

    def on_up(self, vk: int) -> bool:
        """处理松开。返回 True 表示组合刚刚结束（任一键松开即结束）。"""
        vk = normalize_vk(vk)
        if vk not in self._needed:
            return False
        self._pressed.discard(vk)
        if self._active:
            self._active = False
            return True
        return False
