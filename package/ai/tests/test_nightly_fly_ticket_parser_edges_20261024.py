"""Nightly coverage for fly_ticket_parser edge branches (2026-10-24).

补齐此前没有断言的分支：缺年份时推断当前年份、纯数字价格回退、
「已省/省钱」干扰行、OCR 分行城市、机场名兜底城市、脱敏姓名（朱*燕）。
"""

from datetime import datetime

import pytest

from app.services.fly_ticket_parser import FlightTicketParser


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def parser():
    return FlightTicketParser()


def test_date_without_year_infers_current_year(parser):
    result = parser.parse(["9月27日 13:25", "CA1234"])

    assert result["datetime"] == f"{datetime.now().year}-09-27 13:25"
    assert result.get("year_source") == "inferred_current_year"


def test_bare_number_price_is_used_when_no_price_label(parser):
    result = parser.parse(["MU5102", "1200"])

    assert result["price"] == "1200"


def test_discount_noise_line_is_not_treated_as_price(parser):
    result = parser.parse(["CA1234", "已省 ¥1200"])

    assert result["price"] is None


def test_price_out_of_plausible_range_is_ignored(parser):
    result = parser.parse(["CA1234", "88"])

    assert result["price"] is None


def test_adjacent_lines_are_joined_into_departure_and_arrival(parser):
    result = parser.parse(["MU5102", "上海", "北京"])

    assert result["departure_city"] == "上海"
    assert result["arrival_city"] == "北京"


def test_airport_names_are_used_as_cities_fallback(parser):
    result = parser.parse(["北京首都机场", "上海虹桥机场"])

    assert result["departure_city"] == "北京首都"
    assert result["arrival_city"] == "上海虹桥"


def test_masked_passenger_name_is_extracted(parser):
    result = parser.parse(["朱*燕 成人", "CA1234"])

    assert result["name"] == "朱*燕"


def test_passenger_name_on_the_following_line_is_extracted(parser):
    result = parser.parse(["乘机人", "张三"])

    assert result["name"] == "张三"


def test_noise_lines_with_deadline_keywords_are_skipped(parser):
    # 「最晚 23:59 前完成支付」不是航班时间，应当被跳过。
    result = parser.parse(["最晚 23:59 前完成支付", "CA1234"])

    assert result["datetime"] is None
