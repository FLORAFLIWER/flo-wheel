"""打开设置窗口并截图，用来肉眼检查界面布局。

用法::

    python tools/settings_preview.py            # 8 秒后自动关闭
    python tools/settings_preview.py --keep     # 一直开着（自己手动关）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--ms", type=int, default=8000)
    parser.add_argument("--shot", default="", help="截图保存路径（用 Qt 自己抓，避免 DPI 缩放问题）")
    parser.add_argument("--tab", type=int, default=0, help="打开时切到第几个标签页（0=扇区 1=触发 2=外观 3=关于）")
    args = parser.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from mousewheel.logging_setup import setup_logging
    from mousewheel.platform.win import dpi

    dpi.enable()
    app = QApplication([sys.argv[0]])
    setup_logging(console=False)

    from mousewheel.app import AppController
    from mousewheel.ui.settings_window import SettingsWindow

    controller = AppController()
    window = SettingsWindow(controller)
    window.tabs.setCurrentIndex(max(0, min(args.tab, window.tabs.count() - 1)))
    window.show()
    window.raise_()
    print(f"geometry={window.geometry()}", flush=True)
    print(f"sizeHint={window.sizeHint()} minimumSizeHint={window.minimumSizeHint()}", flush=True)
    print(f"screen={window.screen().availableGeometry()}", flush=True)

    if args.shot:
        def snap() -> None:
            pixmap = window.grab()
            pixmap.save(args.shot)
            print(f"已保存截图 {args.shot} {pixmap.width()}x{pixmap.height()}", flush=True)
            app.quit()

        QTimer.singleShot(900, snap)
    elif not args.keep:
        QTimer.singleShot(max(500, args.ms), app.quit)
    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
