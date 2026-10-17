"""轮盘覆盖窗口。

窗口本身**完全不接收输入**：``WS_EX_TRANSPARENT | WS_EX_NOACTIVATE``，
鼠标位置靠 16ms 定时器轮询 ``QCursor.pos()``。这样做的原因：

- 不抢前台焦点，触发的快捷键才会发给原窗口
- 不吃点击，用户在轮盘上"划过"不会误点到下面的程序

Esc 取消用 ``GetAsyncKeyState`` 轮询而不是键盘钩子 —— 少挂一个全局钩子，
就少一份让系统摘钩的风险。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from ..config.model import SectorItem, WheelSettings
from ..platform.win.winapi import VK, user32
from .geometry import sector_index_at
from .renderer import WheelRenderer

__all__ = ["WheelOverlay"]

_TICK_MS = 16
_EASING = None  # 延迟导入 QEasingCurve，避免模块级 QtGui 依赖过重


class WheelOverlay(QWidget):
    """环形菜单窗口。显示/隐藏由 :class:`AppController` 控制。"""

    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._settings = WheelSettings()
        self._items: list[SectorItem] = []
        self._renderer = WheelRenderer(self._settings, self._items)
        self._selected: int | None = None
        self._progress = 1.0
        self._esc_latched = False

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim_value)

        self.setFixedSize(int(self._renderer.diameter), int(self._renderer.diameter))

    # ---- 对外接口 --------------------------------------------------------

    def configure(self, settings: WheelSettings, items: list[SectorItem]) -> None:
        self._settings = settings
        self._items = items
        self._renderer.update(settings, items)
        side = int(self._renderer.diameter)
        self.setFixedSize(side, side)

    @property
    def is_visible(self) -> bool:
        return self.isVisible()

    def current_index(self) -> int | None:
        return self._selected

    def current_label(self) -> str:
        if self._selected is None or self._selected >= len(self._items):
            return ""
        return self._items[self._selected].label

    def show_at(self, global_pos: QPoint) -> None:
        """在 ``global_pos``（逻辑坐标）处弹出。"""
        side = self.width()
        target = QPoint(int(global_pos.x() - side / 2), int(global_pos.y() - side / 2))

        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            x = max(geo.left(), min(target.x(), geo.right() - side + 1))
            y = max(geo.top(), min(target.y(), geo.bottom() - side + 1))
            target = QPoint(x, y)

        self.setGeometry(QRectF(target.x(), target.y(), side, side).toRect())
        self._selected = None
        self._esc_latched = False
        duration = max(0, int(self._settings.animate_ms))
        if duration > 0:
            self._progress = 0.0
            self._anim.stop()
            self._anim.setDuration(duration)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self._progress = 1.0

        self.show()
        self.raise_()
        self._timer.start()

    def hide_wheel(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._selected = None
        self.hide()

    # ---- 内部 ------------------------------------------------------------

    def _on_anim_value(self, value) -> None:
        try:
            self._progress = float(value)
        except (TypeError, ValueError):
            self._progress = 1.0
        self.update()

    def _tick(self) -> None:
        # Esc 取消：轮盘显示期间才轮询
        state = int(user32.GetAsyncKeyState(VK.ESCAPE))
        if state & 0x8000:
            if not self._esc_latched:
                self._esc_latched = True
                self.cancelled.emit()
            return
        self._esc_latched = False

        pos = QCursor.pos()
        local = self.mapFromGlobal(pos)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dx = local.x() - cx
        dy = local.y() - cy
        dist = math.hypot(dx, dy)

        settings = self._settings
        new = self._selected
        if dist < settings.dead_zone:
            new = None
        elif dist > settings.outer_radius:
            pass  # 划出外圈：锁定最后的方向，避免手抖丢选中
        else:
            new = sector_index_at(dx, dy, settings.sectors)

        if new != self._selected:
            self._selected = new
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._renderer.paint(painter, self._selected, self._progress)
        painter.end()
