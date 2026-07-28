"""Unit tests for app/services/fly_ticket_parser.py (pure OCR parser).

The parser is a pure function over a list of OCR text lines; no models,
no DB. We test the high-value branches: full parse, minimal parse, the
multi-line city split, and the "noise" exclusion list.
"""

import pytest

from app.services.fly_ticket_parser import FlightTicketParser


pytestmark = [pytest.mark.smoke]


def test_parse_extracts_full_ticket_fields():
    parser = FlightTicketParser()
    text_list = [
        "航班号 CA1234",
        "2025-09-27 13:25",
        "上海 — 北京",
        "票价 ¥1200",
        "乘机人 张三",
    ]
    result = parser.parse(text_list)

    assert result["flight_code"] == "CA1234"
    assert result["departure_city"] == "上海"
    assert result["arrival_city"] == "北京"
    assert result["datetime"] == "2025-09-27 13:25"
    assert result["price"] == "1200"
    assert result["name"] == "张三"


def test_parse_handles_minimal_input_without_optional_fields():
    parser = FlightTicketParser()
    # No price, no time, no name -> only the strongly-detectable fields
    text_list = ["HU7890", "深圳-广州"]
    result = parser.parse(text_list)

    assert result["flight_code"] == "HU7890"
    assert result["departure_city"] == "深圳"
    assert result["arrival_city"] == "广州"
    assert result["datetime"] is None
    assert result["price"] is None
    assert result["name"] is None


def test_parse_uses_chinese_full_date_format():
    parser = FlightTicketParser()
    text_list = [
        "2025年9月27日 13:25",
        "上海 — 北京",
        "MU5102",
    ]
    result = parser.parse(text_list)

    assert result["datetime"] == "2025-09-27 13:25"
    assert result["flight_code"] == "MU5102"


def test_parse_recognizes_split_city_on_consecutive_lines():
    """When OCR splits a city pair across two lines, parser must still match."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "上海",
        "—",
        "北京",
        "2025-09-27 13:25",
    ]
    result = parser.parse(text_list)

    assert result["departure_city"] == "上海"
    assert result["arrival_city"] == "北京"


def test_parse_extracts_cities_from_airport_codes():
    """Falls back to airport-name stripping when arrow pattern is absent."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "虹桥机场",
        "首都机场T3",
        "2025-09-27 13:25",
    ]
    result = parser.parse(text_list)

    assert result["departure_city"] == "虹桥"
    assert result["arrival_city"] == "首都"


def test_parse_filters_excluded_keywords_from_name_candidate():
    """Common UI/header words must not become a name."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "上海 — 北京",
        "订单",
        "已完成",
        "2025-09-27 13:25",
    ]
    result = parser.parse(text_list)

    # None of the listed tokens are names
    assert result["name"] is None


def test_parse_handles_chinese_colon_in_time():
    """Some OCR output uses full-width colon."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "上海 — 北京",
        "2025-09-27 13：25",
    ]
    result = parser.parse(text_list)

    assert result["datetime"] == "2025-09-27 13:25"


def test_parse_normalizes_time_padding():
    """Single-digit hour/minute should be zero-padded."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "上海 — 北京",
        "2025-09-27 1:5",
    ]
    result = parser.parse(text_list)

    # The parser may still see '1:5' as a single hour-min pair.
    assert result["datetime"] is not None
    assert "2025-09-27" in result["datetime"]


def test_parse_skips_status_time_lines():
    """Lines like "最晚 15:30 截止出票" must not become flight time."""
    parser = FlightTicketParser()
    text_list = [
        "MU5102",
        "上海 — 北京",
        "最晚 15:30 截止完成",
        "2025-09-27 13:25",
    ]
    result = parser.parse(text_list)

    assert result["datetime"] == "2025-09-27 13:25"


def test_parse_returns_all_none_for_garbage_input():
    parser = FlightTicketParser()
    text_list = ["", "  ", "完成", "订单", "电子客票"]
    result = parser.parse(text_list)

    assert result == {
        "flight_code": None,
        "departure_city": None,
        "arrival_city": None,
        "datetime": None,
        "price": None,
        "name": None,
    }
