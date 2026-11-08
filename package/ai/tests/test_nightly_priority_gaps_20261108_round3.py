"""Nightly watch 2026-11-08 (round 3): ticket datetime / text normalisation gaps.

Targets uncovered branches of ``app/services/ticket_parser.py`` reported by the
2026-11-08 coverage snapshot (datetime pattern fallbacks and text helpers).

Every test below exercises an already-implemented behaviour; no production
code is changed.
"""

from __future__ import annotations

import pytest

from app.services.ticket_parser import (
    _extract_month_day,
    _fix_ocr_text,
    _extract_hhmm,
    _is_id_like_text,
    candidate_train_codes,
    normalize_ticket_text,
    parse_ticket_info,
)

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------- #
# Datetime formats
# --------------------------------------------------------------------------- #


def test_full_date_with_time_in_one_block():
    """A printed date and time in the same block yields a full timestamp."""
    info = parse_ticket_info(["2020年08月29日20:54开"], [])

    assert info["datetime"] == "2020年08月29日 20:54"


def test_glued_day_and_time_without_separators():
    """``20240805日1650开`` is read as 2024-08-05 16:50."""
    info = parse_ticket_info(["20240805日1650开"], [])

    assert info["datetime"] == "2024年08月05日 16:50"


def test_glued_month_day_is_zero_padded():
    """``2024年1005日16:50开`` keeps a two-digit month and day."""
    info = parse_ticket_info(["2024年1005日16:50开"], [])

    assert info["datetime"] == "2024年10月05日 16:50"


def test_compact_date_with_ticket_code_prefix():
    """A glued date is still resolved when it follows the ticket serial."""
    info = parse_ticket_info(["G20200101 202008月29日2054"], [])

    assert info["datetime"] == "2020年08月29日 20:54"


def test_date_and_time_split_across_blocks():
    """Date and time may arrive in separate OCR blocks."""
    info = parse_ticket_info(["2020年08月29日", "20:54"], [])

    assert info["datetime"] == "2020年08月29日 20:54"


def test_year_block_combined_with_month_day_time_block():
    """A lonely year block is combined with a ``月日时分`` block."""
    info = parse_ticket_info(["2020年", "08月29日10:40开"], [])

    assert info["datetime"] == "2020年08月29日 10:40"


def test_dotted_date_is_normalised():
    """``2020.08.29`` is rewritten to the Chinese date notation."""
    info = parse_ticket_info(["2020.08.29", "10:40"], [])

    assert info["datetime"] == "2020年08月29日 10:40"


def test_date_without_time_keeps_the_date_only():
    """Without a time the date alone is kept."""
    info = parse_ticket_info(["2020年08月29日"], [])

    assert info["datetime"] == "2020年08月29日"


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #


def test_month_day_and_time_extraction():
    """The small helpers return the printed month/day and hh:mm fragments."""
    assert _extract_month_day("06月02日") == ("06", "02")
    assert _extract_hhmm("10:40") == "10:40"


def test_id_like_text_is_detected():
    """Masked identity blocks are recognised as ids."""
    assert _is_id_like_text("370101199001011234") is True
    assert _is_id_like_text("北京南站") is False


def test_candidate_train_codes_prefers_modern_services():
    """Modern service codes win over the legacy fallback."""
    codes = candidate_train_codes(["G1次", "G1234次", "北京南站"])

    assert codes == {"G1", "G1234"}


def test_candidate_train_codes_falls_back_to_legacy_services():
    """Without a modern code the legacy ``N123次`` form is still recognised."""
    assert candidate_train_codes(["N123次"]) == {"N123"}


def test_normalize_ticket_text_converts_traditional_characters():
    """Traditional characters printed on a ticket are normalised."""
    assert normalize_ticket_text("車站") == "车站"


def test_fix_ocr_text_repairs_digit_confusions():
    """Letters that look like digits are repaired before matching."""
    assert _fix_ocr_text("G1O24") == "G1024"
    assert _fix_ocr_text("IlO") == "110"

