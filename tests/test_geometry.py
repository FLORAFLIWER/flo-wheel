"""轮盘几何的单元测试。

几何错误的表现是"选错扇区"，肉眼很难发现，必须靠测试钉住。
"""

from __future__ import annotations

import math

import pytest

from mousewheel.wheel.geometry import (
    point_at,
    radius_distance,
    sector_count_angles,
    sector_index_at,
    sector_span_deg,
)


@pytest.mark.parametrize("count", [4, 8, 12])
def test_axes_map_to_expected_sectors(count: int) -> None:
    """12 点方向必须是 0 号扇区，顺时针依次递增。

    只对 4/8/12 做坐标轴断言 —— 6 扇区时 90° 恰好是扇区分界线，
    会按"落在后一个扇区"处理（见下一个测试）。
    """
    assert sector_index_at(0, -100, count) == 0  # 12 点
    step = count // 4
    assert sector_index_at(100, 0, count) == step  # 3 点
    assert sector_index_at(0, 100, count) == (step * 2) % count  # 6 点
    assert sector_index_at(-100, 0, count) == (step * 3) % count  # 9 点


def test_six_sectors_axis_is_a_boundary() -> None:
    """6 扇区时每格 60°，90° 正好落在分界线上，归入后一个扇区。"""
    assert sector_index_at(0, -100, 6) == 0
    assert sector_index_at(100, 0, 6) == 2
    # 60° 方向才是 1 号扇区的中心
    a = math.radians(60.0)
    assert sector_index_at(math.sin(a) * 100, -math.cos(a) * 100, 6) == 1


def test_sector_boundaries_with_eight() -> None:
    """8 扇区时，22.5° 是 0 号和 1 号的分界。"""
    # 恰好 22.4°（仍在 0 号）
    a = math.radians(22.0)
    assert sector_index_at(math.sin(a) * 100, -math.cos(a) * 100, 8) == 0
    # 23.0° 已经进 1 号
    a = math.radians(23.0)
    assert sector_index_at(math.sin(a) * 100, -math.cos(a) * 100, 8) == 1
    # 337.5° ~ 22.5° 之间仍是 0 号
    a = math.radians(359.0)
    assert sector_index_at(math.sin(a) * 100, -math.cos(a) * 100, 8) == 0


def test_every_angle_lands_in_some_sector() -> None:
    for count in (4, 6, 8, 12):
        for deg in range(0, 360, 3):
            rad = math.radians(deg)
            idx = sector_index_at(math.sin(rad) * 50, -math.cos(rad) * 50, count)
            assert 0 <= idx < count


def test_span_matches_index() -> None:
    count = 8
    for i in range(count):
        start, end = sector_span_deg(i, count)
        assert end - start == pytest.approx(45.0)
        mid = (start + end) / 2
        rad = math.radians(mid)
        assert sector_index_at(math.sin(rad) * 100, -math.cos(rad) * 100, count) == i


def test_point_at_roundtrip() -> None:
    for deg in (0.0, 45.0, 90.0, 180.0, 270.0, 359.0):
        dx, dy = point_at(deg, 100.0)
        assert radius_distance(dx, dy) == pytest.approx(100.0)
        assert sector_count_angles(0, 8) == 0.0


def test_invalid_count_raises() -> None:
    with pytest.raises(ValueError):
        sector_index_at(1, 1, 0)
