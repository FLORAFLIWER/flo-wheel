"""触发状态机测试。

这是整个程序最核心的判定逻辑：既要"按住才弹"，又要"快击不误触发"。
"""

from __future__ import annotations

from mousewheel.input.trigger import TriggerConfig, TriggerController, TriggerEvent


def make(button: str = "x1", mode: str = "hold", long_press_ms: int = 180) -> TriggerController:
    return TriggerController(
        TriggerConfig(button=button, mode=mode, long_press_ms=long_press_ms)
    )


def test_hold_opens_after_threshold() -> None:
    c = make()
    assert c.on_mouse_down("x1", 10.000) is TriggerEvent.NONE
    assert c.state == "pending"
    assert c.on_tick(10.100) is TriggerEvent.NONE
    assert c.on_tick(10.181) is TriggerEvent.OPEN
    assert c.state == "open"


def test_fast_click_passes_through() -> None:
    c = make()
    c.on_mouse_down("x1", 10.000)
    assert c.on_mouse_up("x1", 10.090) is TriggerEvent.PASS_CLICK
    assert c.state == "idle"


def test_fast_click_without_passthrough_is_swallowed() -> None:
    c = TriggerController(
        TriggerConfig(button="x1", fast_click_passthrough=False)
    )
    c.on_mouse_down("x1", 10.0)
    assert c.on_mouse_up("x1", 10.05) is TriggerEvent.NONE


def test_release_with_selection_commits() -> None:
    c = make()
    c.on_mouse_down("x1", 10.0)
    assert c.on_tick(10.3) is TriggerEvent.OPEN
    assert c.on_mouse_up("x1", 10.4, selected=2) is TriggerEvent.RELEASE


def test_release_without_selection_cancels() -> None:
    c = make()
    c.on_mouse_down("x1", 10.0)
    c.on_tick(10.3)
    assert c.on_mouse_up("x1", 10.4, selected=None) is TriggerEvent.CANCEL


def test_other_buttons_are_ignored() -> None:
    c = make(button="x1")
    assert c.on_mouse_down("x2", 10.0) is TriggerEvent.NONE
    assert c.on_tick(10.5) is TriggerEvent.NONE
    assert c.state == "idle"


def test_disabled_trigger_matches_nothing() -> None:
    c = make(button="none")
    assert c.on_mouse_down("x1", 10.0) is TriggerEvent.NONE
    assert not c.matches("x1")


def test_guard_blocks_double_trigger() -> None:
    """松开后 40ms 内的重复按下视为抖动。"""
    c = make()
    c.on_mouse_down("x1", 10.0)
    c.on_mouse_up("x1", 10.05)  # 快击
    assert c.on_mouse_down("x1", 10.06) is TriggerEvent.NONE
    assert c.state == "idle"
    # 过了保护期就正常
    c.on_mouse_down("x1", 10.20)
    assert c.state == "pending"


def test_toggle_mode_opens_on_press_and_commits_on_second_press() -> None:
    c = make(mode="toggle")
    assert c.on_mouse_down("x1", 10.0) is TriggerEvent.OPEN
    assert c.on_mouse_up("x1", 10.05) is TriggerEvent.NONE
    assert c.state == "open"
    assert c.on_mouse_down("x1", 10.5) is TriggerEvent.RELEASE
    assert c.state == "idle"


def test_escape_cancels_open_wheel() -> None:
    c = make()
    c.on_mouse_down("x1", 10.0)
    c.on_tick(10.3)
    assert c.on_escape() is TriggerEvent.CANCEL
    assert c.state == "idle"
    # 已经关闭后再按 Esc 没有副作用
    assert c.on_escape() is TriggerEvent.NONE


def test_tick_before_threshold_keeps_pending() -> None:
    c = make(long_press_ms=200)
    c.on_mouse_down("x1", 0.0)
    for ms in range(0, 200, 10):
        assert c.on_tick(ms / 1000.0) is TriggerEvent.NONE
    assert c.on_tick(0.201) is TriggerEvent.OPEN


def test_reset_clears_state() -> None:
    c = make()
    c.on_mouse_down("x1", 1.0)
    c.reset()
    assert c.state == "idle"
    assert c.on_tick(5.0) is TriggerEvent.NONE


# ---- 键盘触发键（按住弹出、松开执行） ------------------------------------


def test_keyboard_hold_opens_after_threshold() -> None:
    c = make()
    assert c.on_key_down(10.000) is TriggerEvent.NONE
    assert c.on_tick(10.100) is TriggerEvent.NONE
    assert c.on_tick(10.200) is TriggerEvent.OPEN
    assert c.state == "open"


def test_keyboard_release_commits_selection() -> None:
    c = make()
    c.on_key_down(10.0)
    assert c.on_tick(10.3) is TriggerEvent.OPEN
    assert c.on_key_up(10.4, selected=2) is TriggerEvent.RELEASE


def test_keyboard_short_press_never_replays_mouse_click() -> None:
    """键盘没有"原点击"可重放，绝不能返回 PASS_CLICK。"""
    c = make()
    c.on_key_down(10.0)
    assert c.on_key_up(10.05) is TriggerEvent.NONE


def test_keyboard_release_without_selection_cancels() -> None:
    c = make()
    c.on_key_down(10.0)
    c.on_tick(10.3)
    assert c.on_key_up(10.4, selected=None) is TriggerEvent.CANCEL


def test_keyboard_and_mouse_share_the_same_state() -> None:
    c = make()
    c.on_mouse_down("x1", 10.0)
    # 鼠标还按着时键盘又来一次，不应该把状态搞乱
    assert c.on_key_down(10.05) is TriggerEvent.NONE
    assert c.on_tick(10.3) is TriggerEvent.OPEN
    assert c.on_key_up(10.35, selected=0) is TriggerEvent.RELEASE
    assert c.state == "idle"
