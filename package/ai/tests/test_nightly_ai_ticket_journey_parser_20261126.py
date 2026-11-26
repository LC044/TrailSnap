"""Nightly watch 2026-11-26 · app/services/ticket_journey_parser.py 的日期回填盲区。

行程时间只能来自车票卡本身，不能用手机时钟推算。这个模块里有两类「把日期
回填到只有时刻的车票」的规则，此前几乎没有独立断言：

- ``apply_shared_ticket_date``：整页只有一个明确日期时，给所有同车次的
  只有时刻的车票补上日期；
- ``apply_section_ticket_dates``：同一屏里「乘车日期」标题 + 唯一一处时刻
  文本时，把标题日期补到该时刻上。

本文件覆盖它们的**放弃条件**（多个日期、车次对不上、已经带完整日期、
时刻锚点不唯一），因为这些分支决定了「宁可不给日期，也不要给错日期」。
"""

from __future__ import annotations

import pytest

from app.services.ticket_journey_parser import (
    apply_section_ticket_dates,
    apply_shared_ticket_date,
    extract_journey_time,
)

pytestmark = pytest.mark.smoke


def card(*blocks):
    texts, polys = [], []
    for text, x, y in blocks:
        texts.append(text)
        polys.append([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])
    return texts, polys


# --- 共享页眉日期 ----------------------------------------------------


def test_shared_header_date_is_applied_to_a_clock_only_ticket():
    texts = ["2024年5月1日 G123", "G123"]
    ticket = {"train_code": "G123", "datetime": "08:30"}

    apply_shared_ticket_date(texts, [ticket])

    assert ticket["datetime"] == "2024年5月1日 08:30"
    assert ticket["date_source"] == "shared-ticket-header"


def test_shared_header_date_is_skipped_when_the_page_has_two_dates():
    texts = ["2024年5月1日 G123", "2024年5月2日 G123"]
    ticket = {"train_code": "G123", "datetime": "08:30"}

    apply_shared_ticket_date(texts, [ticket])

    assert ticket["datetime"] == "08:30"
    assert "date_source" not in ticket


def test_shared_header_date_is_skipped_when_the_train_code_is_not_on_the_page():
    texts = ["2024年5月1日 G123", "G123"]
    ticket = {"train_code": "K999", "datetime": "08:30"}

    apply_shared_ticket_date(texts, [ticket])

    assert ticket["datetime"] == "08:30"


def test_shared_header_date_is_skipped_when_the_ticket_has_no_train_code():
    texts = ["2024年5月1日 G123"]
    ticket = {"datetime": "08:30"}

    apply_shared_ticket_date(texts, [ticket])

    assert ticket["datetime"] == "08:30"


def test_shared_header_date_never_overwrites_a_full_datetime():
    texts = ["2024年5月1日 G123"]
    ticket = {"train_code": "G123", "datetime": "2024年5月1日 08:30"}

    apply_shared_ticket_date(texts, [ticket])

    assert ticket["datetime"] == "2024年5月1日 08:30"
    assert "date_source" not in ticket


# --- 分区标题日期 ----------------------------------------------------


def test_section_header_date_is_applied_to_the_only_clock_row():
    texts, polys = card(("乘车日期：2024年5月1日", 20, 60), ("08:30", 20, 140))
    ticket = {"datetime": "08:30"}

    apply_section_ticket_dates(texts, polys, [ticket])

    assert ticket["datetime"] == "2024年5月1日 08:30"
    assert ticket["date_source"] == "ticket-section-header"


def test_section_header_date_is_skipped_when_the_clock_is_ambiguous():
    texts, polys = card(("乘车日期：2024年5月1日", 20, 60), ("08:30", 20, 140), ("08:30", 260, 140))
    ticket = {"datetime": "08:30"}

    apply_section_ticket_dates(texts, polys, [ticket])

    assert ticket["datetime"] == "08:30"
    assert "date_source" not in ticket


def test_section_header_date_is_skipped_without_a_section_header():
    texts, polys = card(("08:30", 20, 140))
    ticket = {"datetime": "08:30"}

    apply_section_ticket_dates(texts, polys, [ticket])

    assert ticket["datetime"] == "08:30"


# --- 行程时长 --------------------------------------------------------


def test_minute_only_duration_is_used_as_the_ticket_duration():
    texts, polys = card(("G123", 180, 100), ("全程45分", 180, 60))

    assert extract_journey_time(texts, polys, {"train_code": "G123"}) == {
        "duration_minutes": 45, "duration_source": "ticket-duration"}


def test_an_implausible_duration_is_ignored():
    texts, polys = card(("G123", 180, 100), ("历时200小时", 180, 60))

    assert extract_journey_time(texts, polys, {"train_code": "G123"}) == {}


def test_a_duration_with_invalid_minutes_is_ignored():
    texts, polys = card(("G123", 180, 100), ("历时2小时75分", 180, 60))

    assert extract_journey_time(texts, polys, {"train_code": "G123"}) == {}
