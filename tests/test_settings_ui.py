"""设置窗口的保存行为测试。

这些测试是为了钉住一个真实 bug：设置窗口曾经只提交了"扇区编辑"和
"自启动开关"，「触发」和「外观」两页改了保存后不生效 —— 用户改触发键，
保存、重开，发现还是 X1。
"""

from __future__ import annotations

import pytest

from mousewheel.config.store import ConfigStore


def make_window(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from mousewheel.app import AppController
    from mousewheel.ui.settings_window import SettingsWindow

    # 任何模态对话框都会让测试永远卡住（offscreen 下没人点按钮）
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )

    store = ConfigStore(tmp_path / "config.json")
    controller = AppController(store)
    # 不要在测试里动真实的注册表
    monkeypatch.setattr(controller, "autostart_status", lambda: (True, "测试跳过"))
    # 也不要真的去装系统键盘钩子（会影响正在运行的实例和后续测试）
    monkeypatch.setattr(controller, "_setup_key_trigger", lambda: None)
    monkeypatch.setattr(controller, "_stop_key_hook", lambda: None)
    return SettingsWindow(controller), controller, store


def load(store: ConfigStore):
    return ConfigStore(store.path).load().config


def test_trigger_change_is_persisted(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.ed_button.setCurrentIndex(window.ed_button.findData("x2"))
    window.sp_long_press.setValue(260)
    window.ed_mode.setCurrentIndex(window.ed_mode.findData("toggle"))
    window.chk_passthrough.setChecked(False)
    window._on_save()

    saved = load(store)
    assert saved.trigger.button == "x2"
    assert saved.trigger.long_press_ms == 260
    assert saved.trigger.mode == "toggle"
    assert saved.trigger.fast_click_passthrough is False
    # 内存里的运行配置也要跟着变（钩子会读到新值）
    assert controller.config.trigger.button == "x2"
    assert controller.hook.trigger_button == "x2"


def test_keyboard_trigger_is_persisted(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.ed_key.set_key_sequence("Ctrl+Alt+Space")
    window._on_save()

    saved = load(store)
    assert saved.trigger.key == "Ctrl+Alt+Space"


def test_appearance_change_is_persisted(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sp_inner.setValue(90)
    window.sp_outer.setValue(300)
    window.sp_dead_zone.setValue(40)
    window.sp_animate.setValue(0)
    window._on_save()

    saved = load(store)
    assert saved.wheel.inner_radius == 90
    assert saved.wheel.outer_radius == 300
    assert saved.wheel.dead_zone == 40
    assert saved.wheel.animate_ms == 0


def test_sector_count_change_grows_items(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.cb_sectors.setCurrentIndex(window.cb_sectors.findData(12))
    window._on_save()

    saved = load(store)
    assert saved.wheel.sectors == 12
    assert len(saved.items()) == 12


def test_sector_edit_is_persisted(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.list_items.setCurrentRow(0)
    window.ed_label.setText("我的复制")
    window.ed_type.setCurrentIndex(window.ed_type.findData("text"))
    window.ed_text.setPlainText("固定回复")
    window._on_save()

    saved = load(store)
    first = saved.items()[0]
    assert first.label == "我的复制"
    assert first.action.type == "text"
    assert first.action.get("text") == "固定回复"


def test_cancel_does_not_write(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)
    before = store.path.read_text(encoding="utf-8")

    window.ed_button.setCurrentIndex(window.ed_button.findData("middle"))
    # 不调用 _on_save，模拟点「取消」
    window.reject()

    assert store.path.read_text(encoding="utf-8") == before
    assert controller.config.trigger.button == "x1"


def test_opacity_slider_is_persisted(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sl_opacity.setValue(40)
    window._on_save()

    saved = load(store)
    assert saved.wheel.theme.opacity == 40


def test_size_slider_scales_both_radii(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sl_size.setValue(150)
    assert window.sp_outer.value() == 345  # 230 * 150%
    assert window.sp_inner.value() == 108  # 72 * 150%
    window._on_save()

    saved = load(store)
    assert saved.wheel.outer_radius == 345
    assert saved.wheel.inner_radius == 108


def test_size_slider_is_clamped_to_spin_ranges(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sl_size.setValue(50)
    assert window.sp_outer.value() >= 80
    assert window.sp_inner.value() >= 30

    window.sl_size.setValue(200)
    assert window.sp_outer.value() <= 600


def test_radius_spin_updates_size_slider(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sp_outer.setValue(345)
    assert window.sl_size.value() == 150
    assert "150%" in window.lbl_size.text()


def test_trigger_combo_excludes_dangerous_buttons(qt_app, tmp_path, monkeypatch) -> None:
    """左键/右键绝不能出现在触发键下拉框里（选中会让鼠标瘫痪）。"""
    window, controller, store = make_window(tmp_path, monkeypatch)

    values = [window.ed_button.itemData(i) for i in range(window.ed_button.count())]
    assert "left" not in values
    assert "right" not in values
    assert {"x1", "x2", "middle", "none"} <= set(values)


def test_preview_reflects_current_values(qt_app, tmp_path, monkeypatch) -> None:
    window, controller, store = make_window(tmp_path, monkeypatch)

    window.sl_size.setValue(150)
    window.sl_opacity.setValue(50)
    window._update_preview()

    assert window.preview.wheel_diameter == int(window.preview._renderer.diameter)
    assert window.preview.wheel_diameter > 500  # 放大后直径确实变大
    assert "直径" in window.lbl_preview.text()
