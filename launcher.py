"""PyInstaller 打包入口。

不能直接把 ``src/mousewheel/__main__.py`` 当脚本打包 —— 那样相对导入
（``from .platform import ...``）会失败。这里用一个薄壳从包入口启动。
"""

from __future__ import annotations

import sys

from mousewheel.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
