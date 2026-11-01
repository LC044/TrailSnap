"""Nightly watch 2026-11-02 guards for compact ticket datetime recovery."""
import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("广告2024年1005日16:50开", "2024年10月05日 16:50"),
        ("广告202404月7日1022开", "2024年04月07日 10:22"),
        ("广告2025年01月18H13:46", "2025年01月18日 13:46"),
    ],
)
def test_parse_ticket_info_recovers_compact_datetime_variants(text, expected):
    # The leading “广告” makes the primary geometry-based datetime builder skip
    # the block, forcing the compact regex fallbacks to repair the OCR text.
    result = parse_ticket_info([text], [[[0, 0], [100, 0], [100, 10], [0, 10]]])

    assert result["datetime"] == expected
