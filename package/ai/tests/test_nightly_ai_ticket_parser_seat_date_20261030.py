"""2026-10-30 nightly coverage for ``app/services/ticket_parser.py``.

The 2026-10-30 AI coverage scan reported ``services/ticket_parser.py`` at 92%
with 86 uncovered lines.  Most of the remaining lines are the *seat / carriage
repair* rules and the cross-block *date + time* assembly:

* the glued carriage/seat split (``0206F`` -> ``02`` / ``06F``);
* the short glued seat (``03403A号``), the combined ``03车03A号`` and the
  lone ``03车`` / ``12C号`` blocks;
* the ``站票`` / ``无座`` seat-type fallback;
* the date assembly when the date and the time live in *different* OCR
  blocks, and the dotted ``YYYY.MM.DD`` date form;
* the OCR-noise variants of the carriage/seat numbers (``03+12C号``).

Every case feeds a synthetic OCR block list into ``parse_ticket_info``; no
model, no network and no image is involved.
"""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _parse(*texts):
    from app.services.ticket_parser import parse_ticket_info

    polys = [_poly(0, index * 50) for index in range(len(texts))]
    return parse_ticket_info(list(texts), polys)


# ---------------------------------------------------------------------------
# carriage / seat repair
# ---------------------------------------------------------------------------


def test_glued_seat_number_is_split_into_carriage_and_seat():
    """``二等座0206F号`` 是粘连的车厢+座位号。"""
    result = _parse("G1", "北京", "上海", "二等座0206F号")
    assert result["carriage"] == "02"
    assert result["seat_num"] == "06F"


def test_glued_seat_number_after_the_seat_type_is_split():
    result = _parse("G1", "二等座0206F号")
    assert result["carriage"] == "02"
    assert result["seat_num"] == "06F"
    assert result["seat_type"] == "二等座"


def test_short_glued_seat_number_is_split():
    """``03403A`` 的第 3 位是 OCR 误识别的“车”，应跳过该位。"""
    result = _parse("G1", "03403A")
    assert result["carriage"] == "03"
    assert result["seat_num"] == "03A"


def test_carriage_and_seat_written_together_are_split():
    result = _parse("G1", "03车03A号")
    assert result["carriage"] == "03"
    assert result["seat_num"] == "03A"


def test_lone_carriage_block_is_recognised():
    result = _parse("G1", "03车")
    assert result["carriage"] == "03"
    assert not result["seat_num"]


def test_lone_seat_block_is_recognised():
    result = _parse("G1", "12C号")
    assert result["seat_num"] == "12C"
    assert not result["carriage"]


def test_ocr_noise_between_carriage_and_seat_is_tolerated():
    """OCR 把分隔符认成符号时也要能拆出车厢号与座位号。"""
    result = _parse("G1", "03+12C号")
    assert result["carriage"] == "03"
    assert result["seat_num"] == "12C"


def test_six_character_ocr_seat_is_split_by_skipping_the_broken_char():
    """``03403A`` 的第 3 位是 OCR 误识别的“车”。"""
    result = _parse("G1", "03403A")
    assert result["carriage"] == "03"
    assert result["seat_num"] == "03A"


def test_standing_ticket_keeps_the_seat_type_and_leaves_the_seat_empty():
    result = _parse("G1", "站票")
    assert result["seat_type"] == "站票"
    assert not result["seat_num"]


def test_no_seat_ticket_keeps_the_seat_type_and_leaves_the_seat_empty():
    result = _parse("G1", "无座")
    assert result["seat_type"] == "无座"
    assert not result["seat_num"]


def test_no_seat_ticket_still_reads_the_carriage():
    result = _parse("G1", "无座", "车厢04车")
    assert result["carriage"] == "04"
    assert result["seat_type"] == "无座"


# ---------------------------------------------------------------------------
# datetime assembly across OCR blocks
# ---------------------------------------------------------------------------


def test_date_and_time_in_two_blocks_are_joined():
    """日期块与时间块分属不同 OCR 文本时也要拼成完整发车时间。"""
    result = _parse("G1", "2025年06月02日", "10:40")
    assert result["datetime"] == "2025年06月02日 10:40"


def test_dotted_date_and_time_in_two_blocks_are_joined():
    result = _parse("G1", "2025.06.02", "10:40")
    assert result["datetime"] == "2025年06月02日 10:40"


def test_year_block_and_month_day_time_block_are_joined():
    """只有年份块 + 月日时分块时也要拼出完整发车时间。"""
    result = _parse("G1", "2025年", "06月02日10:40开")
    assert result["datetime"] == "2025年06月02日 10:40"


def test_date_and_time_in_the_same_block_are_joined():
    result = _parse("G1", "2025年06月02日10:40")
    assert result["datetime"] == "2025年06月02日 10:40"


# ---------------------------------------------------------------------------
# price fragments
# ---------------------------------------------------------------------------


def test_price_fragment_with_a_currency_mark_is_accepted():
    result = _parse("G1", "￥443.5")
    assert result["price"] == "443.5"


