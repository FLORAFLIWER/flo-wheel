"""离屏渲染探针：把轮盘画到 QImage 上，打印关键像素的 RGBA。

用来确认"扇区底色到底有多透"，比截图人眼看可靠。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from mousewheel.config.defaults import default_config
from mousewheel.wheel.renderer import WheelRenderer


def probe() -> int:
    app = QApplication(sys.argv[:1])  # noqa: F841 - 字体渲染需要
    cfg = default_config()
    renderer = WheelRenderer(cfg.wheel, cfg.items())
    side = int(renderer.diameter)
    img = QImage(side, side, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.paint(painter, 0, 1.0)
    painter.end()

    cx, cy = side // 2, side // 2
    print(f"image={side}x{side}")
    print(f"bg_string={cfg.wheel.theme.bg!r}")
    from PySide6.QtGui import QColor

    qc = QColor(cfg.wheel.theme.bg)
    print(f"QColor(bg) -> rgba({qc.red()},{qc.green()},{qc.blue()},{qc.alpha()})")
    probes = [
        (0, -150, "未选中扇区(右上区域)"),
        (0, -150, "选中扇区(12点)"),
        (-150, 0, "未选中扇区(9点)"),
        (0, 0, "中心"),
        (0, -245, "暗底"),
    ]
    for dx, dy, label in probes:
        c = img.pixelColor(cx + dx, cy + dy)
        print(f"  {label:<22} rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})")
    img.save("probe.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(probe())
