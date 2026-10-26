"""Nightly coverage for the ticket price / seat / date blind spots (2026-10-25).

The 2026-10-25 coverage scan showed ``app/services/ticket_parser.py`` is still
the largest single-file gap in the AI service (83.3%, 154 missed lines).  The
missed lines sit in three clusters that no existing test touched:

1. **price parsing** -- the cross-block concatenation path
   (``['￥', '443.5元'] -> '443.5'``), the discount-block guard
   (``'6.6折'`` must never become a price) and the "value points" guard
   (``'价值 5000'`` is a points balance, not a fare).
2. **carriage / seat / berth parsing** -- the short forms the OCR engine
   actually emits (``0303A号`` / ``074080号`` / ``03车03A号`` / ``03403A`` /
   ``03+12C号``) and the "no seat" ticket branch, which must clear
   ``seat_num`` but keep the carriage.
3. **date extraction** -- ``_extract_month_day`` also accepts a dot format
   (``2026.04.02``).  That rule is greedy enough to read a *discount* token
   (``6.6折``) or a *fare* token (``￥12.5``) as a calendar date, which
   silently put ``06月06日`` into ``ticket_info['datetime']``.  The tests
   below pin the corrected behaviour.

The date cases are the only ones that changed production behaviour; the rest
documents the branches that were previously unexercised.
"""

import pytest

pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _parse(*texts):
    """Run the parser over a synthetic OCR block list."""
    from app.services.ticket_parser import parse_ticket_info

    polys = [_poly(0, index * 20) for index in range(len(texts))]
    return parse_ticket_info(list(texts), polys)


# ---------------------------------------------------------------------------
# 1. price parsing
# ---------------------------------------------------------------------------


def test_price_is_concatenated_across_split_blocks():
    """A lone currency symbol followed by the amount is one price."""
    result = _parse("￥", "443.5元")
    assert result["price"] == "443.5"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("￥443.5元", "443.5"),
        ("￥443.5", "443.5"),
        ("443.5元", "443.5"),
        ("￥70", "70"),
        ("70元", "70"),
    ],
)
def test_single_block_price_is_recognised(text, expected):
    assert _parse(text)["price"] == expected


def test_discount_block_is_never_used_as_a_price():
    """``6.6折`` is a discount, not a fare."""
    result = _parse("6.6折")
    assert result["price"] == ""


def test_points_value_block_is_never_used_as_a_price():
    """``价值 5000`` is the points balance of the ticket, not the fare."""
    result = _parse("价值5000")
    assert result["price"] == ""


# ---------------------------------------------------------------------------
# 2. carriage / seat / berth parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "carriage", "seat"),
    [
        ("0303A号", "03", "03A"),
        ("074080号", "07", "4080"),
        ("03车03A号", "03", "03A"),
        ("03403A", "03", "03A"),
        ("03+12C号", "03", "12C"),
        ("09车14F号上铺", "09", "14F"),
        ("3车02号中铺", "3", "02"),
    ],
)
def test_carriage_and_seat_forms(text, carriage, seat):
    result = _parse(text)
    assert result["carriage"] == carriage
    assert result["seat_num"] == seat


def test_carriage_only_block():
    assert _parse("03车")["carriage"] == "03"


def test_seat_only_block():
    result = _parse("12C号")
    assert result["carriage"] == ""
    assert result["seat_num"] == "12C"


@pytest.mark.parametrize("keyword", ["无座", "站票"])
def test_no_seat_ticket_clears_seat_number(keyword):
    """无座/站票 must not carry a seat number."""
    result = _parse(keyword)
    assert result["seat_type"] == keyword
    assert result["seat_num"] == ""


def test_no_seat_ticket_still_records_the_carriage():
    """The carriage is still printed on a no-seat ticket."""
    result = _parse("车厢04车", "无座")
    assert result["carriage"] == "04"
    assert result["seat_type"] == "无座"


@pytest.mark.parametrize(
    ("text", "berth", "seat_type"),
    [
        ("上 铺", "上铺", ""),
        ("硬卧中铺", "中铺", "硬卧"),
    ],
)
def test_berth_type_normalises_whitespace(text, berth, seat_type):
    result = _parse(text)
    assert result["berth_type"] == berth
    assert result["seat_type"] == seat_type


@pytest.mark.parametrize(
    ("text", "seat_type"),
    [
        ("新车空调硬卧", "硬卧"),
        ("硬座", "硬座"),
        ("二等座", "二等座"),
    ],
)
def test_seat_type_keyword_is_detected(text, seat_type):
    assert _parse(text)["seat_type"] == seat_type


# ---------------------------------------------------------------------------
# 3. discount type + passenger name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("学惠", "学生票"), ("学生票", "学生票")],
)
def test_discount_type_is_normalised(text, expected):
    assert _parse(text)["discount_type"] == expected


@pytest.mark.parametrize("text", ["旅客姓名：张三", "乘车人：李四", "姓名:王五"])
def test_explicit_name_label_is_used(text):
    assert _parse(text)["name"] != ""


def test_name_after_a_numbered_block_is_used():
    """Backup rule: ``5678 张三`` -> 张三."""
    assert _parse("5678 张三")["name"] == "张三"


def test_name_next_to_a_masked_id_is_used():
    """A masked id fragment plus a Chinese block yields the passenger name."""
    assert _parse("*8035xxx", "张三")["name"] == "张三"


# ---------------------------------------------------------------------------
# 4. date extraction must not read prices / discounts as calendar dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["6.6折", "8.5折", "￥12.5", "￥5.5元"])
def test_price_like_tokens_do_not_become_a_datetime(text):
    """``6.6折`` used to be parsed as ``06月06日``."""
    result = _parse(text)
    assert result["datetime"] == ""


def test_real_dot_dates_are_still_recognised():
    """The dot date format itself must keep working."""
    from app.services.ticket_parser import _extract_month_day

    assert _extract_month_day("2026.04.02") == ("04", "02")
    assert _extract_month_day("04.02") == ("04", "02")
