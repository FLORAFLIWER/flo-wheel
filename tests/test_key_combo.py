"""组合键跟踪测试。

这里覆盖的都是"按住触发键没反应 / 松早了没结束"的典型原因：
左右 Ctrl 混用、按键自动重复、提前松开修饰键。
"""

from __future__ import annotations

from mousewheel.input.key_combo import KeyComboTracker
from mousewheel.platform.win.winapi import VK


def tracker() -> KeyComboTracker:
    return KeyComboTracker([VK.CONTROL, VK.MENU], ord("Q"))


def test_full_combo_fires_once() -> None:
    t = tracker()
    assert t.on_down(VK.CONTROL) is False
    assert t.on_down(VK.MENU) is False
    assert t.on_down(ord("Q")) is True
    assert t.active


def test_auto_repeat_does_not_retrigger() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    t.on_down(VK.MENU)
    t.on_down(ord("Q"))
    assert t.on_down(ord("Q")) is False
    assert t.on_down(VK.CONTROL) is False


def test_releasing_any_key_ends_combo() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    t.on_down(VK.MENU)
    t.on_down(ord("Q"))
    assert t.on_up(VK.CONTROL) is True
    assert not t.active


def test_left_ctrl_from_hook_is_accepted() -> None:
    """低级键盘钩子送来的是 LCONTROL(0xA2)，配置里写的是通用 CONTROL。"""
    t = tracker()
    t.on_down(VK.LCONTROL)
    t.on_down(VK.MENU)
    assert t.on_down(ord("Q")) is True


def test_right_alt_from_hook_is_accepted() -> None:
    t = KeyComboTracker([VK.MENU], ord("X"))
    t.on_down(VK.RMENU)
    assert t.on_down(ord("X")) is True


def test_partial_combo_does_nothing() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    assert t.on_down(ord("Q")) is False
    assert not t.active


def test_unrelated_keys_are_ignored() -> None:
    t = tracker()
    assert t.on_down(ord("Z")) is False
    assert t.on_up(ord("Z")) is False


def test_can_retrigger_while_modifiers_held() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    t.on_down(VK.MENU)
    t.on_down(ord("Q"))
    t.on_up(ord("Q"))
    # Ctrl/Alt 还按着，再敲一次 Q 应该重新触发
    assert t.on_down(ord("Q")) is True


def test_release_without_activation_does_not_fire() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    assert t.on_up(VK.CONTROL) is False


def test_needed_is_normalized_set() -> None:
    t = tracker()
    assert t.needed == frozenset({VK.CONTROL, VK.MENU, ord("Q")})


def test_recurring_flag_is_ignored() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    t.on_down(VK.MENU)
    assert t.on_down(ord("Q"), recurring=True) is False
    assert not t.active


def test_reset_clears_state() -> None:
    t = tracker()
    t.on_down(VK.CONTROL)
    t.on_down(VK.MENU)
    t.on_down(ord("Q"))
    t.reset()
    assert not t.active
    assert t.on_down(ord("Q")) is False
