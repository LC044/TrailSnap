"""Nightly gap coverage for app/services/ticket_parser.py date/time branches.

The nightly coverage scan flagged the fallback ``time_patterns`` loop and the
glued-date fallback as uncovered.  Those branches are what rescue real tickets
whose date and time are printed in unusual layouts (compact ``202401月05``,
``2024年1005日16:50``, separated ``2025年01月18H13:46`` …).

Each case pins the resulting ``datetime`` string so a regression in the
fallback ordering is caught instead of silently producing a wrong date.
"""

from __future__ import annotations

import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _datetime(text: str) -> str:
    info = parse_ticket_info([text], [])
    return info.get("datetime")


def test_compact_year_month_pattern():
    """紧凑的 202401月05 + 3 位小时 + 分钟。"""
    assert _datetime("202401月05123:45开") == "2024年01月05日 23:45"


def test_year_month_day_without_separators():
    """2024年1005日16:50：月日粘连。"""
    assert _datetime("2024年1005日16:50开") == "2024年10月05日 16:50"


def test_separated_day_and_time():
    """2025年01月18H13:46：日期与时间之间有额外分隔符。"""
    assert _datetime("2025年01月18H13:46") == "2025年01月18日 13:46"


def test_compact_four_digit_time_after_day():
    """202404月07日1022开：时间只有 4 位数字。"""
    assert _datetime("202404月07日1022开") == "2024年04月07日 10:22"


def test_glued_day_with_four_digit_time():
    """日期与 4 位时间粘连。"""
    assert _datetime("2024年02月2608:30") == "2024年02月26日 08:30"


def test_glued_day_with_six_digit_time():
    """日期与 6 位时间粘连（时分秒）。"""
    assert _datetime("2024年02月260080:30") == "2024年02月26日 00:30"


def test_glued_day_with_five_digit_time():
    """日期与 5 位时间粘连：走 else 兜底分支。"""
    assert _datetime("2024年02月26008:30") == "2024年02月26日 08:30"


def test_single_digit_month_day_keeps_padding():
    """2025年1月8日 9:05：月/日/小时按需补零。"""
    assert _datetime("2025年1月8日 9:05") == "2025年1月8日 09:05"


def test_invalid_sticky_time_is_rejected():
    """越界的粘连日期不会产出非法 datetime。"""
    result = _datetime("2024年02月9999:99")
    assert result is None or "日" not in str(result)
