"""覆盖 app/service/moment/day_highlight_service.py 中此前没有测试引用的四个纯函数。

盲区来源：函数级静态引用扫描命中 _day_bounds_naive / _segment_by_time /
_cluster_segment / _pick_group_representative。

它们是「每日精选」的纯计算内核：
- _day_bounds_naive 决定当天的 [start, end) 时间窗，跨月跨闰年必须正确；
- _segment_by_time 按 5 分钟间隔切段，并对超长段做 200 张的硬切；
- _cluster_segment 在段内做余弦相似度聚类；
- _pick_group_representative 按 score 选代表，score 相同取更晚的照片。

既有测试只走 get_day_highlights 的整体流程，从未直接断言这些边界行为。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.service.moment import day_highlight_service as service

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _candidate(identifier, minute, score=1.0, embedding=(1.0, 0.0)):
    return {
        "id": identifier,
        "photo_time": datetime(2026, 5, 20, 10, 0) + timedelta(minutes=minute),
        "embedding": list(embedding),
        "score": score,
    }


def test_day_bounds_are_a_half_open_interval():
    start, end = service._day_bounds_naive(date(2026, 5, 20))
    assert start == datetime(2026, 5, 20, 0, 0, 0)
    assert end == datetime(2026, 5, 21, 0, 0, 0)


def test_day_bounds_handle_leap_days_and_year_ends():
    start, end = service._day_bounds_naive(date(2024, 2, 28))
    assert end == datetime(2024, 2, 29, 0, 0, 0)
    start, end = service._day_bounds_naive(date(2026, 12, 31))
    assert end == datetime(2027, 1, 1, 0, 0, 0)


def test_segment_by_time_returns_nothing_for_an_empty_day():
    assert service._segment_by_time([]) == []


def test_segment_by_time_keeps_photos_inside_the_gap_together():
    candidates = [_candidate("a", 0), _candidate("b", 1), _candidate("c", 2)]
    segments = service._segment_by_time(candidates)
    assert len(segments) == 1
    assert [item["id"] for item in segments[0]] == ["a", "b", "c"]


def test_segment_by_time_splits_once_the_gap_is_exceeded():
    candidates = [_candidate("a", 0), _candidate("b", service._GAP_SECONDS // 60 + 1)]
    segments = service._segment_by_time(candidates)
    assert [[item["id"] for item in segment] for segment in segments] == [["a"], ["b"]]


def test_segment_by_time_hard_splits_oversized_segments():
    candidates = [_candidate(f"p{index}", 0) for index in range(service._MAX_SEGMENT_SIZE + 50)]
    segments = service._segment_by_time(candidates)
    assert [len(segment) for segment in segments] == [service._MAX_SEGMENT_SIZE, 50]


def test_cluster_segment_keeps_a_single_photo_alone():
    only = _candidate("a", 0)
    assert service._cluster_segment([only]) == [[only]]


def test_cluster_segment_groups_similar_and_separates_different_photos():
    pytest.importorskip("sklearn")
    identical = [_candidate("a", 0, embedding=(1.0, 0.0)), _candidate("b", 0, embedding=(1.0, 0.0))]
    groups = service._cluster_segment(identical)
    assert len(groups) == 1
    assert {item["id"] for item in groups[0]} == {"a", "b"}

    different = [_candidate("a", 0, embedding=(1.0, 0.0)), _candidate("b", 0, embedding=(0.0, 1.0))]
    groups = service._cluster_segment(different)
    assert len(groups) == 2


def test_group_representative_requires_a_non_empty_group():
    with pytest.raises(ValueError):
        service._pick_group_representative([])


def test_group_representative_prefers_the_highest_score():
    low = _candidate("low", 0, score=0.4)
    high = _candidate("high", 0, score=0.9)
    representative, size = service._pick_group_representative([low, high])
    assert representative["id"] == "high"
    assert size == 2


def test_group_representative_breaks_a_score_tie_with_the_later_photo():
    earlier = _candidate("earlier", 0, score=0.7)
    later = _candidate("later", 5, score=0.7)
    representative, size = service._pick_group_representative([earlier, later])
    assert representative["id"] == "later"
    assert size == 2
