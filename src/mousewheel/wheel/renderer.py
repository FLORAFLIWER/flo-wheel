"""轮盘绘制。

全部用 QPainter 矢量绘制，不依赖图片资源：
- 暗底圆 → 让轮盘在浅色窗口上也看得清
- N 个环形扇区，选中项填充主色并向外扩 4px
- 中心圆显示当前选中项名称，未选中时显示提示语
- `progress` (0..1) 控制出现动画：缩放 0.9→1.0 与整体淡入
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from ..config.model import SectorItem, Theme, WheelSettings
from .geometry import point_at, sector_count_angles, sector_span_deg

__all__ = ["WheelRenderer", "sector_path"]

#: 选中扇区比未选中外扩的像素
_SELECTED_GROW = 5.0
#: 暗底比外径大出的像素
_BACKDROP_PAD = 20.0


def sector_path(inner: float, outer: float, start_deg: float, end_deg: float) -> QPainterPath:
    """构造一个环形扇区的路径（圆心在坐标原点）。"""
    qt_start = 90.0 - start_deg
    sweep = -(end_deg - start_deg)
    outer_rect = QRectF(-outer, -outer, outer * 2.0, outer * 2.0)
    inner_rect = QRectF(-inner, -inner, inner * 2.0, inner * 2.0)

    path = QPainterPath()
    path.arcMoveTo(outer_rect, qt_start)
    path.arcTo(outer_rect, qt_start, sweep)
    path.arcTo(inner_rect, qt_start + sweep, -sweep)
    path.closeSubpath()
    return path


class WheelRenderer:
    def __init__(self, settings: WheelSettings, items: list[SectorItem]) -> None:
        self.settings = settings
        self.items = items

    # ---- 尺寸 ------------------------------------------------------------

    @property
    def diameter(self) -> float:
        return (self.settings.outer_radius + _BACKDROP_PAD) * 2.0

    def update(self, settings: WheelSettings, items: list[SectorItem]) -> None:
        self.settings = settings
        self.items = items

    # ---- 绘制 ------------------------------------------------------------

    def paint(self, painter: QPainter, selected: int | None, progress: float) -> None:
        settings = self.settings
        theme = settings.theme
        count = max(1, settings.sectors)
        inner = settings.inner_radius
        outer = settings.outer_radius
        center = QPointF(self.diameter / 2.0, self.diameter / 2.0)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, progress)))
        painter.translate(center)
        scale = 0.90 + 0.10 * max(0.0, min(1.0, progress))
        painter.scale(scale, scale)

        # 1. 暗底（跟随背景不透明度，否则调透明后会剩一圈黑影）
        painter.setPen(Qt.PenStyle.NoPen)
        backdrop_alpha = int(round(90 * max(0, min(100, theme.opacity)) / 100.0))
        painter.setBrush(QColor(0, 0, 0, backdrop_alpha))
        painter.drawEllipse(QPointF(0, 0), outer + _BACKDROP_PAD * 0.6, outer + _BACKDROP_PAD * 0.6)

        bg = QColor(theme.bg)
        # 底色只存 RGB，透明度由 theme.opacity 决定
        bg.setAlpha(int(round(255 * max(0, min(100, theme.opacity)) / 100.0)))
        # 扇区底色比整体背景略亮一档，做出层次感（否则和暗底糊在一起）
        sector_bg = QColor(bg).lighter(118)
        sector_bg.setAlpha(bg.alpha())
        border = QColor(theme.border)
        accent = QColor(theme.accent)
        text_color = QColor(theme.text)
        dim = QColor(theme.text_dim)

        # 2. 未选中的扇区
        for i in range(count):
            if i == selected:
                continue
            start, end = sector_span_deg(i, count)
            path = sector_path(inner, outer, start + 0.35, end - 0.35)
            painter.setBrush(sector_bg)
            painter.setPen(QPen(border, 1.0))
            painter.drawPath(path)

        # 3. 选中的扇区（画在最上面）
        if selected is not None:
            start, end = sector_span_deg(selected, count)
            path = sector_path(
                max(4.0, inner - 3.0),
                outer + _SELECTED_GROW,
                start + 0.35,
                end - 0.35,
            )
            painter.setBrush(accent)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 1.6))
            painter.drawPath(path)

        # 4. 中心圆
        hub_r = max(18.0, inner - 8.0)
        hub_bg = QColor(bg)
        hub_bg.setAlpha(min(255, bg.alpha() + 20))
        painter.setBrush(hub_bg)
        accent_edge = QColor(accent)
        accent_edge.setAlpha(70)
        painter.setPen(QPen(accent_edge, 1.4))
        painter.drawEllipse(QPointF(0, 0), hub_r, hub_r)

        # 5. 扇区文字
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(9, int(settings.font_size)))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        label_radius = (inner + outer) / 2.0
        for i in range(count):
            label = (self.items[i].label if i < len(self.items) else "").strip()
            if not label:
                continue
            dx, dy = point_at(sector_count_angles(i, count), label_radius)
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(outer - inner - 8))
            painter.setPen(text_color if i == selected else dim)
            rect = QRectF(dx - 80, dy - 12, 160, 24)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        # 6. 中心文字
        center_font = QFont("Microsoft YaHei UI")
        center_font.setPixelSize(max(11, int(settings.font_size) + 1))
        center_font.setBold(True)
        painter.setFont(center_font)
        if selected is not None and selected < len(self.items):
            center_text = self.items[selected].label or ""
            painter.setPen(text_color)
        else:
            center_text = "松开取消" if count else ""
            painter.setPen(dim)
        painter.drawText(
            QRectF(-hub_r, -hub_r, hub_r * 2, hub_r * 2),
            Qt.AlignmentFlag.AlignCenter,
            center_text,
        )

        painter.restore()
