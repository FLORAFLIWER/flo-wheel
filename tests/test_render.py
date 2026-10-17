"""渲染层测试：透明度和尺寸必须真的反映到像素上。

这些断言比"截个图看看"可靠 —— 透明度曾经写错成 #RRGGBBAA 顺序，
肉眼只觉得"有点怪"，像素值不会说谎。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from mousewheel.config.defaults import default_config
from mousewheel.wheel.renderer import WheelRenderer


def render(settings, selected=None) -> QImage:
    renderer = WheelRenderer(settings, default_config().items())
    side = int(renderer.diameter)
    image = QImage(side, side, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.paint(painter, selected, 1.0)
    painter.end()
    return image


def sample_sector(image: QImage):
    """取 9 点方向的未选中扇区像素（内径与外径之间）。"""
    cx = image.width() // 2
    return image.pixelColor(cx - 150, image.height() // 2)


def test_opacity_controls_background_alpha(qt_app) -> None:
    opaque_cfg = default_config().wheel
    opaque_cfg.theme.opacity = 100
    translucent_cfg = default_config().wheel
    translucent_cfg.theme.opacity = 30

    opaque = sample_sector(render(opaque_cfg))
    translucent = sample_sector(render(translucent_cfg))

    assert opaque.alpha() > 240
    assert translucent.alpha() < 130
    assert opaque.alpha() > translucent.alpha() + 80


def test_zero_opacity_is_almost_invisible(qt_app) -> None:
    cfg = default_config().wheel
    cfg.theme.opacity = 0
    pixel = sample_sector(render(cfg))
    assert pixel.alpha() < 30


def test_background_colour_is_applied(qt_app) -> None:
    cfg = default_config().wheel
    cfg.theme.opacity = 100
    cfg.theme.bg = "#FF0000"
    pixel = sample_sector(render(cfg))
    assert pixel.red() > 200
    assert pixel.green() < 80


def test_accent_is_used_for_selected_sector(qt_app) -> None:
    cfg = default_config().wheel
    cfg.theme.opacity = 100
    cfg.theme.accent = "#00FF00"
    image = render(cfg, selected=0)
    # 12 点方向、半径 150 处是 0 号扇区
    cx, cy = image.width() // 2, image.height() // 2
    pixel = image.pixelColor(cx, cy - 150)
    assert pixel.green() > 200
    assert pixel.red() < 80


def test_diameter_follows_radii() -> None:
    cfg = default_config().wheel
    renderer = WheelRenderer(cfg, default_config().items())
    small = renderer.diameter
    cfg.outer_radius = 100
    renderer.update(cfg, default_config().items())
    assert renderer.diameter < small
