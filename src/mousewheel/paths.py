"""路径约定。

便携模式：exe 同目录存在 ``portable.flag`` 时，配置与日志都放在 exe 旁边，
否则放用户目录（%APPDATA% / %LOCALAPPDATA%）。

之所以默认不放 exe 目录：程序装在 Program Files 或 OneDrive 里时，
exe 目录经常不可写或会被同步冲突。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "APP_NAME",
    "portable_root",
    "is_portable",
    "app_data_dir",
    "config_path",
    "log_dir",
    "state_path",
    "install_dir",
    "executable",
]

APP_NAME = "MouseWheel"


def executable() -> Path:
    """当前可执行文件（打包后是 exe，开发时是 python.exe）。"""
    return Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def install_dir() -> Path:
    """程序安装目录（exe 所在目录）。"""
    return _exe_dir()


def portable_root() -> Path:
    return _exe_dir()


def is_portable() -> bool:
    try:
        return (portable_root() / "portable.flag").exists()
    except OSError:
        return False


def app_data_dir() -> Path:
    if is_portable():
        target = portable_root() / "data"
    else:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        target = Path(base) / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def log_dir() -> Path:
    if is_portable():
        target = portable_root() / "logs"
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        target = Path(base) / APP_NAME / "logs"
    target.mkdir(parents=True, exist_ok=True)
    return target


def config_path() -> Path:
    return app_data_dir() / "config.json"


def state_path() -> Path:
    """运行时状态（非用户配置），例如上次安装位置。"""
    return app_data_dir() / "state.json"
