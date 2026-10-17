"""快捷键解析测试。"""

from __future__ import annotations

import pytest

from mousewheel.input.hotkey_spec import (
    HotkeyError,
    format_hotkey,
    normalize_vk,
    parse_hotkey,
)
from mousewheel.platform.win.winapi import VK


def test_simple_combination() -> None:
    spec = parse_hotkey("Ctrl+Shift+S")
    assert spec.mods == ("ctrl", "shift")
    assert spec.vk == ord("S")
    assert spec.modifier_vks == [VK.CONTROL, VK.SHIFT]


def test_case_insensitive_and_aliases() -> None:
    assert parse_hotkey("control+c").vk == ord("C")
    assert parse_hotkey("CTRL+C").mods == ("ctrl",)
    assert parse_hotkey("Win+Shift+S").mods == ("shift", "win")


def test_modifier_order_is_normalized() -> None:
    """用户怎么写都行，内部统一成 ctrl → alt → shift → win。"""
    assert parse_hotkey("Shift+Win+S").mods == parse_hotkey("Win+Shift+S").mods
    assert parse_hotkey("Win+Shift+S").mods == ("shift", "win")


def test_win_key_order_is_normalized() -> None:
    spec = parse_hotkey("Shift+Win+S")
    # 显示/发送时顺序固定为 ctrl, alt, shift, win
    assert spec.mods == ("shift", "win")
    assert spec.modifier_vks == [VK.SHIFT, VK.LWIN]


def test_function_keys() -> None:
    assert parse_hotkey("F1").vk == VK.F1
    assert parse_hotkey("F12").vk == VK.F1 + 11
    assert parse_hotkey("F24").vk == VK.F24
    assert parse_hotkey("f5").vk == VK.F1 + 4


def test_named_keys() -> None:
    assert parse_hotkey("Ctrl+Space").vk == VK.SPACE
    assert parse_hotkey("Alt+Tab").vk == VK.TAB
    assert parse_hotkey("Esc").vk == VK.ESCAPE
    assert parse_hotkey("PageUp").vk == VK.PRIOR
    assert parse_hotkey("Win+D").vk == ord("D")


def test_punctuation() -> None:
    assert parse_hotkey("Ctrl+,").vk == VK.OEM_COMMA
    assert parse_hotkey("Ctrl+.").vk == VK.OEM_PERIOD
    assert parse_hotkey("Ctrl+/").vk == VK.OEM_2
    assert parse_hotkey("Ctrl+;").vk == VK.OEM_1


def test_media_keys() -> None:
    assert parse_hotkey("VolUp").vk == VK.VOLUME_UP
    assert parse_hotkey("PlayPause").vk == VK.MEDIA_PLAY_PAUSE


def test_extended_flag_for_arrows() -> None:
    assert parse_hotkey("Ctrl+Left").is_extended
    assert not parse_hotkey("Ctrl+C").is_extended


def test_format_roundtrip() -> None:
    for text in ("Ctrl+C", "Ctrl+Shift+S", "Shift+Win+S", "Alt+F4", "F5"):
        assert format_hotkey(parse_hotkey(text)) == text


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "Ctrl", "Ctrl+Shift", "Ctrl+Nope", "A+B"],
)
def test_invalid_inputs(bad: str) -> None:
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (VK.LCONTROL, VK.CONTROL),
        (VK.RCONTROL, VK.CONTROL),
        (VK.LSHIFT, VK.SHIFT),
        (VK.RSHIFT, VK.SHIFT),
        (VK.LMENU, VK.MENU),
        (VK.RMENU, VK.MENU),
        (VK.RWIN, VK.LWIN),
        (ord("A"), ord("A")),
        (VK.F1 + 4, VK.F1 + 4),  # F5
    ],
)
def test_normalize_vk(raw: int, expected: int) -> None:
    assert normalize_vk(raw) == expected
