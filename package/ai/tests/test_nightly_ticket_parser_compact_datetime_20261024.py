"""Nightly regression tests for compact (digit-glued) ticket datetime blocks (2026-10-24).

The 2026-10-23 nightly round flagged a real defect in
``app/services/ticket_parser.py``: OCR frequently returns the whole
departure datetime as one glued digit block, e.g. ``202405月07日1022开``.
The generic extractors only see the pieces they know:

* ``_extract_month_day`` matched ``05月07日`` but dropped the glued year,
* ``_extract_hhmm`` requires a colon, so ``1022`` was not recognised as a time.

The result was the degraded ``05月07日`` instead of
``2024年05月07日 10:22``. Because the per-block scan runs *before* the
full-format fallback table, the degraded value also shadowed the richer
``(\d{4})(\d{2})月(\d{1,2})日(\d{4})`` pattern that could have handled it.

The fix recovers the glued year and glued time in
``_build_departure_datetime``. These tests pin the behaviour down.
"""

import pytest

pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _parse_datetime(text: str) -> str:
    from app.services.ticket_parser import parse_ticket_info

    return parse_ticket_info([text], [_poly(0, 0)])["datetime"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 年份粘在月份前 + 时分粘在日字后（无冒号）
        ("202405月07日1022开", "2024年05月07日 10:22"),
        ("2024年05月07日1022开", "2024年05月07日 10:22"),
        # 年份粘在月份前 + 常规冒号时间
        ("202405月07日10:22开", "2024年05月07日 10:22"),
        # 年月日全部粘连（无「月」字）
        ("20240507日1022", "2024年05月07日 10:22"),
    ],
)
def test_compact_block_restores_full_datetime(text, expected):
    """粘连数字块必须还原完整的年月日 + 时分。"""
    assert _parse_datetime(text) == expected


def test_compact_block_restores_year_when_time_is_separate():
    """年份粘在月份前时，年份不应因为“无分隔符”而丢失。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["202405月07日", "10:22"], [_poly(0, 0), _poly(0, 50)])

    assert info["datetime"] == "2024年05月07日 10:22"


def test_plain_month_day_block_keeps_year_omitted():
    """没有年份时不猜年，不能因为新增的粘连规则而伪造。"""
    assert _parse_datetime("05月07日") == "05月07日"


def test_compact_block_without_time_keeps_date_only():
    """只有日期的粘连块不应编造时分。"""
    assert _parse_datetime("202405月07日") == "2024年05月07日"


def test_compact_block_does_not_consume_unrelated_trailing_digits():
    """日期后面的无关数字不应被当成时分。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["202405月07日", "88888"], [_poly(0, 0), _poly(0, 50)])

    assert info["datetime"] == "2024年05月07日"


def test_compact_block_with_hhmm_colon_and_plain_block_agree():
    """同一业务上有冒号与无冒号两种写法应进出同一结果。"""
    assert _parse_datetime("202405月07日10:22开") == _parse_datetime("202405月07日1022开")
