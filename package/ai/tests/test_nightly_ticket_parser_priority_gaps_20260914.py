"""2026-09-14 nightly tests for AI ticket parser priority gaps."""

import pytest

from app.services.ticket_parser import parse_ticket_info


pytestmark = [pytest.mark.smoke]


def _poly(x, y):
    return [[x, y], [x + 20, y], [x + 20, y + 12], [x, y + 12]]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("202405月07110:20开", "2024年05月07日 10:20"),
        ("20240507日1020", "2024年05月07日 10:20"),
        ("202404月07日1022开", "2024年04月07日 10:22"),
    ],
)
def test_parse_ticket_info_supports_compact_datetime_variants(text, expected):
    """The fallback parser normalizes three OCR forms missed by block pairing."""

    result = parse_ticket_info([text], [])

    assert result["datetime"] == expected


def test_parse_ticket_info_extracts_full_train_ticket_fields():
    texts = [
        "G1234",
        "北京南站",
        "上海虹桥站",
        "20240507日1020",
        "05车06F号",
        "二等座",
        "（88.5元）",
        "学生票",
        "****8035张三",
    ]

    polys = [
        _poly(0, 0),
        _poly(100, 0),
        _poly(200, 0),
        _poly(0, 100),
        _poly(0, 140),
        _poly(0, 180),
        _poly(0, 220),
        _poly(0, 260),
        _poly(0, 300),
    ]
    result = parse_ticket_info(texts, polys)

    assert result["train_code"] == "G1234"
    assert result["departure_station"] == "北京南"
    assert result["arrival_station"] == "上海虹桥"
    assert result["datetime"] == "2024年05月07日 10:20"
    assert result["seat_num"] == "06F"
    assert result["price"] == "88.5"
    assert result["seat_type"] == "二等座"
    assert result["discount_type"] == "学生票"
    assert result["name"] == "张三"


def test_parse_ticket_info_normalizes_common_ocr_digit_substitutions():
    result = parse_ticket_info(["GIOO"], [_poly(0, 0)])

    assert result["train_code"] == "G100"
