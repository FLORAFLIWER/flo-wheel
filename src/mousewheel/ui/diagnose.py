"""鼠标按键诊断窗口。

用途：当"按了侧键没反应"时，用它区分三种情况：
1. 按下去这里**有记录**，且标着"当前触发键" → 配置没问题，问题在别处
2. 有记录但标着"不是当前触发键" → 配置选错了键（X1/X2 记反了很常见）
3. **完全没记录** → 按键事件根本没到程序：鼠标驱动把它映射成了宏/键盘事件，
   或者这个键是 DPI 切换之类的硬件功能

诊断模式期间钩子不吞任何键，所以鼠标功能完全正常。
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from .tray import BUTTON_LABELS

__all__ = ["MouseDiagnoseDialog"]

_MAX_LINES = 60


class MouseDiagnoseDialog(QDialog):
    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._hits: set[str] = set()

        self.setWindowTitle("检测鼠标按键")
        self.resize(460, 380)

        layout = QVBoxLayout(self)

        tip = QLabel(
            "按一下你想用来触发轮盘的鼠标键（侧键、中键都可以），下面会显示程序实际收到的按键。\n"
            "诊断期间不会弹出轮盘，也不会影响鼠标本来的功能。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888;")
        layout.addWidget(tip)

        self.lbl_hint = QLabel("等待按键…")
        self.lbl_hint.setWordWrap(True)
        font = self.lbl_hint.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        self.lbl_hint.setFont(font)
        layout.addWidget(self.lbl_hint)

        self.log = QListWidget()
        layout.addWidget(self.log, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("关闭")
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        layout.addWidget(buttons)

        controller.diagnose_event.connect(self._on_event)
        controller.set_diagnose(True)
        # 无论怎么关（关闭按钮/ESC/点 X），都要把诊断关掉，
        # 否则钩子会一直处于"不吞任何键"的状态 —— 轮盘就再也不弹了
        self.finished.connect(lambda _=0: controller.set_diagnose(False))

    # ---- 事件 ------------------------------------------------------------

    def _on_event(self, kind: str, button: str) -> None:
        trigger = self._controller.config.trigger.button
        name = BUTTON_LABELS.get(button, button)
        is_trigger = button == trigger

        stamp = time.strftime("%H:%M:%S")
        action = "按下" if kind == "down" else "松开"
        suffix = "   ← 当前触发键" if is_trigger else ""
        self.log.addItem(f"{stamp}  {action}  {name}{suffix}")
        if self.log.count() > _MAX_LINES:
            self.log.takeItem(0)
        self.log.scrollToBottom()

        if kind != "down":
            return
        self._hits.add(button)
        if is_trigger:
            self.lbl_hint.setText(f"✓ 收到了「{name}」，它就是当前触发键，配置正确")
            self.lbl_hint.setStyleSheet("color: #35C46A;")
        else:
            self.lbl_hint.setText(
                f"收到了「{name}」，但它不是当前触发键（当前是 {BUTTON_LABELS.get(trigger, trigger)}）。"
                "请到设置里把触发键改成这个键。"
            )
            self.lbl_hint.setStyleSheet("color: #E0A030;")

    # ---- 关闭 ------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._controller.set_diagnose(False)
        super().closeEvent(event)

    def reject(self) -> None:
        self._controller.set_diagnose(False)
        super().reject()

    def accept(self) -> None:
        self._controller.set_diagnose(False)
        super().accept()
