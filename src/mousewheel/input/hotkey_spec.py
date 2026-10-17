"""快捷键字符串 ⇄ 虚拟键码。

支持写法：``Ctrl+Shift+S``、``Win+Shift+S``、``Alt+F4``、``Ctrl+Alt+Delete``。
不区分大小写，别名很多（ctrl/control、esc/escape、pgup/pageup……）。

设计上只解析、不做平台调用，因此可以被单元测试完整覆盖；真正按下按键在
:mod:`mousewheel.input.inject` 里。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..platform.win.winapi import VK

__all__ = ["HotkeySpec", "parse_hotkey", "format_hotkey", "normalize_vk", "MODIFIERS"]


class _Mod:
    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    WIN = "win"


#: 修饰键显示顺序
MOD_ORDER = (_Mod.CTRL, _Mod.ALT, _Mod.SHIFT, _Mod.WIN)
MODIFIERS = MOD_ORDER

_MOD_ALIASES = {
    "ctrl": _Mod.CTRL,
    "control": _Mod.CTRL,
    "ctl": _Mod.CTRL,
    "alt": _Mod.ALT,
    "menu": _Mod.ALT,
    "shift": _Mod.SHIFT,
    "win": _Mod.WIN,
    "meta": _Mod.WIN,
    "super": _Mod.WIN,
    "cmd": _Mod.WIN,
}

_MOD_VK = {
    _Mod.CTRL: VK.CONTROL,
    _Mod.ALT: VK.MENU,
    _Mod.SHIFT: VK.SHIFT,
    _Mod.WIN: VK.LWIN,
}


def _build_key_aliases() -> dict[str, int]:
    table: dict[str, int] = {}
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        table[ch] = ord(ch)
    for ch in "0123456789":
        table[ch] = ord(ch)
    for i in range(1, 25):
        table[f"f{i}"] = VK.F1 + i - 1
    for i in range(10):
        table[f"numpad{i}"] = VK.NUMPAD0 + i

    named = {
        "space": VK.SPACE,
        "spacebar": VK.SPACE,
        "enter": VK.RETURN,
        "return": VK.RETURN,
        "tab": VK.TAB,
        "esc": VK.ESCAPE,
        "escape": VK.ESCAPE,
        "backspace": VK.BACK,
        "back": VK.BACK,
        "delete": VK.DELETE,
        "del": VK.DELETE,
        "insert": VK.INSERT,
        "ins": VK.INSERT,
        "home": VK.HOME,
        "end": VK.END,
        "pageup": VK.PRIOR,
        "pgup": VK.PRIOR,
        "pagedown": VK.NEXT,
        "pgdn": VK.NEXT,
        "up": VK.UP,
        "arrowup": VK.UP,
        "down": VK.DOWN,
        "arrowdown": VK.DOWN,
        "left": VK.LEFT,
        "arrowleft": VK.LEFT,
        "right": VK.RIGHT,
        "arrowright": VK.RIGHT,
        "capslock": VK.CAPITAL,
        "caps": VK.CAPITAL,
        "printscreen": VK.SNAPSHOT,
        "prtsc": VK.SNAPSHOT,
        "prtscn": VK.SNAPSHOT,
        "pause": VK.PAUSE,
        "numlock": VK.NUMLOCK,
        "scrolllock": VK.SCROLL,
        "apps": VK.APPS,
        "comma": VK.OEM_COMMA,
        ",": VK.OEM_COMMA,
        "period": VK.OEM_PERIOD,
        ".": VK.OEM_PERIOD,
        "slash": VK.OEM_2,
        "/": VK.OEM_2,
        "semicolon": VK.OEM_1,
        ";": VK.OEM_1,
        "quote": VK.OEM_7,
        "'": VK.OEM_7,
        "bracketleft": VK.OEM_4,
        "[": VK.OEM_4,
        "bracketright": VK.OEM_6,
        "]": VK.OEM_6,
        "backslash": VK.OEM_5,
        "\\": VK.OEM_5,
        "minus": VK.OEM_MINUS,
        "-": VK.OEM_MINUS,
        "equal": VK.OEM_PLUS,
        "=": VK.OEM_PLUS,
        "plus": VK.ADD,
        "grave": VK.OEM_3,
        "`": VK.OEM_3,
        "volup": VK.VOLUME_UP,
        "volumeup": VK.VOLUME_UP,
        "voldown": VK.VOLUME_DOWN,
        "volumedown": VK.VOLUME_DOWN,
        "mute": VK.VOLUME_MUTE,
        "volumemute": VK.VOLUME_MUTE,
        "playpause": VK.MEDIA_PLAY_PAUSE,
        "nexttrack": VK.MEDIA_NEXT_TRACK,
        "prevtrack": VK.MEDIA_PREV_TRACK,
        "mediastop": VK.MEDIA_STOP,
    }
    table.update(named)
    return table


KEY_ALIASES = _build_key_aliases()

#: 需要 KEYEVENTF_EXTENDEDKEY 才能被正确识别的键
EXTENDED_VKS = frozenset(
    {
        VK.UP, VK.DOWN, VK.LEFT, VK.RIGHT,
        VK.INSERT, VK.DELETE, VK.HOME, VK.END, VK.PRIOR, VK.NEXT,
        VK.LWIN, VK.RWIN, VK.APPS, VK.SNAPSHOT,
        VK.DIVIDE, VK.NUMLOCK, VK.RCONTROL, VK.RMENU,
    }
)


#: 左右修饰键归一到通用码：钩子收到的是 LCONTROL(0xA2)，而配置里存的是 CONTROL(0x11)
_VK_NORMALIZE = {
    VK.LSHIFT: VK.SHIFT,
    VK.RSHIFT: VK.SHIFT,
    VK.LCONTROL: VK.CONTROL,
    VK.RCONTROL: VK.CONTROL,
    VK.LMENU: VK.MENU,
    VK.RMENU: VK.MENU,
    VK.RWIN: VK.LWIN,
}


def normalize_vk(vk: int) -> int:
    """把左右区分的虚拟键码（LCONTROL/RCONTROL…）归一成通用码。

    低级键盘钩子送来的码是具体的（左 Ctrl = 0xA2），而用户配置里写的
    ``Ctrl`` 解析出来是 0x11。不归一就永远匹配不上 —— 这正是"按了没反应"的
    经典原因。
    """
    return _VK_NORMALIZE.get(vk, vk)


class HotkeyError(ValueError):
    """快捷键字符串无法解析"""


@dataclass(frozen=True)
class HotkeySpec:
    """解析后的快捷键：修饰键 + 主键"""

    mods: tuple[str, ...]
    vk: int
    source: str

    @property
    def modifier_vks(self) -> list[int]:
        return [_MOD_VK[m] for m in MOD_ORDER if m in self.mods]

    @property
    def all_vks(self) -> list[int]:
        return self.modifier_vks + [self.vk]

    @property
    def is_extended(self) -> bool:
        return self.vk in EXTENDED_VKS

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志
        return format_hotkey(self)


def parse_hotkey(text: str) -> HotkeySpec:
    """把 ``"Ctrl+Shift+S"`` 解析成 :class:`HotkeySpec`。"""
    if not text or not text.strip():
        raise HotkeyError("快捷键为空")

    raw = text.strip()
    parts = [p.strip() for p in raw.split("+")]
    parts = [p for p in parts if p]
    if not parts:
        raise HotkeyError(f"快捷键无法解析: {raw!r}")

    mods: list[str] = []
    vk: int | None = None
    for part in parts:
        low = part.lower()
        if low in _MOD_ALIASES and vk is None:
            mod = _MOD_ALIASES[low]
            if mod not in mods:
                mods.append(mod)
            continue
        if vk is not None:
            raise HotkeyError(f"只能有一个主键: {raw!r}")
        if low in KEY_ALIASES:
            vk = KEY_ALIASES[low]
        elif len(part) == 1:
            upper = part.upper()
            if upper in KEY_ALIASES:
                vk = KEY_ALIASES[upper]
            else:
                raise HotkeyError(f"未知按键: {part!r}")
        else:
            raise HotkeyError(f"未知按键: {part!r}")

    if vk is None:
        raise HotkeyError(f"缺少主键（只有修饰键）: {raw!r}")

    # 无论用户怎么写，修饰键一律按 ctrl/alt/shift/win 的固定顺序存放，
    # 这样显示与发送顺序稳定，比较也方便
    ordered_mods = tuple(mod for mod in MOD_ORDER if mod in mods)
    return HotkeySpec(mods=ordered_mods, vk=vk, source=raw)


def format_hotkey(spec: HotkeySpec) -> str:
    """把 :class:`HotkeySpec` 还原成显示用的字符串。"""
    name = _vk_display_name(spec.vk)
    names = []
    for mod in MOD_ORDER:
        if mod in spec.mods:
            names.append({"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}[mod])
    names.append(name)
    return "+".join(names)


_VK_NAMES = {v: k for k, v in KEY_ALIASES.items() if len(k) > 1}


def _vk_display_name(vk: int) -> str:
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if VK.F1 <= vk <= VK.F24:
        return f"F{vk - VK.F1 + 1}"
    pretty = {
        VK.SPACE: "Space",
        VK.RETURN: "Enter",
        VK.TAB: "Tab",
        VK.ESCAPE: "Esc",
        VK.BACK: "Backspace",
        VK.DELETE: "Delete",
        VK.INSERT: "Insert",
        VK.HOME: "Home",
        VK.END: "End",
        VK.PRIOR: "PageUp",
        VK.NEXT: "PageDown",
        VK.UP: "Up",
        VK.DOWN: "Down",
        VK.LEFT: "Left",
        VK.RIGHT: "Right",
        VK.CAPITAL: "CapsLock",
        VK.SNAPSHOT: "PrintScreen",
        VK.OEM_COMMA: ",",
        VK.OEM_PERIOD: ".",
        VK.OEM_2: "/",
        VK.OEM_1: ";",
        VK.OEM_7: "'",
        VK.OEM_4: "[",
        VK.OEM_6: "]",
        VK.OEM_5: "\\",
        VK.OEM_MINUS: "-",
        VK.OEM_PLUS: "=",
        VK.OEM_3: "`",
        VK.VOLUME_UP: "VolUp",
        VK.VOLUME_DOWN: "VolDown",
        VK.VOLUME_MUTE: "Mute",
        VK.MEDIA_PLAY_PAUSE: "PlayPause",
        VK.MEDIA_NEXT_TRACK: "NextTrack",
        VK.MEDIA_PREV_TRACK: "PrevTrack",
    }
    if vk in pretty:
        return pretty[vk]
    return _VK_NAMES.get(vk, f"VK{vk}")
