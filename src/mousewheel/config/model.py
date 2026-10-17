"""配置数据模型。

设计原则：
1. 全程容错 —— 缺失字段用默认值补齐，未知字段忽略，坏 JSON 不炸程序
2. 只做数据与校验，不做 IO（IO 在 :mod:`store`）
3. 每个字段都有明确的取值范围，``normalize()`` 负责夹紧
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "Action",
    "SectorItem",
    "Page",
    "TriggerSettings",
    "Theme",
    "WheelSettings",
    "StartupSettings",
    "AppConfig",
    "ALLOWED_SECTORS",
]

SCHEMA_VERSION = 1
ALLOWED_SECTORS = (4, 6, 8, 12)
#: 只允许侧键和中键做触发键。
#: 刻意不支持左键/右键 —— 那两键被钩子吞掉后鼠标等于瘫痪（点不了任何东西），
#: 用户会以为程序把鼠标搞坏了。想要键盘党用「键盘触发键」。
ALLOWED_BUTTONS = ("x1", "x2", "middle", "none")
ALLOWED_MODES = ("hold", "toggle")


def _as_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off", ""):
            return False
    return default


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _parse_hex_color(value: Any) -> tuple[str, int] | None:
    """解析颜色字符串，返回 ("#RRGGBB", alpha 0-255)。

    同时接受 ``#RRGGBB`` 和 Qt 的 ``#AARRGGBB``（透明度写在前面）。
    注意 Qt 的这种顺序很容易写反 —— 早期版本就因为这个 bug 把边框画成了黄色。
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("#"):
        return None
    body = text[1:]
    if len(body) not in (6, 8):
        return None
    try:
        int(body, 16)
    except ValueError:
        return None
    if len(body) == 6:
        return "#" + body.upper(), 255
    return "#" + body[2:].upper(), int(body[:2], 16)


def _alpha_to_percent(alpha: int) -> int:
    return max(0, min(100, round(alpha / 255.0 * 100)))


@dataclass
class Action:
    """扇区要执行的动作。参数放 dict，便于以后加新类型而不改 schema。"""

    type: str = "none"
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.params}

    @classmethod
    def from_dict(cls, raw: Any) -> "Action":
        if not isinstance(raw, dict):
            return cls()
        params = {k: v for k, v in raw.items() if k != "type"}
        return cls(type=_as_str(raw.get("type"), "none").strip().lower() or "none", params=params)

    @property
    def is_empty(self) -> bool:
        return self.type in ("", "none")


@dataclass
class SectorItem:
    label: str = ""
    icon: str = ""
    action: Action = field(default_factory=Action)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "icon": self.icon, "action": self.action.to_dict()}

    @classmethod
    def from_dict(cls, raw: Any) -> "SectorItem":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            label=_as_str(raw.get("label")),
            icon=_as_str(raw.get("icon")),
            action=Action.from_dict(raw.get("action")),
        )


@dataclass
class Page:
    name: str = "main"
    items: list[SectorItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, raw: Any) -> "Page":
        if not isinstance(raw, dict):
            return cls()
        items_raw = raw.get("items")
        items = [SectorItem.from_dict(x) for x in items_raw] if isinstance(items_raw, list) else []
        return cls(name=_as_str(raw.get("name"), "main") or "main", items=items)


@dataclass
class TriggerSettings:
    button: str = "x1"
    key: str = ""              # 键盘热键（可选），如 "Ctrl+Alt+Space"
    mode: str = "hold"         # hold | toggle
    long_press_ms: int = 180
    fast_click_passthrough: bool = True

    def normalize(self) -> None:
        if self.button not in ALLOWED_BUTTONS:
            self.button = "x1"
        if self.mode not in ALLOWED_MODES:
            self.mode = "hold"
        self.long_press_ms = _as_int(self.long_press_ms, 180, 80, 600)
        self.fast_click_passthrough = _as_bool(self.fast_click_passthrough, True)
        self.key = _as_str(self.key).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "button": self.button,
            "key": self.key,
            "mode": self.mode,
            "long_press_ms": self.long_press_ms,
            "fast_click_passthrough": self.fast_click_passthrough,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "TriggerSettings":
        raw = raw if isinstance(raw, dict) else {}
        obj = cls(
            button=_as_str(raw.get("button"), "x1").lower(),
            key=_as_str(raw.get("key")),
            mode=_as_str(raw.get("mode"), "hold").lower(),
            long_press_ms=_as_int(raw.get("long_press_ms"), 180, 80, 600),
            fast_click_passthrough=_as_bool(raw.get("fast_click_passthrough"), True),
        )
        obj.normalize()
        return obj


