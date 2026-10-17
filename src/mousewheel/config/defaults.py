"""开箱即用的默认配置。

按方位从 12 点顺时针排列，都是几乎所有 Windows 程序都认的组合键。
"""

from __future__ import annotations

from .model import Action, AppConfig, Page, SectorItem

__all__ = ["default_config", "DEFAULT_ITEMS"]


def _item(label: str, keys: str) -> SectorItem:
    return SectorItem(label=label, icon="", action=Action(type="hotkey", params={"keys": keys}))


DEFAULT_ITEMS: list[SectorItem] = [
    _item("复制", "Ctrl+C"),          # 12 点
    _item("粘贴", "Ctrl+V"),          # 1:30
    _item("剪切", "Ctrl+X"),          # 3 点
    _item("撤销", "Ctrl+Z"),          # 4:30
    _item("全选", "Ctrl+A"),          # 6 点
    _item("截图", "Win+Shift+S"),     # 7:30
    SectorItem(
        label="浏览器",
        icon="",
        action=Action(type="url", params={"url": "https://www.bing.com"}),
    ),                                # 9 点
    SectorItem(
        label="锁屏",
        icon="",
        action=Action(type="system", params={"cmd": "lock"}),
    ),                                # 10:30
]


def default_config() -> AppConfig:
    cfg = AppConfig()
    cfg.pages = [Page(name="main", items=[SectorItem.from_dict(i.to_dict()) for i in DEFAULT_ITEMS])]
    cfg.normalize()
    return cfg
