"""生成应用图标。

复用托盘图标的绘制代码，保证 exe / 快捷方式 / 托盘三处视觉一致。
输出多个尺寸的 PNG，再由 Pillow 合成 .ico（Qt 的 ico 写入插件不可靠）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication([sys.argv[0]])  # noqa: F841

    from mousewheel.ui.tray import build_icon

    out_dir = ROOT / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = build_icon(size).pixmap(size, size)
        path = out_dir / f"icon_{size}.png"
        pixmap.save(str(path))
        print(path)
    # 256 拷贝一份给 Pillow 用
    build_icon(256).pixmap(256, 256).save(str(out_dir / "icon.png"))
    print(out_dir / "icon.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
