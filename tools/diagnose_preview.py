"""打开"检测鼠标按键"窗口，并自动注入一次中键，验证它真的能看到按键。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from mousewheel.logging_setup import setup_logging
    from mousewheel.platform.win import dpi

    dpi.enable()
    app = QApplication([sys.argv[0]])
    setup_logging(console=False)

    from mousewheel.app import AppController
    from mousewheel.ui.diagnose import MouseDiagnoseDialog

    controller = AppController()
    controller.start()

    dialog = MouseDiagnoseDialog(controller)
    dialog.show()
    dialog.raise_()

    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")

    def inject() -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "inject_mouse.py"),
             "--button", "middle", "--hold", "150"],
            env=env,
            stdout=subprocess.DEVNULL,
            check=False,
        )

    def snap() -> None:
        out = ROOT / "docs" / "diagnose.png"
        dialog.grab().save(str(out))
        print(f"已保存 {out}", flush=True)
        app.quit()

    QTimer.singleShot(900, inject)
    QTimer.singleShot(2200, snap)
    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
