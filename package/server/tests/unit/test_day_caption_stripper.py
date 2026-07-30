"""Unit tests for the pure helpers in ``app/service/moment/day_caption_service.py``.

The module under test is the moment day caption generator, which depends on
SQLAlchemy / LangChain / the user config manager at import time. The
``_ThinkStripper`` state machine, the ``_strip_think_blocks`` regex helper,
``day_bounds_utc`` and ``_format_materials_for_prompt`` are all pure
functions, so we exercise them in isolation. The conftest loads
``tests/.env.test`` before any test imports the service module, which is
required for the import chain
``app.service.moment.day_caption_service -> app.service.agent.service ->
app.db.session`` to succeed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_moment]


# ---------------------------------------------------------------------------
# _ThinkStripper 跨 chunk 状态机
# ---------------------------------------------------------------------------

def _make_stripper():
    from app.service.moment.day_caption_service import _ThinkStripper
    return _ThinkStripper()


def test_stripper_passes_through_plain_text():
    s = _make_stripper()
    assert s.feed("hello world") == "hello world"
    assert s.feed(" 继续") == " 继续"
    assert s.flush() == ""


def test_stripper_drops_complete_think_block_in_one_chunk():
    s = _make_stripper()
    out = s.feed("<think>reasoning</think>visible")
    assert out == "visible"
    assert s.flush() == ""


def test_stripper_handles_think_block_split_across_chunks():
    s = _make_stripper()
    assert s.feed("<think>rea") == ""
    assert s.feed("soning abou") == ""
    assert s.feed("t the trip</think>caption body") == "caption body"
    assert s.flush() == ""


def test_stripper_drops_unterminated_think_block_on_flush():
    """If a stream ends inside <think> ... </think>, the partial block is discarded."""
    s = _make_stripper()
    assert s.feed("<think>never closed") == ""
    assert s.flush() == ""


def test_stripper_flushes_partial_normal_buffer():
    """Buffer shorter than <think> that was waiting for more characters."""
    s = _make_stripper()
    # Only "<" was buffered, then stream ended before "<think>" was completed.
    assert s.feed("text <") == "text "
    assert s.flush() == "<"


def test_stripper_rejects_partial_open_with_different_suffix():
    """Buffer that started with '<' but did not become <think> is emitted as plain text."""
    s = _make_stripper()
    # '<' + 'd' should be flushed immediately (does not start with <think>)
    assert s.feed("a<d") == "a<d"
    assert s.flush() == ""


def test_stripper_is_case_insensitive_on_think_tags():
    s = _make_stripper()
    out = s.feed("<THINK>reasoning</THINK>visible")
    assert out == "visible"


def test_stripper_strips_remaining_buffer_after_think_close():
    s = _make_stripper()
    s.feed("<think>drop this</think>")
    # No pending buffer, flush is empty.
    assert s.flush() == ""


# ---------------------------------------------------------------------------
# _strip_think_blocks 落库前兜底正则
# ---------------------------------------------------------------------------

def test_strip_think_blocks_keeps_text_without_blocks():
    from app.service.moment.day_caption_service import _strip_think_blocks
    assert _strip_think_blocks("plain text") == "plain text"
    assert _strip_think_blocks("") == ""


def test_strip_think_blocks_removes_all_blocks_in_text():
    from app.service.moment.day_caption_service import _strip_think_blocks
    text = "a<think>reason 1</think>b<think>reason 2</think>c"
    assert _strip_think_blocks(text) == "abc"


def test_strip_think_blocks_handles_multiline_think():
    from app.service.moment.day_caption_service import _strip_think_blocks
    text = "before<think>line1\nline2\nline3</think>after"
    assert _strip_think_blocks(text) == "beforeafter"


# ---------------------------------------------------------------------------
# day_bounds_utc
# ---------------------------------------------------------------------------

def test_day_bounds_utc_returns_naive_start_and_exclusive_next_day():
    from app.service.moment.day_caption_service import day_bounds_utc
    start, end = day_bounds_utc(date(2026, 7, 30), "Asia/Shanghai")
    assert start == datetime(2026, 7, 30, 0, 0, 0)
    assert end == datetime(2026, 7, 31, 0, 0, 0)
    assert end - start == timedelta(days=1)


def test_day_bounds_utc_is_tz_independent_in_docstring_semantics():
    """``tz_name`` is kept for signature compatibility; bounds stay naive either way."""
    from app.service.moment.day_caption_service import day_bounds_utc
    s1, e1 = day_bounds_utc(date(2026, 1, 1), "UTC")
    s2, e2 = day_bounds_utc(date(2026, 1, 1), "America/New_York")
    assert (s1, e1) == (s2, e2)


def test_day_bounds_utc_spans_year_boundary():
    from app.service.moment.day_caption_service import day_bounds_utc
    start, end = day_bounds_utc(date(2026, 12, 31), "")
    assert start == datetime(2026, 12, 31)
    assert end == datetime(2027, 1, 1)


# ---------------------------------------------------------------------------
# _format_materials_for_prompt
# ---------------------------------------------------------------------------

def test_format_materials_omits_optional_sections_when_empty():
    from app.service.moment.day_caption_service import _format_materials_for_prompt
    out = _format_materials_for_prompt(date(2026, 7, 30), {
        "locations": [],
        "people": [],
        "descriptions": [],
        "tags": [],
        "counts": {"image": 0, "video": 0},
    }, style=None)
    assert "日期（仅供你理解" in out
    assert "期望风格" not in out
    assert "主要地点" not in out
    assert "一起出现的人物" not in out
    assert "常见标签" not in out
    # When descriptions is empty we must surface the placeholder, not silently drop the section.
    assert "尚未生成视觉描述" in out


def test_format_materials_renders_all_sections_when_present():
    from app.service.moment.day_caption_service import _format_materials_for_prompt
    out = _format_materials_for_prompt(
        date(2026, 7, 30),
        {
            "locations": ["武汉 · 黄鹤楼"],
            "people": ["小明", "小红"],
            "descriptions": ["登黄鹤楼远眺长江", "夜晚灯光秀"],
            "tags": ["city", "night"],
            "counts": {"image": 3, "video": 1},
        },
        style="抒情",
    )
    assert "期望风格：抒情" in out
    assert "照片数量：3 张图 / 1 个视频" in out
    assert "一起出现的人物：小明、小红" in out
    assert "主要地点：武汉 · 黄鹤楼" in out
    assert "常见标签：city、night" in out
    assert "1) 登黄鹤楼远眺长江" in out
    assert "2) 夜晚灯光秀" in out
