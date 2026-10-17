"""配置模型与读写的测试。"""

from __future__ import annotations

import json

from mousewheel.config.defaults import default_config
from mousewheel.config.model import (
    ALLOWED_SECTORS,
    Action,
    AppConfig,
    SectorItem,
    Theme,
    TriggerSettings,
    WheelSettings,
)
from mousewheel.config.store import ConfigStore


def test_default_config_is_valid() -> None:
    cfg = default_config()
    assert cfg.wheel.sectors == 8
    assert len(cfg.items()) == 8
    assert cfg.trigger.button == "x1"
    assert all(item.label for item in cfg.items())


def test_roundtrip_keeps_everything() -> None:
    cfg = default_config()
    cfg.items()[0].label = "自定义"
    cfg.items()[0].action = Action(type="text", params={"text": "你好"})
    data = cfg.to_dict()
    again = AppConfig.from_dict(json.loads(json.dumps(data)))
    assert again.to_dict() == data
    assert again.items()[0].label == "自定义"
    assert again.items()[0].action.params["text"] == "你好"


def test_sector_count_normalization_keeps_items_in_sync() -> None:
    cfg = default_config()
    cfg.wheel.sectors = 12
    cfg.normalize()
    assert len(cfg.items()) == 12
    cfg.wheel.sectors = 4
    cfg.normalize()
    assert len(cfg.items()) == 4


def test_invalid_sector_count_snaps_to_nearest() -> None:
    wheel = WheelSettings(sectors=7)
    wheel.normalize()
    assert wheel.sectors in ALLOWED_SECTORS
    assert abs(wheel.sectors - 7) <= 1


def test_radii_clamped() -> None:
    wheel = WheelSettings(inner_radius=500, outer_radius=10)
    wheel.normalize()
    assert wheel.inner_radius <= 200
    assert wheel.outer_radius - wheel.inner_radius >= 40


def test_bad_theme_falls_back() -> None:
    theme = Theme(bg="not-a-color", accent="", text="#12345")
    theme.normalize()
    assert theme.bg.startswith("#")
    assert len(theme.bg) in (7, 9)


def test_unknown_fields_are_ignored() -> None:
    cfg = AppConfig.from_dict({"schema": 1, "unknown": {"a": 1}, "trigger": {"wat": 1}})
    assert cfg.trigger.button == "x1"


def test_broken_json_recovers(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    store = ConfigStore(path)
    result = store.load()
    assert result.recovered
    assert result.config.wheel.sectors == 8
    assert (tmp_path / "config.json.broken").exists()


def test_missing_file_creates_default(tmp_path) -> None:
    path = tmp_path / "sub" / "config.json"
    store = ConfigStore(path)
    result = store.load()
    assert result.created
    assert path.exists()


def test_save_is_atomic_and_keeps_backup(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    cfg = default_config()
    store.save(cfg)
    cfg.items()[0].label = "第二次"
    store.save(cfg)
    backup = tmp_path / "config.json.bak"
    assert backup.exists()
    assert "复制" in backup.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("cfg-*.tmp"))


def test_trigger_normalization() -> None:
    trigger = TriggerSettings(button="unicorn", mode="weird", long_press_ms=9999)
    trigger.normalize()
    assert trigger.button == "x1"
    assert trigger.mode == "hold"
    assert trigger.long_press_ms <= 600


def test_left_right_cannot_be_trigger_keys() -> None:
    """左右键一旦被当作触发键，钩子会吞掉它们，鼠标等于瘫痪 —— 必须拒绝。"""
    for bad in ("left", "right"):
        trigger = TriggerSettings(button=bad)
        trigger.normalize()
        assert trigger.button == "x1"


def test_allowed_buttons_are_side_and_middle_only() -> None:
    from mousewheel.config.model import ALLOWED_BUTTONS

    assert set(ALLOWED_BUTTONS) == {"x1", "x2", "middle", "none"}


def test_item_and_action_roundtrip() -> None:
    item = SectorItem.from_dict(
        {"label": "x", "icon": "", "action": {"type": "hotkey", "keys": "Ctrl+C", "repeat": 2}}
    )
    assert item.action.type == "hotkey"
    assert item.action.get("repeat") == 2
    assert item.to_dict()["action"]["keys"] == "Ctrl+C"


def test_legacy_theme_alpha_migrates_to_opacity() -> None:
    """旧版本把透明度写在 bg 的 alpha 里（#AARRGGBB），加载时要迁移到 opacity。"""
    theme = Theme.from_dict({"bg": "#F21B1D22"})

    assert theme.bg == "#1B1D22"  # 只保留 RGB
    assert theme.opacity == 95  # 242 / 255 ≈ 95%


def test_explicit_opacity_wins_over_bg_alpha() -> None:
    theme = Theme.from_dict({"bg": "#80FFFFFF", "opacity": 20})

    assert theme.bg == "#FFFFFF"
    assert theme.opacity == 20


def test_theme_opacity_roundtrip() -> None:
    theme = Theme(bg="#123456", opacity=42)
    theme.normalize()

    data = theme.to_dict()
    assert data["opacity"] == 42
    assert data["bg"] == "#123456"

    again = Theme.from_dict(data)
    assert again.opacity == 42
    assert again.bg == "#123456"


def test_opacity_out_of_range_is_clamped() -> None:
    assert Theme(opacity=999).to_dict()["opacity"] == 999  # to_dict 不做夹紧
    theme = Theme(opacity=999)
    theme.normalize()
    assert theme.opacity == 100
    theme = Theme(opacity=-5)
    theme.normalize()
    assert theme.opacity == 0
