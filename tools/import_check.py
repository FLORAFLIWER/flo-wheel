"""静态自检：逐个导入所有模块，把 ImportError 在启动前暴露出来。

比等到运行时崩溃好得多 —— 尤其是那些藏在动作/UI 分支里的 import。
"""

from __future__ import annotations

import importlib
import sys
import traceback

MODULES = [
    "mousewheel.paths",
    "mousewheel.logging_setup",
    "mousewheel.config.model",
    "mousewheel.config.defaults",
    "mousewheel.config.store",
    "mousewheel.platform.win.winapi",
    "mousewheel.platform.win.dpi",
    "mousewheel.platform.win.clipboard",
    "mousewheel.platform.win.autostart",
    "mousewheel.platform.win.single_instance",
    "mousewheel.platform.win.hotkeys",
    "mousewheel.input.hotkey_spec",
    "mousewheel.input.inject",
    "mousewheel.input.trigger",
    "mousewheel.input.mouse_hook",
    "mousewheel.input.key_combo",
    "mousewheel.input.key_hook",
    "mousewheel.actions.base",
    "mousewheel.actions.builtin",
    "mousewheel.actions.registry",
    "mousewheel.wheel.geometry",
    "mousewheel.wheel.renderer",
    "mousewheel.wheel.overlay",
    "mousewheel.ui.tray",
    "mousewheel.ui.settings_window",
    "mousewheel.ui.diagnose",
    "mousewheel.app",
    "mousewheel.__main__",
]


def main() -> int:
    failed = 0
    for name in MODULES:
        try:
            importlib.import_module(name)
            print(f"ok   {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(MODULES) - failed}/{len(MODULES)} 个模块导入成功")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
