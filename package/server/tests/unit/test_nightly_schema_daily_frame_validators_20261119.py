"""2026-11-19 nightly coverage for ``app/schemas/daily_frame.py``.

The frame validators (``one_line``, ``nonempty_title``, ``valid_color``) were
never referenced by any test file.  They are the last guard before user input
reaches the daily-frame renderer, so their normalisation and rejection rules
are asserted here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.daily_frame import BatchFill, FilmSettings, FrameSelection


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


PHOTO_ID = "11111111-2222-3333-4444-555555555555"


def test_caption_whitespace_is_collapsed_into_a_single_line():
    selection = FrameSelection(photo_id=PHOTO_ID, caption="  一日   一帧\n第二行  ")

    assert selection.caption == "一日 一帧 第二行"
    assert "\n" not in selection.caption


def test_an_empty_caption_stays_empty():
    assert FrameSelection(photo_id=PHOTO_ID, caption="   ").caption == ""


def test_a_caption_longer_than_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        FrameSelection(photo_id=PHOTO_ID, caption="字" * 31)


def test_a_blank_film_title_is_rejected():
    with pytest.raises(ValidationError, match="请填写影片标题"):
        FilmSettings(start_date="2026-01-01", end_date="2026-01-02", title="   ")


def test_a_film_title_is_trimmed():
    settings = FilmSettings(start_date="2026-01-01", end_date="2026-01-02", title="  一日一帧  ")

    assert settings.title == "一日一帧"


def test_a_non_hex_background_is_rejected():
    with pytest.raises(ValidationError, match="背景必须是六位十六进制颜色"):
        FilmSettings(start_date="2026-01-01", end_date="2026-01-02", background="#12345")


def test_a_background_without_a_hash_is_rejected():
    with pytest.raises(ValidationError):
        FilmSettings(start_date="2026-01-01", end_date="2026-01-02", background="111827")


def test_a_valid_background_is_lowercased():
    settings = FilmSettings(start_date="2026-01-01", end_date="2026-01-02", background="#A1B2C3")

    assert settings.background == "#a1b2c3"


def test_unknown_fields_are_forbidden():
    with pytest.raises(ValidationError):
        FilmSettings(start_date="2026-01-01", end_date="2026-01-02", surprise="boom")


def test_a_batch_fill_needs_at_least_one_item():
    with pytest.raises(ValidationError):
        BatchFill(items=[])


def test_a_negative_start_offset_is_rejected():
    with pytest.raises(ValidationError):
        FrameSelection(photo_id=PHOTO_ID, start_seconds=-1)
