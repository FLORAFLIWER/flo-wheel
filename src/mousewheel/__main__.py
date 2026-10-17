"""程序入口。

用法::

    python -m mousewheel              # 正常运行（托盘常驻）
    python -m mousewheel --autostart  # 开机自启动模式：延迟后静默进托盘
    python -m mousewheel --settings   # 启动并打开设置窗口
    python -m mousewheel --demo       # 只显示轮盘（调试渲染，不挂钩子）
"""

from __future__ import annotations

import argparse
import logging
import sys

__all__ = ["main"]

log = logging.getLogger("mousewheel")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mousewheel", description="鼠标轮盘：按住侧键弹出环形快捷菜单")
    parser.add_argument("--autostart", action="store_true", help="开机自启动模式（延迟挂载钩子、不弹窗口）")
    parser.add_argument("--settings", action="store_true", help="启动后立即打开设置窗口")
    parser.add_argument("--demo", action="store_true", help="只在屏幕中央显示轮盘用于调试渲染")
    parser.add_argument("--demo-ms", type=int, default=6000, help="demo 模式显示时长（毫秒）")
    parser.add_argument("--demo-shot", default="", help="demo 模式结束时把整屏截图存到该路径")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    # DPI 感知必须早于 QApplication
    from .platform.win import dpi

    dpi.enable()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    qt_app = QApplication([sys.argv[0]])
    qt_app.setApplicationName("FLO-Wheel")
    qt_app.setApplicationDisplayName("FLO 快捷轮盘")
    qt_app.setQuitOnLastWindowClosed(False)

    from .logging_setup import setup_logging

    setup_logging(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        console=not args.autostart,
    )

    if args.demo:
        return _run_demo(qt_app, args.demo_ms, args.demo_shot)

    from .app import AppController
    from .config.store import ConfigStore
    from .platform.win.single_instance import SingleInstance
    from .ui.tray import TrayIcon

    instance = SingleInstance()
    if not instance.acquire_mutex():
        if SingleInstance.notify_existing("show"):
            log.info("已有实例在运行，已请求它打开设置窗口")
            return 0
        log.warning("检测到残留的实例互斥体，按新实例启动")

    instance.start_server()

    store = ConfigStore()
    controller = AppController(store)
    qt_app.aboutToQuit.connect(controller.shutdown)

    windows: dict[str, object] = {}

    def open_settings() -> None:
        from .ui.settings_window import SettingsWindow

        window = windows.get("settings")
        if window is None:
            window = SettingsWindow(controller)
            windows["settings"] = window
        window.refresh_from_controller()
        window.show()
        window.raise_()
        window.activateWindow()

    instance.message.connect(lambda payload: open_settings() if payload == "show" else None)

    def open_diagnose() -> None:
        from .ui.diagnose import MouseDiagnoseDialog

        dialog = MouseDiagnoseDialog(controller)
        dialog.exec()

    tray = TrayIcon(controller, open_settings, open_diagnose)
    tray.refresh()

    startup_delay = 0
    if args.autostart:
        startup_delay = max(0, int(controller.config.startup.delay_s))
    if startup_delay > 0:
        log.info("自启动模式：%s 秒后挂载钩子", startup_delay)
        QTimer.singleShot(startup_delay * 1000, controller.start)
    else:
        controller.start()

    # 打包版每次都校验一次自启动项，防止路径失效
    if getattr(sys, "frozen", False):
        enabled, message = controller.autostart_status()
        log.info("开机自启动：%s", message)

    for warning in controller.warnings:
        tray.showMessage("鼠标轮盘", warning, TrayIcon.MessageIcon.Warning, 4000)

    if args.settings:
        open_settings()

    try:
        return int(qt_app.exec())
    finally:
        instance.close()


def _run_demo(qt_app, duration_ms: int, shot_path: str = "") -> int:
    """不挂任何钩子，把轮盘画在屏幕中央，并把光标放到 12 点扇区上。"""
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtGui import QCursor

    from .config.store import ConfigStore
    from .wheel.overlay import WheelOverlay

    config = ConfigStore().load().config
    overlay = WheelOverlay()
    overlay.configure(config.wheel, config.items())
    screen = qt_app.primaryScreen()
    center = screen.geometry().center() if screen else None
    if center is None:  # pragma: no cover
        return 1
    overlay.show_at(center)
    # 用 Qt 的 QCursor 而不是 SetCursorPos：后者只认物理像素，会撞上 DPI 缩放
    radius = (config.wheel.inner_radius + config.wheel.outer_radius) // 2
    QCursor.setPos(QPoint(center.x(), center.y() - radius))
    log.info("demo：轮盘已显示 %s ms", duration_ms)

    if shot_path:
        def snap() -> None:
            # 用 Qt 抓屏：PowerShell 是非 DPI-aware 的，高缩放下只能抓到一部分
            scr = qt_app.primaryScreen()
            if scr is not None:
                scr.grabWindow(0).save(shot_path)
                log.info("demo：截图已保存到 %s", shot_path)
            qt_app.quit()

        QTimer.singleShot(max(500, duration_ms - 1200), snap)
    else:
        QTimer.singleShot(max(200, duration_ms), qt_app.quit)
    return int(qt_app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
