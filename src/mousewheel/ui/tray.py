"""系统托盘图标与菜单。"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config.model import ALLOWED_BUTTONS

__all__ = ["TrayIcon", "build_icon", "BUTTON_LABELS"]

log = logging.getLogger(__name__)

BUTTON_LABELS = {
    "x1": "侧键 X1（通常是「后退」键）",
    "x2": "侧键 X2（通常是「前进」键）",
    "middle": "中键（滚轮按下）",
    "none": "不启用鼠标触发",
}


def build_icon(size: int = 64, accent: str = "#4C8DFF", muted: bool = False) -> QIcon:
    """画一个 8 段圆环当图标（不依赖图片资源）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2.0, size / 2.0)

    color = QColor("#6B7280" if muted else accent)
    outer = size * 0.44
    inner = size * 0.20
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(8):
        start = i * 45.0 + 4.0
        end = (i + 1) * 45.0 - 4.0
        path = _sector(inner, outer, start, end)
        shade = QColor(color)
        shade.setAlpha(255 if i % 2 == 0 else 170)
        painter.setBrush(shade)
        painter.drawPath(path)
    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 90))
    painter.drawEllipse(QPointF(0, 0), inner * 0.9, inner * 0.9)
    painter.end()
    return QIcon(pm)


def _sector(inner: float, outer: float, start_deg: float, end_deg: float):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath

    qt_start = 90.0 - start_deg
    sweep = -(end_deg - start_deg)
    o = QRectF(-outer, -outer, outer * 2, outer * 2)
    i = QRectF(-inner, -inner, inner * 2, inner * 2)
    p = QPainterPath()
    p.arcMoveTo(o, qt_start)
    p.arcTo(o, qt_start, sweep)
    p.arcTo(i, qt_start + sweep, -sweep)
    p.closeSubpath()
    return p


class TrayIcon(QSystemTrayIcon):
    def __init__(self, controller, open_settings, open_diagnose=None, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._open_settings = open_settings
        self._open_diagnose = open_diagnose
        self.setIcon(build_icon(accent=controller.config.wheel.theme.accent))
        self.setToolTip("FLO 快捷轮盘")

        menu = QMenu()
        self._menu = menu

        settings_action = QAction("打开设置…", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        menu.setDefaultAction(settings_action)

        menu.addSeparator()

        self._enable_action = QAction("启用轮盘", menu)
        self._enable_action.setCheckable(True)
        self._enable_action.setChecked(not controller.paused)
        self._enable_action.toggled.connect(self._on_enable_toggled)
        menu.addAction(self._enable_action)

        reload_action = QAction("重新载入配置", menu)
        reload_action.triggered.connect(self._on_reload)
        menu.addAction(reload_action)

        diagnose_action = QAction("检测鼠标按键…", menu)
        diagnose_action.triggered.connect(self._on_diagnose)
        menu.addAction(diagnose_action)

        folder_action = QAction("打开配置文件夹", menu)
        folder_action.triggered.connect(self._on_open_folder)
        menu.addAction(folder_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        controller.action_failed.connect(self._on_failed)
        self.setVisible(True)

    def _on_diagnose(self) -> None:
        if self._open_diagnose is not None:
            self._open_diagnose()

    # ---- 菜单回调 --------------------------------------------------------

    def _on_enable_toggled(self, checked: bool) -> None:
        self._controller.set_paused(not checked)
        self.setIcon(
            build_icon(accent=self._controller.config.wheel.theme.accent, muted=not checked)
        )

    def _on_reload(self) -> None:
        warnings = self._controller.reload_config()
        self._enable_action.setChecked(not self._controller.paused)
        if warnings:
            self.showMessage("配置已重载", "；".join(warnings), QSystemTrayIcon.MessageIcon.Warning, 4000)
        else:
            self.showMessage("配置已重载", "已生效", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _on_open_folder(self) -> None:
        import os

        path = self._controller.config_path().parent
        os.startfile(str(path))  # type: ignore[attr-defined]

    def _on_quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._open_settings()

    def _on_failed(self, message: str) -> None:
        self.showMessage("鼠标轮盘", message, QSystemTrayIcon.MessageIcon.Warning, 4000)

    # ---- 状态 ------------------------------------------------------------

    def refresh(self) -> None:
        self._enable_action.setChecked(not self._controller.paused)
        button = self._controller.config.trigger.button
        self.setToolTip(
            f"FLO 快捷轮盘 · {BUTTON_LABELS.get(button, button)}"
            + ("（已暂停）" if self._controller.paused else "")
        )
        self.setIcon(
            build_icon(
                accent=self._controller.config.wheel.theme.accent,
                muted=self._controller.paused,
            )
        )
