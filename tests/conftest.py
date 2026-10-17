"""pytest 公共设置与 fixture。

设置窗口、渲染器的测试需要 QApplication；用 offscreen 平台避免真的弹窗。
这个环境变量必须在任何 Qt 对象创建之前设置。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
