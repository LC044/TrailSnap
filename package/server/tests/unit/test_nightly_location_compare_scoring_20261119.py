"""覆盖 app/crud/location.py 中此前没有测试引用的三个比较评分函数。

盲区来源：函数级静态引用扫描命中 _haversine_km / _orientation_compatible /
_comparison_score。

它们是「同时光对比」的纯计算内核：
- _haversine_km 计算两点球面距离，超过半径的候选必须被排除；
- _orientation_compatible 保证横构图不会与竖构图配对；
- _comparison_score 按 视觉 / 距离 / 时间 三个权重打分，
  且在缺少 embedding 时仍保留 0.55 距离 + 0.45 时间的兜底分。

既有测试只走 get_time_compare_summary 的整体流程，从未直接断言这些边界行为。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.crud import location

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _photo(photo_time, width=100, height=100):
    return SimpleNamespace(photo_time=photo_time, width=width, height=height)


def _metadata(latitude=31.2304, longitude=121.4737):
    return SimpleNamespace(latitude=latitude, longitude=longitude)


def test_haversine_distance_is_zero_for_the_same_point():
    assert location._haversine_km(31.2304, 121.4737, 31.2304, 121.4737) == pytest.approx(0.0, abs=1e-9)


def test_haversine_distance_matches_a_known_degree_of_latitude():
    distance = location._haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 111.0 < distance < 111.5


def test_haversine_distance_is_symmetric():
    forward = location._haversine_km(31.2304, 121.4737, 39.9042, 116.4074)
    backward = location._haversine_km(39.9042, 116.4074, 31.2304, 121.4737)
    assert forward == pytest.approx(backward)


def test_orientation_is_derived_from_the_aspect_ratio():
    assert location._photo_orientation(_photo(None, 200, 100)) == "landscape"
    assert location._photo_orientation(_photo(None, 100, 200)) == "portrait"
    assert location._photo_orientation(_photo(None, 100, 100)) == "square"


def test_orientation_compatibility_blocks_mixed_orientations():
    landscape = _photo(None, 200, 100)
    portrait = _photo(None, 100, 200)
    square = _photo(None, 100, 100)
    assert location._orientation_compatible(landscape, landscape) is True
    assert location._orientation_compatible(landscape, portrait) is False
    assert location._orientation_compatible(square, landscape) is False


def test_orientation_compatibility_allows_unknown_orientations():
    unknown = SimpleNamespace(photo_time=datetime(2026, 1, 1), width=None, height=None)
    landscape = _photo(None, 200, 100)
    # 缺少尺寸信息时不得把候选误判为不兼容。
    assert location._orientation_compatible(unknown, landscape) is True
    assert location._orientation_compatible(landscape, unknown) is True


def test_comparison_score_without_embeddings_falls_back_to_distance_and_time():
    time = datetime(2026, 5, 20, 10, 0)
    reference = _photo(time)
    candidate = _photo(time)
    score = location._comparison_score(reference, _metadata(), candidate, _metadata())
    # 距离为 0 -> 距离分 1.0；时间差为 0 -> 时间分 0.0。
    assert score == pytest.approx(0.55)


def test_comparison_score_uses_the_visual_weight_when_embeddings_are_present():
    time = datetime(2026, 5, 20, 10, 0)
    reference = _photo(time)
    candidate = _photo(time)
    score = location._comparison_score(
        reference, _metadata(), candidate, _metadata(),
        reference_embedding=[1.0, 0.0], candidate_embedding=[1.0, 0.0],
    )
    expected = (
        location.TIME_COMPARE_VISUAL_WEIGHT * 1.0
        + location.TIME_COMPARE_DISTANCE_WEIGHT * 1.0
        + location.TIME_COMPARE_TIME_WEIGHT * 0.0
    )
    assert score == pytest.approx(expected)


def test_comparison_score_drops_when_the_candidate_is_far_away():
    time = datetime(2026, 5, 20, 10, 0)
    reference = _photo(time)
    candidate = _photo(time)
    score = location._comparison_score(
        reference, _metadata(31.2304, 121.4737), candidate, _metadata(39.9042, 116.4074),
    )
    # 距离远超 200m 半径 -> 距离分 0.0。
    assert score == pytest.approx(0.0)


def test_comparison_score_uses_the_neutral_distance_without_coordinates():
    time = datetime(2026, 5, 20, 10, 0)
    reference = _photo(time)
    candidate = _photo(time + timedelta(days=90))
    score = location._comparison_score(
        reference, _metadata(None, None), candidate, _metadata(None, None),
    )
    # 缺少坐标 -> 距离分 0.5；90 天 -> 时间分 0.5。
    assert score == pytest.approx(0.55 * 0.5 + 0.45 * 0.5)
