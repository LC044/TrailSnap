"""Nightly watch 2026-11-02 guards for ticket parser datetime assembly."""
import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke]


def test_parse_ticket_info_joins_year_and_month_day_time_blocks():
    result = parse_ticket_info(
        ["2025年", "06月02日10:40开"],
        [
            [[0, 0], [100, 0], [100, 10], [0, 10]],
            [[0, 20], [100, 20], [100, 30], [0, 30]],
        ],
    )

    assert result["datetime"] == "2025年06月02日 10:40"