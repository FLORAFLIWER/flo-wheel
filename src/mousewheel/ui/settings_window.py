"""设置窗口。

设计原则：
- 打开时克隆一份配置当草稿，点"保存"才落盘，中途关闭不影响正在运行的配置
- 扇区编辑用「左列表 + 右参数面板」，参数面板按动作类型切换
- 所有输入都做校验，存不进去的东西在保存时统一报错
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..actions.registry import ACTION_LABELS, ACTION_TYPES, validate
from ..config.defaults import default_config
from ..config.model import Action, AppConfig, ALLOWED_SECTORS, SectorItem, WheelSettings
from ..wheel.renderer import WheelRenderer
from .tray import BUTTON_LABELS

__all__ = ["SettingsWindow", "describe_action"]

log = logging.getLogger(__name__)

#: 「整体大小」100% 时对应的默认半径
_BASE_INNER = 72
_BASE_OUTER = 230

_MEDIA_CHOICES = [
    ("VOLUME_UP", "音量 +"),
    ("VOLUME_DOWN", "音量 −"),
    ("VOLUME_MUTE", "静音"),
    ("PLAY_PAUSE", "播放 / 暂停"),
    ("NEXT", "下一首"),
    ("PREV", "上一首"),
    ("STOP", "停止"),
]

_SYSTEM_CHOICES = [
    ("lock", "锁定屏幕"),
    ("screenshot", "截图（Win+Shift+S）"),
    ("showdesktop", "显示桌面"),
    ("taskmgr", "任务管理器"),
    ("explorer", "文件资源管理器"),
    ("sleep", "睡眠"),
]

_TYPE_HINTS = {
    "hotkey": "按下这一组键，例如 Ctrl+Shift+S。",
    "text": "通过剪贴板粘贴，中文与表情都可靠。",
    "launch": "程序、文件或文件夹的完整路径。",
    "url": "用默认浏览器打开。",
    "media": "系统媒体键，部分键盘/驱动可能不支持。",
    "system": "Windows 内置操作。",
    "script": "在后台运行命令，不会闪窗口。",
    "none": "留空：这个扇区只显示名字，松手不做任何事。",
}

_TYPE_PLACEHOLDERS = {
    "hotkey": "Ctrl+Shift+S",
    "text": "收到，稍后回复你",
    "launch": "C:\\Windows\\System32\\notepad.exe",
    "url": "https://example.com",
    "script": "start https://www.bing.com",
}


def describe_action(action: Action) -> str:
    """给扇区列表用的单行摘要。"""
    if action.is_empty:
        return "（空）"
    t = action.type
    p = action.params
    if t == "hotkey":
        keys = str(p.get("keys") or "?")
        repeat = int(p.get("repeat") or 1)
        return f"{keys}" + (f" ×{repeat}" if repeat > 1 else "")
    if t == "text":
        text = str(p.get("text") or "").replace("\n", " ")
        return "文本：" + (text[:16] + "…" if len(text) > 16 else text) or "文本"
    if t == "launch":
        path = str(p.get("path") or "")
        return "启动：" + (os.path.basename(path) or path or "?")
    if t == "url":
        return "网址：" + str(p.get("url") or "?")
    if t == "media":
        key = str(p.get("key") or "").upper()
        label = dict(_MEDIA_CHOICES).get(key, key or "?")
        repeat = int(p.get("repeat") or 1)
        return f"{ACTION_LABELS[t]}：{label}" + (f" ×{repeat}" if repeat > 1 else "")
    if t == "system":
        cmd = str(p.get("cmd") or "").lower()
        return "系统：" + dict(_SYSTEM_CHOICES).get(cmd, cmd or "?")
    if t == "script":
        command = str(p.get("command") or "").replace("\n", " ")
        return "命令：" + (command[:16] + "…" if len(command) > 16 else command) or "命令"
    return ACTION_LABELS.get(t, t)


class SettingsWindow(QDialog):
    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._draft: AppConfig = controller.config.clone()
        self._index = 0
        self._updating = False
        self._loaded_type = "none"

        self.setWindowTitle("FLO 快捷轮盘 · 设置")
        self.resize(760, 600)
        self.setMinimumSize(680, 520)

        self._build_ui()
        self._reload_from_draft()
        self._sync_autostart_label()

    # ---- 界面搭建 --------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_sector_tab(), "扇区")
        self.tabs.addTab(self._build_trigger_tab(), "触发")
        self.tabs.addTab(self._build_appearance_tab(), "外观")
        self.tabs.addTab(self._build_about_tab(), "关于")

        buttons = QDialogButtonBox()
        self._btn_save = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_cancel = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self._btn_defaults = buttons.addButton("恢复默认", QDialogButtonBox.ButtonRole.ResetRole)
        self._btn_save.setDefault(True)
        self._btn_save.clicked.connect(self._on_save)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_defaults.clicked.connect(self._on_restore_defaults)
        layout.addWidget(buttons)

    def _build_sector_tab(self) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)

        self.list_items = QListWidget()
        self.list_items.setFixedWidth(230)
        self.list_items.currentRowChanged.connect(self._on_item_changed)
        outer.addWidget(self.list_items)

        right = QVBoxLayout()

        form = QFormLayout()
        self.ed_label = QLineEdit()
        self.ed_label.textChanged.connect(self._on_label_edited)
        form.addRow("名称", self.ed_label)

        self.ed_type = QComboBox()
        for key in ACTION_TYPES:
            self.ed_type.addItem(ACTION_LABELS[key], key)
        self.ed_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("动作", self.ed_type)
        right.addLayout(form)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #888;")
        right.addWidget(self.hint)

        self.params = QStackedWidget()
        right.addWidget(self.params, 1)

        # 空
        self.page_none = QWidget()
        self.params.addWidget(self.page_none)

        # 快捷键
        self.page_hotkey = QWidget()
        hk_form = QFormLayout(self.page_hotkey)
        self.ed_hotkey = QKeySequenceEditCompat()
        hk_form.addRow("组合键", self.ed_hotkey)
        self.ed_repeat = QSpinBox()
        self.ed_repeat.setRange(1, 20)
        hk_form.addRow("重复次数", self.ed_repeat)
        self.params.addWidget(self.page_hotkey)

        # 文本
        self.page_text = QWidget()
        text_layout = QVBoxLayout(self.page_text)
        self.ed_text = QPlainTextEdit()
        self.ed_text.setPlaceholderText(_TYPE_PLACEHOLDERS["text"])
        text_layout.addWidget(self.ed_text)
        self.chk_restore_clip = QCheckBox("用完恢复原来的剪贴板内容")
        self.chk_restore_clip.setChecked(True)
        text_layout.addWidget(self.chk_restore_clip)
        self.params.addWidget(self.page_text)

        # 启动程序
        self.page_launch = QWidget()
        launch_form = QFormLayout(self.page_launch)
        row = QHBoxLayout()
        self.ed_launch = QLineEdit()
        self.ed_launch.setPlaceholderText(_TYPE_PLACEHOLDERS["launch"])
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_launch_path)
        row.addWidget(self.ed_launch, 1)
        row.addWidget(browse)
        launch_form.addRow("路径", row)
        self.params.addWidget(self.page_launch)

        # 网址
        self.page_url = QWidget()
        url_form = QFormLayout(self.page_url)
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText(_TYPE_PLACEHOLDERS["url"])
        url_form.addRow("网址", self.ed_url)
        self.params.addWidget(self.page_url)

        # 媒体键
        self.page_media = QWidget()
        media_form = QFormLayout(self.page_media)
        self.ed_media = QComboBox()
        for key, label in _MEDIA_CHOICES:
            self.ed_media.addItem(label, key)
        media_form.addRow("按键", self.ed_media)
        self.ed_media_repeat = QSpinBox()
        self.ed_media_repeat.setRange(1, 30)
        media_form.addRow("重复次数", self.ed_media_repeat)
        self.params.addWidget(self.page_media)

        # 系统
        self.page_system = QWidget()
        system_form = QFormLayout(self.page_system)
        self.ed_system = QComboBox()
        for key, label in _SYSTEM_CHOICES:
            self.ed_system.addItem(label, key)
        system_form.addRow("动作", self.ed_system)
        self.params.addWidget(self.page_system)

        # 命令
        self.page_script = QWidget()
        script_form = QFormLayout(self.page_script)
        self.ed_script = QLineEdit()
        self.ed_script.setPlaceholderText(_TYPE_PLACEHOLDERS["script"])
        script_form.addRow("命令", self.ed_script)
        self.ed_shell = QComboBox()
        self.ed_shell.addItem("cmd（简单命令）", "cmd")
        self.ed_shell.addItem("PowerShell", "pwsh")
        script_form.addRow("解释器", self.ed_shell)
        self.params.addWidget(self.page_script)

        outer.addLayout(right, 1)
        return page

    def _build_trigger_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.ed_button = QComboBox()
        for key, label in BUTTON_LABELS.items():
            self.ed_button.addItem(label, key)
        form.addRow("鼠标触发键", self.ed_button)

        note = QLabel(
            "按住超过设定时间才会弹出轮盘；快速点一下仍保留原来的功能"
            "（例如 X1 在浏览器里是“后退”）。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        form.addRow("", note)

        self.ed_key = QKeySequenceEditCompat(allow_empty=True)
        form.addRow("键盘热键（可选）", self.ed_key)

        self.ed_mode = QComboBox()
        self.ed_mode.addItem("按住滑动（松开生效）", "hold")
        self.ed_mode.addItem("点一下开 / 再点一下生效", "toggle")
        form.addRow("触发方式", self.ed_mode)

        self.sp_long_press = QSpinBox()
        self.sp_long_press.setRange(80, 600)
        self.sp_long_press.setSuffix(" ms")
        form.addRow("长按判定", self.sp_long_press)

        self.chk_passthrough = QCheckBox("快速点击时把原来的点击还给系统")
        form.addRow("", self.chk_passthrough)

        self.btn_diagnose = QPushButton("检测我按的是哪个键…")
        self.btn_diagnose.clicked.connect(self._open_diagnose)
        form.addRow("", self.btn_diagnose)

        tip = QLabel(
            "注意：如果鼠标装了 G HUB / Synapse 之类的驱动，侧键可能被映射成宏或键盘事件，"
            "导致收不到。遇到这种情况请在驱动里把侧键改回“默认 / 后退-前进”。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888;")
        form.addRow("", tip)
        return page

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)

        left = QVBoxLayout()

        form = QFormLayout()
        self.cb_sectors = QComboBox()
        for n in ALLOWED_SECTORS:
            self.cb_sectors.addItem(f"{n} 个扇区", n)
        self.cb_sectors.currentIndexChanged.connect(self._on_sectors_changed)
        form.addRow("扇区数量", self.cb_sectors)

        size_row, self.sl_size, self.lbl_size = self._labeled_slider(50, 200, 100)
        self.sl_size.valueChanged.connect(self._on_size_slider)
        form.addRow("整体大小", size_row)

        self.sp_inner = QSpinBox()
        self.sp_inner.setRange(30, 200)
        self.sp_inner.valueChanged.connect(self._on_radius_spin)
        form.addRow("内圈半径", self.sp_inner)

        self.sp_outer = QSpinBox()
        self.sp_outer.setRange(80, 600)
        self.sp_outer.valueChanged.connect(self._on_radius_spin)
        form.addRow("外圈半径", self.sp_outer)

        self.sp_dead_zone = QSpinBox()
        self.sp_dead_zone.setRange(0, 200)
        self.sp_dead_zone.valueChanged.connect(lambda _=0: self._update_preview())
        form.addRow("中心死区", self.sp_dead_zone)

        opacity_row, self.sl_opacity, self.lbl_opacity = self._labeled_slider(0, 100, 95)
        self.sl_opacity.valueChanged.connect(self._on_opacity_slider)
        form.addRow("背景不透明度", opacity_row)

        self.sp_animate = QSpinBox()
        self.sp_animate.setRange(0, 600)
        self.sp_animate.setSuffix(" ms")
        self.sp_animate.valueChanged.connect(lambda _=0: self._update_preview())
        form.addRow("出现动画", self.sp_animate)

        self.btn_accent = QPushButton("选择主色…")
        self.btn_accent.clicked.connect(self._pick_accent)
        form.addRow("主色", self.btn_accent)

        left.addLayout(form)

        hint = QLabel(
            "「整体大小」会同时缩放内外圈，也可以用下面两个半径精细调整。\n"
            "「背景不透明度」只影响底色，文字和选中高亮始终清晰。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        left.addWidget(hint)
        left.addStretch(1)
        outer.addLayout(left, 1)

        right = QVBoxLayout()
        self.preview = WheelPreview()
        right.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.lbl_preview = QLabel("实时预览")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("color: #888;")
        right.addWidget(self.lbl_preview)
        right.addStretch(1)
        outer.addLayout(right)

        return page

    @staticmethod
    def _labeled_slider(lo: int, hi: int, value: int):
        """返回 (容器, slider, 数值标签)。"""
        from PySide6.QtWidgets import QSlider

        row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(value)
        label = QLabel(f"{value}%")
        label.setFixedWidth(44)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(slider, 1)
        row.addWidget(label)
        wrapper = QWidget()
        wrapper.setLayout(row)
        wrapper.setMinimumWidth(220)
        return wrapper, slider, label

    def _on_size_slider(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self.sp_inner.setValue(max(30, min(200, round(_BASE_INNER * value / 100))))
            self.sp_outer.setValue(max(80, min(600, round(_BASE_OUTER * value / 100))))
            self.lbl_size.setText(f"{value}%")
        finally:
            self._updating = False
        self._update_preview()

    def _on_radius_spin(self, _value: int = 0) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            percent = max(50, min(200, round(self.sp_outer.value() / _BASE_OUTER * 100)))
            self.sl_size.setValue(percent)
            self.lbl_size.setText(f"{percent}%")
        finally:
            self._updating = False
        self._update_preview()

    def _on_opacity_slider(self, value: int) -> None:
        self.lbl_opacity.setText(f"{value}%")
        # 低于 25% 时轮盘会几乎看不见，给个颜色警示（曾经有人调太低以为程序坏了）
        self.lbl_opacity.setStyleSheet("color: #E0A030;" if value < 25 else "")
        if self._updating:
            return
        self._update_preview()

    def _preview_settings(self):
        """按当前控件值拼一份临时设置（不动草稿）。"""
        from ..config.model import SectorItem, WheelSettings

        settings = WheelSettings.from_dict(self._draft.wheel.to_dict())
        settings.inner_radius = self.sp_inner.value()
        settings.outer_radius = self.sp_outer.value()
        settings.dead_zone = self.sp_dead_zone.value()
        settings.animate_ms = self.sp_animate.value()
        settings.sectors = int(self.cb_sectors.currentData() or 8)
        settings.theme.opacity = self.sl_opacity.value()
        settings.theme.accent = self._draft.wheel.theme.accent
        settings.theme.bg = self._draft.wheel.theme.bg
        settings.normalize()

        count = settings.sectors
        items = list(self._draft.main_page.items)[:count]
        while len(items) < count:
            items.append(SectorItem())
        return settings, items

    def _update_preview(self) -> None:
        preview = getattr(self, "preview", None)
        if preview is None:
            return
        settings, items = self._preview_settings()
        preview.set_preview(settings, items, selected=0)
        label = getattr(self, "lbl_preview", None)
        if label is not None:
            label.setText(f"实时预览 · 直径 {preview.wheel_diameter} px")

    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.chk_autostart = QCheckBox("开机自动启动（当前用户，普通权限）")
        form.addRow("自启动", self.chk_autostart)

        self.lbl_autostart = QLabel("")
        self.lbl_autostart.setStyleSheet("color: #888;")
        form.addRow("", self.lbl_autostart)

        config_row = QHBoxLayout()
        self.lbl_config_path = QLabel("")
        self.lbl_config_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_config = QPushButton("打开")
        open_config.clicked.connect(lambda: self._open_folder(self._controller.config_path().parent))
        config_row.addWidget(self.lbl_config_path, 1)
        config_row.addWidget(open_config)
        form.addRow("配置文件", config_row)

        buttons_row = QHBoxLayout()
        open_log = QPushButton("打开日志文件夹")
        open_log.clicked.connect(self._open_log_folder)
        buttons_row.addWidget(open_log)
        buttons_row.addStretch(1)
        form.addRow("排查", buttons_row)

        info = QLabel(
            "鼠标轮盘 0.1.0\n"
            "轮盘显示时不抢焦点，触发的快捷键会发给原来的窗口。\n"
            "以管理员身份运行的程序需要本程序也提权才能接收按键（本版本不支持）。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")
        form.addRow("", info)
        return page

    # ---- 数据同步 --------------------------------------------------------

    def refresh_from_controller(self) -> None:
        """外部改了配置（例如托盘暂停）后刷新界面。"""
        self._draft = self._controller.config.clone()
        self._reload_from_draft()
        self._sync_autostart_label()

    def _reload_from_draft(self) -> None:
        cfg = self._draft
        self._index = min(self._index, max(0, len(cfg.items()) - 1))

        self._updating = True
        try:
            self._fill_list()
            trigger = cfg.trigger
            self._set_combo(self.ed_button, trigger.button)
            self.ed_key.set_key_sequence(trigger.key)
            self._set_combo(self.ed_mode, trigger.mode)
            self.sp_long_press.setValue(trigger.long_press_ms)
            self.chk_passthrough.setChecked(trigger.fast_click_passthrough)

            wheel = cfg.wheel
            self._set_combo(self.cb_sectors, wheel.sectors)
            self.sp_inner.setValue(wheel.inner_radius)
            self.sp_outer.setValue(wheel.outer_radius)
            self.sp_dead_zone.setValue(wheel.dead_zone)
            self.sp_animate.setValue(wheel.animate_ms)
            self.sl_opacity.setValue(wheel.theme.opacity)
            self.lbl_opacity.setText(f"{wheel.theme.opacity}%")
            percent = max(50, min(200, round(wheel.outer_radius / _BASE_OUTER * 100)))
            self.sl_size.setValue(percent)
            self.lbl_size.setText(f"{percent}%")
            self.btn_accent.setText(wheel.theme.accent)
            self.chk_autostart.setChecked(cfg.startup.enabled)
            self.lbl_config_path.setText(str(self._controller.config_path()))
        finally:
            self._updating = False

        self._update_preview()

        # 先把数据装进编辑控件，再选中列表行 —— 否则 setCurrentRow 会触发
        # _on_item_changed → _commit_editor，用空白控件覆盖掉真实配置
        self._load_item(self._index)
        self._updating = True
        try:
            self.list_items.setCurrentRow(self._index)
        finally:
            self._updating = False

    def _fill_list(self) -> None:
        self.list_items.blockSignals(True)
        self.list_items.clear()
        for i, item in enumerate(self._draft.items()):
            label = item.label or f"扇区 {i + 1}"
            text = f"{i + 1}. {label}\n     {describe_action(item.action)}"
            entry = QListWidgetItem(text)
            entry.setSizeHint(entry.sizeHint().expandedTo(entry.sizeHint()))
            self.list_items.addItem(entry)
        self.list_items.blockSignals(False)

    def _refresh_list_row(self, index: int) -> None:
        if index < 0 or index >= self.list_items.count():
            return
        item = self._draft.items()[index]
        label = item.label or f"扇区 {index + 1}"
        self.list_items.item(index).setText(
            f"{index + 1}. {label}\n     {describe_action(item.action)}"
        )

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ---- 扇区编辑 --------------------------------------------------------

    def _on_item_changed(self, row: int) -> None:
        if self._updating or row < 0:
            return
        self._commit_editor()
        self._index = row
        self._load_item(row)
        self._update_preview()

    def _load_item(self, index: int) -> None:
        items = self._draft.items()
        if not items or index >= len(items):
            return
        item = items[index]
        self._updating = True
        try:
            self.ed_label.setText(item.label)
            action = item.action
            self._loaded_type = action.type if action.type in ACTION_TYPES else "none"
            self._set_combo(self.ed_type, self._loaded_type)
            self.params.setCurrentIndex(self._page_index(self._loaded_type))
            self.hint.setText(_TYPE_HINTS.get(self._loaded_type, ""))
            p = action.params
            if self._loaded_type == "hotkey":
                self.ed_hotkey.set_key_sequence(str(p.get("keys") or ""))
                self.ed_repeat.setValue(int(p.get("repeat") or 1))
            elif self._loaded_type == "text":
                self.ed_text.setPlainText(str(p.get("text") or ""))
                self.chk_restore_clip.setChecked(bool(p.get("restore_clipboard", True)))
            elif self._loaded_type == "launch":
                self.ed_launch.setText(str(p.get("path") or ""))
            elif self._loaded_type == "url":
                self.ed_url.setText(str(p.get("url") or ""))
            elif self._loaded_type == "media":
                self._set_combo(self.ed_media, str(p.get("key") or "VOLUME_UP").upper())
                self.ed_media_repeat.setValue(int(p.get("repeat") or 1))
            elif self._loaded_type == "system":
                self._set_combo(self.ed_system, str(p.get("cmd") or "lock").lower())
            elif self._loaded_type == "script":
                self.ed_script.setText(str(p.get("command") or ""))
                self._set_combo(self.ed_shell, str(p.get("shell") or "cmd").lower())
        finally:
            self._updating = False

    def _commit_editor(self) -> None:
        items = self._draft.items()
        if not items or self._index >= len(items):
            return
        item = items[self._index]
        item.label = self.ed_label.text().strip() or f"扇区 {self._index + 1}"
        atype = self.ed_type.currentData() or "none"
        params: dict = {}
        if atype == "hotkey":
            params = {
                "keys": self.ed_hotkey.key_text(),
                "repeat": self.ed_repeat.value(),
            }
        elif atype == "text":
            params = {
                "text": self.ed_text.toPlainText(),
                "restore_clipboard": self.chk_restore_clip.isChecked(),
            }
        elif atype == "launch":
            params = {"path": self.ed_launch.text().strip()}
        elif atype == "url":
            params = {"url": self.ed_url.text().strip()}
        elif atype == "media":
            params = {
                "key": self.ed_media.currentData() or "VOLUME_UP",
                "repeat": self.ed_media_repeat.value(),
            }
        elif atype == "system":
            params = {"cmd": self.ed_system.currentData() or "lock"}
        elif atype == "script":
            params = {
                "command": self.ed_script.text().strip(),
                "shell": self.ed_shell.currentData() or "cmd",
                "hidden": True,
            }
        item.action = Action(type=atype, params=params)
        self._refresh_list_row(self._index)

    def _on_label_edited(self, text: str) -> None:
        if self._updating:
            return
        items = self._draft.items()
        if items and self._index < len(items):
            items[self._index].label = text
            self._refresh_list_row(self._index)
            self._update_preview()

    def _on_type_changed(self, _index: int) -> None:
        if self._updating:
            return
        atype = self.ed_type.currentData() or "none"
        self.params.setCurrentIndex(self._page_index(atype))
        self.hint.setText(_TYPE_HINTS.get(atype, ""))

    @staticmethod
    def _page_index(action_type: str) -> int:
        order = ["none", "hotkey", "text", "launch", "url", "media", "system", "script"]
        try:
            return order.index(action_type)
        except ValueError:
            return 0

    def _on_sectors_changed(self) -> None:
        if self._updating:
            return
        count = int(self.cb_sectors.currentData() or 8)
        self._commit_editor()
        cfg = self._draft
        cfg.wheel.sectors = count
        cfg.normalize()
        self._fill_list()
        self._index = min(self._index, count - 1)
        self._load_item(self._index)
        self._updating = True
        try:
            self.list_items.setCurrentRow(self._index)
        finally:
            self._updating = False
        self._update_preview()

    def _pick_launch_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要启动的程序或文件", self.ed_launch.text() or "C:\\"
        )
        if path:
            self.ed_launch.setText(path)
            if not self.ed_label.text().strip():
                self.ed_label.setText(os.path.splitext(os.path.basename(path))[0])

    def _pick_accent(self) -> None:
        current = self._draft.wheel.theme.accent
        color = QColorDialog.getColor(_maybe_color(current), self, "选择主色")
        if color.isValid():
            self._draft.wheel.theme.accent = color.name()
            self.btn_accent.setText(color.name())
            self._update_preview()

    # ---- 自启动 ----------------------------------------------------------

    def _sync_autostart_label(self) -> None:
        from ..platform.win import autostart

        cmd = autostart.current_command()
        if cmd:
            self.lbl_autostart.setText(f"注册表中已存在：{cmd}")
        else:
            self.lbl_autostart.setText("注册表中尚未设置")

    def _open_log_folder(self) -> None:
        from .. import paths

        self._open_folder(paths.log_dir())

    def _open_diagnose(self) -> None:
        from .diagnose import MouseDiagnoseDialog

        dialog = MouseDiagnoseDialog(self._controller, self)
        dialog.exec()

    @staticmethod
    def _open_folder(path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError:
            pass

    # ---- 保存 ------------------------------------------------------------

    def _on_restore_defaults(self) -> None:
        if (
            QMessageBox.question(
                self,
                "恢复默认",
                "把所有扇区和设置恢复成出厂默认？你的自定义内容会丢失。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._draft = default_config()
        self._index = 0
        self._reload_from_draft()

    def _commit_settings(self) -> None:
        """把「触发」「外观」「关于」三页的控件值写回草稿。

        注意：这里必须显式逐项搬运 —— 控件不会自动绑定到 dataclass。
        （早期版本漏了这一步，表现为"改完触发键保存后再打开还是 X1"。）
        """
        cfg = self._draft
        cfg.trigger.button = self.ed_button.currentData() or "x1"
        cfg.trigger.key = self.ed_key.key_text()
        cfg.trigger.mode = self.ed_mode.currentData() or "hold"
        cfg.trigger.long_press_ms = self.sp_long_press.value()
        cfg.trigger.fast_click_passthrough = self.chk_passthrough.isChecked()

        cfg.wheel.sectors = int(self.cb_sectors.currentData() or 8)
        cfg.wheel.inner_radius = self.sp_inner.value()
        cfg.wheel.outer_radius = self.sp_outer.value()
        cfg.wheel.dead_zone = self.sp_dead_zone.value()
        cfg.wheel.animate_ms = self.sp_animate.value()
        cfg.wheel.theme.opacity = self.sl_opacity.value()

        cfg.startup.enabled = self.chk_autostart.isChecked()
        cfg.normalize()

    def _on_save(self) -> None:
        self._commit_editor()
        self._commit_settings()
        cfg = self._draft

        problems: list[str] = []
        for i, item in enumerate(cfg.items()):
            err = validate(item.action)
            if err:
                problems.append(f"第 {i + 1} 个扇区「{item.label}」：{err}")
        if problems:
            QMessageBox.warning(self, "还有配置没填好", "\n".join(problems))
            return

        warnings = self._controller.apply(cfg, save=True)
        if warnings:
            QMessageBox.warning(self, "已保存但有提醒", "\n".join(warnings))

        enabled, message = self._controller.autostart_status()
        self.lbl_autostart.setText(message)
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        # 在 QKeySequenceEdit 里录键时不要触发 Esc 关闭窗口
        if event.key() == Qt.Key.Key_Escape and self.ed_key.has_focus():
            event.ignore()
            return
        super().keyPressEvent(event)


class QKeySequenceEditCompat(QWidget):
    """对 QKeySequenceEdit 的薄封装：空值安全 + 输出规范化文本。"""

    def __init__(self, allow_empty: bool = False, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QKeySequenceEdit

        self._allow_empty = allow_empty
        self._edit = QKeySequenceEdit()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._edit, 1)
        clear = QPushButton("清除")
        clear.setFixedWidth(56)
        clear.clicked.connect(self._edit.clear)
        row.addWidget(clear)

    def set_key_sequence(self, text: str) -> None:
        self._edit.setKeySequence(QKeySequence(text) if text else QKeySequence())

    def key_text(self) -> str:
        """返回规范化后的字符串（Win 键统一写成 Win）。"""
        seq = self._edit.keySequence()
        if seq.isEmpty():
            return ""
        text = seq.toString(QKeySequence.SequenceFormat.PortableText)
        from ..input.hotkey_spec import HotkeyError, format_hotkey, parse_hotkey

        try:
            return format_hotkey(parse_hotkey(text))
        except HotkeyError:
            return text

    def has_focus(self) -> bool:
        return self._edit.hasFocus()


def _maybe_color(text: str):
    from PySide6.QtGui import QColor

    color = QColor(text)
    return color if color.isValid() else QColor("#4C8DFF")


class WheelPreview(QWidget):
    """外观页的实时预览。

    背景画成浅色渐变模拟桌面 —— 这样拖「背景不透明度」时能立刻看出差别。
    缩放基准是固定的（不是「总是填满控件」），所以调「整体大小」时预览里的
    轮盘是真的会变大变小，超过控件时被裁掉（说明确实很大了）。
    """

    #: 缩放基准：150% 时的轮盘直径，此时刚好填满 260px 的控件
    _REF_DIAMETER = 740.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(260, 260)
        self._settings = WheelSettings()
        self._items: list[SectorItem] = []
        self._selected: int | None = 0
        self._renderer = WheelRenderer(self._settings, self._items)

    def set_preview(self, settings: WheelSettings, items: list[SectorItem], selected: int | None = 0) -> None:
        self._settings = settings
        self._items = items
        self._selected = selected
        self._renderer.update(settings, items)
        self.update()

    @property
    def wheel_diameter(self) -> int:
        """实际弹出时窗口的直径（逻辑像素），用于在界面上显示。"""
        return int(round(self._renderer.diameter))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        gradient = QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.0, QColor("#3F4551"))
        gradient.setColorAt(1.0, QColor("#A3AAB9"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 10, 10)

        side = float(min(rect.width(), rect.height()))
        scale = side / self._REF_DIAMETER
        diameter = self._renderer.diameter

        painter.save()
        painter.setClipRect(rect)
        painter.translate(rect.width() / 2.0, rect.height() / 2.0)
        painter.scale(scale, scale)
        painter.translate(-diameter / 2.0, -diameter / 2.0)
        self._renderer.paint(painter, self._selected, 1.0)
        painter.restore()
        painter.end()
