"""触发状态机：把原始鼠标/键盘事件翻译成"开轮盘 / 放行点击 / 提交 / 取消"。

纯逻辑，不依赖 Qt 和 Win32，因此可以完整单测。时间由调用方注入（``now``），
测试里可以直接喂数字，不需要真的等 180 毫秒。

状态图（hold 模式，以触发键为 X1 为例）::

    IDLE --down--> PENDING --超时--> OPEN --up--> IDLE (RELEASE)
                      |                  |
                      +--up--> IDLE       +--Esc--> IDLE (CANCEL)
                     (PASS_CLICK)

toggle 模式没有 PENDING：down 立即 OPEN，再按一次 down 收尾。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = ["TriggerEvent", "TriggerController", "TriggerConfig"]


class TriggerEvent(Enum):
    NONE = "none"
    OPEN = "open"            # 该显示轮盘了
    PASS_CLICK = "pass"      # 快击：把点击重放给系统
    RELEASE = "release"      # 松手：上层根据当前选中决定执行/取消
    CANCEL = "cancel"        # Esc 或配置变化：取消


class _State(Enum):
    IDLE = "idle"
    PENDING = "pending"
    OPEN = "open"


#: 松开后这段时间内的重复按下视为抖动（防止双击触发两次）
DEFAULT_GUARD_MS = 40


@dataclass
class TriggerConfig:
    button: str = "x1"
    mode: str = "hold"  # hold | toggle
    long_press_ms: int = 180
    fast_click_passthrough: bool = True
    guard_ms: int = DEFAULT_GUARD_MS


@dataclass
class TriggerController:
    config: TriggerConfig = field(default_factory=TriggerConfig)

    _state: _State = field(default=_State.IDLE, init=False)
    _down_at: float = field(default=0.0, init=False)
    _last_release_at: float = field(default=-1e9, init=False)

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def is_open(self) -> bool:
        return self._state is _State.OPEN

    def matches(self, button: str) -> bool:
        return bool(self.config.button) and self.config.button != "none" and button == self.config.button

    # ---- 事件入口 ---------------------------------------------------------

    def on_mouse_down(self, button: str, now: float) -> TriggerEvent:
        if not self.matches(button):
            return TriggerEvent.NONE
        return self.on_press(now)

    def on_mouse_up(self, button: str, now: float, selected: int | None = None) -> TriggerEvent:
        if not self.matches(button):
            return TriggerEvent.NONE
        return self.on_release(now, selected, passthrough=True)

    # 键盘触发键（组合键按住/松开）走同一套状态机，只是不做"点击重放"

    def on_key_down(self, now: float) -> TriggerEvent:
        return self.on_press(now)

    def on_key_up(self, now: float, selected: int | None = None) -> TriggerEvent:
        return self.on_release(now, selected, passthrough=False)

    # ---- 与触发来源无关的核心逻辑 ----------------------------------------

    def on_press(self, now: float) -> TriggerEvent:
        """触发源按下（鼠标键或键盘组合，由调用方过滤）。"""
        if self.config.mode == "toggle":
            if self._state is _State.OPEN:
                self._state = _State.IDLE
                self._last_release_at = now
                return TriggerEvent.RELEASE
            if now - self._last_release_at < self.config.guard_ms / 1000.0:
                return TriggerEvent.NONE
            self._state = _State.OPEN
            self._down_at = now
            return TriggerEvent.OPEN

        # hold 模式：先进入 PENDING，等长按超时再开
        if self._state is _State.OPEN:
            return TriggerEvent.NONE
        if self._state is _State.PENDING:
            return TriggerEvent.NONE
        if now - self._last_release_at < self.config.guard_ms / 1000.0:
            return TriggerEvent.NONE
        self._state = _State.PENDING
        self._down_at = now
        return TriggerEvent.NONE

    def on_release(
        self,
        now: float,
        selected: int | None = None,
        passthrough: bool = True,
    ) -> TriggerEvent:
        """触发源松开。``passthrough`` 控制"没到阈值就松开"时是否要重放原点击。"""
        if self.config.mode == "toggle":
            return TriggerEvent.NONE  # toggle 模式靠再按一次收尾

        if self._state is _State.PENDING:
            self._state = _State.IDLE
            self._last_release_at = now
            if passthrough and self.config.fast_click_passthrough:
                return TriggerEvent.PASS_CLICK
            return TriggerEvent.NONE

        if self._state is _State.OPEN:
            self._state = _State.IDLE
            self._last_release_at = now
            if selected is None:
                return TriggerEvent.CANCEL
            return TriggerEvent.RELEASE

        return TriggerEvent.NONE

    def on_tick(self, now: float) -> TriggerEvent:
        """UI 定时器每次调用，用来判断长按是否超时。"""
        if self._state is _State.PENDING:
            elapsed = (now - self._down_at) * 1000.0
            if elapsed >= self.config.long_press_ms:
                self._state = _State.OPEN
                return TriggerEvent.OPEN
        return TriggerEvent.NONE

    def on_escape(self) -> TriggerEvent:
        if self._state is _State.OPEN:
            self._state = _State.IDLE
            return TriggerEvent.CANCEL
        return TriggerEvent.NONE

    def reset(self) -> None:
        self._state = _State.IDLE
        self._last_release_at = -1e9
