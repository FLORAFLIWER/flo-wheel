"""轮盘几何：角度与扇区的换算。

这些函数是纯函数，不依赖 Qt 也不依赖 Win32，方便单元测试。
角度约定：**0° 指向正上方（12 点），顺时针增大**，与用户直觉一致。
"""

from __future__ import annotations

import math

__all__ = [
    "sector_count_angles",
    "sector_index_at",
    "sector_span_deg",
    "point_at",
    "radius_distance",
    "normalize_angle_deg",
]


def normalize_angle_deg(deg: float) -> float:
    return deg % 360.0


def sector_index_at(dx: float, dy: float, count: int) -> int:
    """把相对中心的偏移量换算成扇区下标。

    dx 向右为正，dy 向下为正（屏幕坐标）。返回 0..count-1。
    """
    if count <= 0:
        raise ValueError("count must be positive")
    # atan2(dx, -dy)：屏幕 y 轴向下，取负让 0° 落在 12 点方向
    angle = math.atan2(dx, -dy)
    if angle < 0:
        angle += 2.0 * math.pi
    step = 2.0 * math.pi / count
    return int((angle + step / 2.0) // step) % count


def sector_span_deg(index: int, count: int) -> tuple[float, float]:
    """扇区 index 覆盖的角度区间 [start, end)，从 12 点顺时针，单位度。"""
    step = 360.0 / count
    center = index * step
    return center - step / 2.0, center + step / 2.0


def sector_count_angles(index: int, count: int) -> float:
    """扇区中心角度（度，从 12 点顺时针）。"""
    return index * (360.0 / count)


def point_at(angle_deg: float, radius: float) -> tuple[float, float]:
    """极坐标（12 点顺时针）转屏幕偏移 (dx, dy)。"""
    rad = math.radians(angle_deg)
    return radius * math.sin(rad), -radius * math.cos(rad)


def radius_distance(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


def qt_arc_params(start_deg: float, end_deg: float) -> tuple[float, float]:
    """把"12 点顺时针"的角度区间翻成 Qt painter.arcTo 的 (起始角, 扫过角)。

    Qt 的角度以 3 点方向为 0、逆时针为正、单位是度（内部再 ×16）。
    """
    qt_start = 90.0 - start_deg
    sweep = -(end_deg - start_deg)
    return qt_start, sweep
