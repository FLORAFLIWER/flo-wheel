"""日志：输出到文件 + 控制台。

自启动时没有控制台，文件日志是排查"为什么没弹出"的唯一线索，
所以滚动日志用 ``RotatingFileHandler``，默认 1MB × 3 份。
"""

from __future__ import annotations

import logging
import logging.handlers

from . import paths

__all__ = ["setup_logging", "LOG_NAME"]

LOG_NAME = "mousewheel.log"


def setup_logging(level: int = logging.INFO, console: bool = True) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            paths.log_dir() / LOG_NAME, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass

    if console:
        import sys

        if sys.stderr is not None:
            stream = logging.StreamHandler()
            stream.setFormatter(fmt)
            root.addHandler(stream)

    return logging.getLogger("mousewheel")
