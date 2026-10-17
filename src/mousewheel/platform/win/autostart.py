"""开机自启动：只走当前用户注册表 Run 项。

为什么不用任务计划/服务：
- 用户明确不需要管理员权限，Run 项最省心，不弹 UAC
- 任务计划适合提权场景，这里用不上

关键细节：每次启动都要**校验**注册表里的路径是否还指向自己。程序被移动或
改名后，Run 项会悄悄失效，用户以为"自启开着"其实早就没生效了。
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from ... import paths

__all__ = [
    "RUN_KEY",
    "VALUE_NAME",
    "is_enabled",
    "current_command",
    "enable",
    "disable",
    "sync",
    "autostart_command",
]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FLO-Wheel"
#: 改名前的注册表值名，启用时会顺手清掉，避免自启动两份
LEGACY_VALUE_NAMES = ("MouseWheel",)
AUTOSTART_ARG = "--autostart"


def launch_target() -> Path:
    """自启动时应该执行的路径。

    打包后是 exe 本身；开发模式下退化为 ``pythonw.exe -m mousewheel``，
    这样自启动也能用于调试（不建议长期这样用）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    import shutil

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable).resolve()
    return exe


def autostart_command() -> str:
    target = launch_target()
    if getattr(sys, "frozen", False):
        return f'"{target}" {AUTOSTART_ARG}'
    pkg_parent = Path(__file__).resolve().parents[3]
    return f'"{target}" -m mousewheel {AUTOSTART_ARG}'


def current_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def is_enabled() -> bool:
    """注册表里有这一项就算开启（不管路径是否过期）。"""
    return current_command() is not None


def _expected_path_part() -> str:
    return str(launch_target()).lower()


def is_current() -> bool:
    """Run 项存在且指向当前程序。"""
    cmd = current_command()
    if not cmd:
        return False
    return _expected_path_part() in cmd.lower()


def enable() -> bool:
    """写入 Run 项，返回是否成功。"""
    command = autostart_command()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
            for legacy in LEGACY_VALUE_NAMES:
                try:
                    winreg.DeleteValue(key, legacy)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def disable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in (VALUE_NAME, *LEGACY_VALUE_NAMES):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def sync(desired: bool) -> tuple[bool, str]:
    """把注册表对齐到用户设置，并回报实际状态。

    返回 ``(实际是否启用, 给用户看的说明)``。
    """
    if desired:
        if is_current():
            return True, "已启用（开机自动启动）"
        if not enable():
            return is_enabled(), "写入注册表失败，可能被安全软件拦截"
        return True, "已启用（开机自动启动）"
    disable()
    if is_enabled():
        return True, "关闭失败，注册表项仍在"
    return False, "未启用"
