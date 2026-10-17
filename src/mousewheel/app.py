"""应用控制器：把钩子、触发状态机、轮盘窗口、动作执行串起来。

数据流（全部在 Qt 主线程，除了钩子回调和动作线程）::

    钩子线程 --signal--> _on_mouse_event --> TriggerController --OPEN--> 弹轮盘
                                          --> PASS_CLICK --> 重放点击
                                          --> RELEASE --> 执行动作
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCursor

from .actions.base import ActionContext
from .actions.registry import execute as run_action
from .config.model import AppConfig, SectorItem
from .config.store import ConfigStore, LoadResult
from .input.trigger import TriggerConfig, TriggerController, TriggerEvent
from .input.inject import send_mouse_click
from .input.mouse_hook import MouseHookThread
from .input.key_hook import KeyHookThread
from .input.key_combo import KeyComboTracker
from .input.hotkey_spec import HotkeyError, parse_hotkey
from .platform.win import autostart
from .platform.win.winapi import get_foreground_window
from .wheel.overlay import WheelOverlay

__all__ = ["AppController"]

log = logging.getLogger(__name__)

_TICK_MS = 16


class AppController(QObject):
    status_changed = Signal(str)
    wheel_opened = Signal()
    wheel_closed = Signal()
    action_failed = Signal(str)
    #: 诊断模式下的原始鼠标事件（kind, button），供"检测鼠标按键"窗口显示
    diagnose_event = Signal(str, str)

    def __init__(self, store: ConfigStore | None = None, parent=None) -> None:
        super().__init__(parent)
        self._store = store or ConfigStore()
        self._load_result: LoadResult = self._store.load()
        self.config: AppConfig = self._load_result.config
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mw-action")
        self._paused = False
        self._foreground_hwnd = 0
        self._hotkey_error = ""
        self._combo: KeyComboTracker | None = None

        self.trigger = TriggerController()
        self.overlay = WheelOverlay()
        self.overlay.cancelled.connect(self._on_cancelled)

        self.hook = MouseHookThread(self)
        self.hook.mouse_event.connect(self._on_mouse_event)
        self.hook.diagnostic_event.connect(self.diagnose_event)
        self.hook.failed.connect(self._on_hook_failed)

        self.key_hook = KeyHookThread(self)
        self.key_hook.key_event.connect(self._on_key_event)
        self.key_hook.failed.connect(self._on_hook_failed)

        self._tick = QTimer(self)
        self._tick.setInterval(_TICK_MS)
        self._tick.timeout.connect(self._on_tick)

        self._apply_config()
        if self._load_result.warnings:
            for warning in self._load_result.warnings:
                log.warning(warning)

    # ---- 生命周期 --------------------------------------------------------

    def start(self) -> None:
        self.hook.start()
        self._tick.start()
        self._setup_key_trigger()
        log.info(
            "已启动：触发键=%s 键盘=%s 模式=%s 扇区=%s",
            self.config.trigger.button,
            self.config.trigger.key or "无",
            self.config.trigger.mode,
            self.config.wheel.sectors,
        )

    def shutdown(self) -> None:
        log.info("正在退出")
        self._tick.stop()
        try:
            self.overlay.hide_wheel()
        except Exception:
            pass
        self._stop_key_hook()
        self.hook.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- 配置 ------------------------------------------------------------

    @property
    def warnings(self) -> list[str]:
        return list(self._load_result.warnings)

    @property
    def paused(self) -> bool:
        return self._paused

    def config_path(self):
        return self._store.path

    def items(self) -> list[SectorItem]:
        return self.config.items()

    def set_diagnose(self, on: bool) -> None:
        """开关鼠标按键诊断：开的时候钩子投递所有按钮且一个都不吞。"""
        self.hook.diagnose = bool(on)
        log.info("鼠标按键诊断：%s", "开启" if on else "关闭")

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        if self._paused:
            self.overlay.hide_wheel()
            self.trigger.reset()
            self._stop_key_hook()
        else:
            self._setup_key_trigger()
        self.hook.trigger_button = "" if self._paused else self.config.trigger.button
        log.info("暂停开关：%s", "暂停" if self._paused else "恢复")
        self.status_changed.emit("已暂停" if self._paused else "已恢复")

    def reload_config(self) -> list[str]:
        self._load_result = self._store.load()
        self.config = self._load_result.config
        self._apply_config()
        self._setup_key_trigger()
        log.info("配置已重载")
        self.status_changed.emit("配置已重载")
        return list(self._load_result.warnings)

    def apply(self, config: AppConfig, save: bool = True) -> list[str]:
        """应用一份新配置（设置窗口保存时调用）。"""
        warnings: list[str] = []
        self.config = config
        if save:
            try:
                self._store.save(config)
            except Exception as exc:  # ConfigError
                warnings.append(str(exc))
        self._apply_config()
        self._setup_key_trigger()
        if self._hotkey_error:
            warnings.append(self._hotkey_error)
        return warnings

    def _apply_config(self) -> None:
        cfg = self.config
        self.trigger.config = TriggerConfig(
            button=cfg.trigger.button,
            mode=cfg.trigger.mode,
            long_press_ms=cfg.trigger.long_press_ms,
            fast_click_passthrough=cfg.trigger.fast_click_passthrough,
        )
        # 暂停时把触发键置空，钩子就不会吞任何键
        self.hook.trigger_button = "" if self._paused else cfg.trigger.button
        self.overlay.configure(cfg.wheel, cfg.items())

    def _setup_key_trigger(self) -> None:
        """配置键盘触发键：按住组合键弹出，松开执行。

        用低级键盘钩子而不是 RegisterHotKey —— 后者只知道"按下了"，
        拿不到"松开了"，做不出和侧键一致的按住-松开手感。
        """
        key = self.config.trigger.key.strip()
        self._stop_key_hook()
        self._hotkey_error = ""
        self._combo = None
        if not key:
            return
        try:
            spec = parse_hotkey(key)
        except HotkeyError as exc:
            self._hotkey_error = str(exc)
            log.warning("键盘触发键无效：%s", exc)
            return
        combo = KeyComboTracker(spec.modifier_vks, spec.vk)
        self._combo = combo
        self.key_hook.interest = combo.needed
        self.key_hook.start()
        log.info("键盘触发键已就绪：%s（按住弹出，松开执行）", spec.source)

    def _stop_key_hook(self) -> None:
        try:
            if self.key_hook.isRunning():
                self.key_hook.stop()
        except Exception:
            log.exception("停止键盘钩子失败")
        self.key_hook.interest = frozenset()

    def autostart_status(self) -> tuple[bool, str]:
        """把注册表对齐到配置，并返回真实状态（供设置界面显示）。"""
        return autostart.sync(self.config.startup.enabled)

    # ---- 事件 ------------------------------------------------------------

    @Slot(str, str)
    def _on_mouse_event(self, kind: str, button: str) -> None:
        if self._paused:
            return
        now = time.monotonic()
        if kind == "down":
            event = self.trigger.on_mouse_down(button, now)
            if event is TriggerEvent.OPEN:
                self._open_wheel()
        elif kind == "up":
            selected = self.overlay.current_index() if self.overlay.is_visible else None
            event = self.trigger.on_mouse_up(button, now, selected)
            if event is TriggerEvent.PASS_CLICK:
                # 不在这里 SendInput：回调线程里注入会重入
                QTimer.singleShot(0, lambda b=button: send_mouse_click(b))
            elif event is TriggerEvent.RELEASE:
                self._commit()
            elif event is TriggerEvent.CANCEL:
                self._close_wheel()

    @Slot()
    def _on_tick(self) -> None:
        if self._paused:
            return
        event = self.trigger.on_tick(time.monotonic())
        if event is TriggerEvent.OPEN:
            self._open_wheel()

    @Slot()
    def _on_cancelled(self) -> None:
        self.trigger.on_escape()
        self._close_wheel()

    @Slot(str)
    def _on_hook_failed(self, message: str) -> None:
        log.error(message)
        self.action_failed.emit(message)

    @Slot(str, int)
    def _on_key_event(self, kind: str, vk: int) -> None:
        """键盘触发键：组合按住 → 弹轮盘；松开 → 执行。"""
        if self._paused or self._combo is None:
            return
        now = time.monotonic()
        if kind == "down":
            if not self._combo.on_down(vk):
                return
            event = self.trigger.on_key_down(now)
            if event is TriggerEvent.OPEN:
                self._open_wheel()
            elif event is TriggerEvent.RELEASE:  # toggle 模式的第二次按下
                self._commit()
        else:
            if not self._combo.on_up(vk):
                return
            selected = self.overlay.current_index() if self.overlay.is_visible else None
            event = self.trigger.on_key_up(now, selected)
            if event is TriggerEvent.RELEASE:
                self._commit()
            elif event is TriggerEvent.CANCEL:
                self._close_wheel()

    # ---- 轮盘 ------------------------------------------------------------

    def _open_wheel(self) -> None:
        self._foreground_hwnd = get_foreground_window()
        self.overlay.configure(self.config.wheel, self.config.items())
        self.overlay.show_at(QCursor.pos())
        log.info("轮盘弹出：位置=%s 扇区=%s", QCursor.pos(), self.config.wheel.sectors)
        self.wheel_opened.emit()

    def _close_wheel(self) -> None:
        if self.overlay.is_visible:
            self.overlay.hide_wheel()
            self.wheel_closed.emit()

    def _commit(self) -> None:
        index = self.overlay.current_index()
        self._close_wheel()
        if index is None:
            log.info("松开时没有选中扇区 → 取消")
            return
        items = self.items()
        if index >= len(items):
            return
        item = items[index]
        if item.action.is_empty:
            return
        hwnd = self._foreground_hwnd
        action = item.action
        label = item.label or action.type
        self._pool.submit(self._run_action, action, label, hwnd)

    def _run_action(self, action, label: str, hwnd: int) -> None:
        log.info("执行动作：%s (%s)", label, action.type)
        result = run_action(action, ActionContext(foreground_hwnd=hwnd))
        if not result.ok:
            log.warning("动作失败：%s -> %s", label, result.detail)
            self.action_failed.emit(f"{label}：{result.detail}")