@dataclass
class Theme:
    """配色。

    ``bg`` 只存六位 RGB，透明度单独由 ``opacity``（0-100）控制 —— 这样用户
    拖透明度滑块不会破坏底色，取色器改颜色也不会把透明度弄丢。
    早期版本把透明度塞在 ``bg`` 的 alpha 里（``#AARRGGBB``），
    :meth:`from_dict` 会自动迁移过来。
    """

    bg: str = "#1B1D22"
    opacity: int = 95
    accent: str = "#4C8DFF"
    text: str = "#FFFFFF"
    border: str = "#59FFFFFF"
    text_dim: str = "#99FFFFFF"

    def normalize(self) -> None:
        parsed = _parse_hex_color(self.bg)
        if parsed is None:
            self.bg = Theme().bg
        else:
            # 只留 RGB；旧配置里存在的 alpha 已在 from_dict 转成 opacity
            self.bg = parsed[0]
        self.opacity = _as_int(self.opacity, 95, 0, 100)
        for name in ("accent", "text", "border", "text_dim"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.startswith("#") or len(value) not in (7, 9):
                setattr(self, name, getattr(Theme(), name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bg": self.bg,
            "opacity": self.opacity,
            "accent": self.accent,
            "text": self.text,
            "border": self.border,
            "text_dim": self.text_dim,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Theme":
        raw = raw if isinstance(raw, dict) else {}
        parsed = _parse_hex_color(raw.get("bg"))
        bg_rgb, bg_alpha = parsed if parsed else (Theme().bg, 242)
        opacity_raw = raw.get("opacity")
        if opacity_raw is None:
            # 旧配置没有 opacity 字段：从 bg 的 alpha 推导，保持观感不变
            opacity = _alpha_to_percent(bg_alpha)
        else:
            opacity = _as_int(opacity_raw, 95, 0, 100)
        obj = cls(
            bg=bg_rgb,
            opacity=opacity,
            accent=_as_str(raw.get("accent"), "#4C8DFF"),
            text=_as_str(raw.get("text"), "#FFFFFF"),
            border=_as_str(raw.get("border"), "#59FFFFFF"),
            text_dim=_as_str(raw.get("text_dim"), "#99FFFFFF"),
        )
        obj.normalize()
        return obj


@dataclass
class WheelSettings:
    sectors: int = 8
    inner_radius: int = 72
    outer_radius: int = 230
    dead_zone: int = 24
    animate_ms: int = 120
    center_on: str = "cursor"     # cursor | screen
    hold_commit_on_deadzone: bool = False
    font_size: int = 13
    theme: Theme = field(default_factory=Theme)

    def normalize(self) -> None:
        if self.sectors not in ALLOWED_SECTORS:
            self.sectors = min(ALLOWED_SECTORS, key=lambda s: abs(s - _as_int(self.sectors, 8, 4, 12)))
        self.inner_radius = _as_int(self.inner_radius, 72, 30, 200)
        self.outer_radius = _as_int(self.outer_radius, 230, 80, 600)
        if self.outer_radius - self.inner_radius < 40:
            self.outer_radius = self.inner_radius + 40
        self.dead_zone = _as_int(self.dead_zone, 24, 0, max(0, self.inner_radius - 4))
        self.animate_ms = _as_int(self.animate_ms, 120, 0, 600)
        if self.center_on not in ("cursor", "screen"):
            self.center_on = "cursor"
        self.font_size = _as_int(self.font_size, 13, 8, 40)
        self.hold_commit_on_deadzone = _as_bool(self.hold_commit_on_deadzone, False)
        self.theme.normalize()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectors": self.sectors,
            "inner_radius": self.inner_radius,
            "outer_radius": self.outer_radius,
            "dead_zone": self.dead_zone,
            "animate_ms": self.animate_ms,
            "center_on": self.center_on,
            "hold_commit_on_deadzone": self.hold_commit_on_deadzone,
            "font_size": self.font_size,
            "theme": self.theme.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "WheelSettings":
        raw = raw if isinstance(raw, dict) else {}
        obj = cls(
            sectors=_as_int(raw.get("sectors"), 8, 4, 12),
            inner_radius=_as_int(raw.get("inner_radius"), 72, 30, 200),
            outer_radius=_as_int(raw.get("outer_radius"), 230, 80, 600),
            dead_zone=_as_int(raw.get("dead_zone"), 24, 0, 400),
            animate_ms=_as_int(raw.get("animate_ms"), 120, 0, 600),
            center_on=_as_str(raw.get("center_on"), "cursor"),
            hold_commit_on_deadzone=_as_bool(raw.get("hold_commit_on_deadzone"), False),
            font_size=_as_int(raw.get("font_size"), 13, 8, 40),
            theme=Theme.from_dict(raw.get("theme")),
        )
        obj.normalize()
        return obj


@dataclass
class StartupSettings:
    enabled: bool = True
    delay_s: int = 5

    def normalize(self) -> None:
        self.enabled = _as_bool(self.enabled, True)
        self.delay_s = _as_int(self.delay_s, 5, 0, 120)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "delay_s": self.delay_s}

    @classmethod
    def from_dict(cls, raw: Any) -> "StartupSettings":
        raw = raw if isinstance(raw, dict) else {}
        obj = cls(
            enabled=_as_bool(raw.get("enabled"), True),
            delay_s=_as_int(raw.get("delay_s"), 5, 0, 120),
        )
        obj.normalize()
        return obj


@dataclass
class AppConfig:
    schema: int = SCHEMA_VERSION
    trigger: TriggerSettings = field(default_factory=TriggerSettings)
    wheel: WheelSettings = field(default_factory=WheelSettings)
    pages: list[Page] = field(default_factory=list)
    startup: StartupSettings = field(default_factory=StartupSettings)

    # ---- 便捷访问 --------------------------------------------------------

    @property
    def main_page(self) -> Page:
        if not self.pages:
            self.pages.append(Page(name="main", items=[]))
        return self.pages[0]

    def items(self) -> list[SectorItem]:
        """当前扇区内容，长度一定等于 ``wheel.sectors``。"""
        page = self.main_page
        count = self.wheel.sectors
        items = list(page.items[:count])
        while len(items) < count:
            items.append(SectorItem())
        return items

    def set_items(self, items: list[SectorItem]) -> None:
        self.main_page.items = list(items)

    def normalize(self) -> None:
        self.trigger.normalize()
        self.wheel.normalize()
        self.startup.normalize()
        if not isinstance(self.pages, list) or not self.pages:
            self.pages = [Page(name="main")]
        # 扇区数量变了要补齐；但**不截断**，这样用户临时调小再调回来时配置还在
        page = self.main_page
        count = self.wheel.sectors
        while len(page.items) < count:
            page.items.append(SectorItem())
        self.schema = SCHEMA_VERSION

    # ---- 序列化 ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "trigger": self.trigger.to_dict(),
            "wheel": self.wheel.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
            "startup": self.startup.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "AppConfig":
        raw = raw if isinstance(raw, dict) else {}
        pages_raw = raw.get("pages")
        pages = [Page.from_dict(x) for x in pages_raw] if isinstance(pages_raw, list) else []
        obj = cls(
            schema=_as_int(raw.get("schema"), SCHEMA_VERSION, 0, 999),
            trigger=TriggerSettings.from_dict(raw.get("trigger")),
            wheel=WheelSettings.from_dict(raw.get("wheel")),
            pages=pages,
            startup=StartupSettings.from_dict(raw.get("startup")),
        )
        obj.normalize()
        return obj

    def clone(self) -> "AppConfig":
        return AppConfig.from_dict(self.to_dict())
