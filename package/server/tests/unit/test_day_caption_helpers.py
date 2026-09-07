from datetime import date, datetime, timezone

import pytest

from app.service.moment.day_caption_service import (
    _ThinkStripper,
    _resolve_tz,
    _strip_think_blocks,
    day_bounds_utc,
)

pytestmark = [pytest.mark.smoke]


def test_strip_think_blocks_removes_complete_blocks_only():
    text = "前文<think>内部\n思考</think>后文<think>未闭合"

    assert _strip_think_blocks(text) == "前文后文<think>未闭合"


def test_resolve_tz_prefers_named_zone_and_falls_back_to_utc():
    assert _resolve_tz("") is timezone.utc
    assert _resolve_tz("not/a/zone") is timezone.utc
    assert str(_resolve_tz("Asia/Shanghai")) == "Asia/Shanghai"


def test_day_bounds_utc_returns_naive_wall_clock_range():
    start, end = day_bounds_utc(date(2026, 9, 7), "Asia/Shanghai")

    assert start == datetime(2026, 9, 7, 0, 0, 0)
    assert end == datetime(2026, 9, 8, 0, 0, 0)
    assert start.tzinfo is None
    assert end.tzinfo is None


def test_think_stripper_handles_chunked_open_and_close_tags():
    stripper = _ThinkStripper()

    assert stripper.feed("可见<th") == "可见"
    assert stripper.feed("ink>隐藏</think>") == ""
    assert stripper.feed("正文") == "正文"
    assert stripper.flush() == ""