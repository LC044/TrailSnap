"""夜间盲区补测：AI 票据解析的日期时间抽取与车厢/座位粘连拆分。

覆盖 app/services/ticket_parser.py 中此前未被覆盖的
``parse_ticket_info`` 日期时间分支与 ``_split_carriage_seat_if_glued``。
"""
import pytest

from app.services import ticket_parser

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


@pytest.mark.parametrize(
    ("ocr_texts", "expected"),
    [
        (["2025年01月18日 13:46"], "2025年01月18日 13:46"),
        (["2025.01.18", "13:46开"], "2025年01月18日 13:46"),
        (["2025年01月18日13:46开"], "2025年01月18日 13:46"),
        (["2025年01月26014:08"], "2025年01月26日 14:08"),
    ],
)
def test_datetime_is_recovered_from_common_ocr_layouts(ocr_texts, expected):
    """不同 OCR 排版下最终 datetime 都要归一化成同一格式。"""
    info = ticket_parser.parse_ticket_info(list(ocr_texts), [])
    assert info.get("datetime") == expected


def test_glued_carriage_and_seat_is_split():
    """「12 01A」粘连时车厢号必须拆出来，座位号保持 2 位车厢 + 座位字母。"""
    ticket_info = {"seat_num": "1201A"}

    ticket_parser._split_carriage_seat_if_glued(ticket_info)

    assert ticket_info["carriage"] == "12"
    assert ticket_info["seat_num"] == "01A"


def test_existing_carriage_is_never_overwritten():
    """已经识别出车厢号时不得再次改写它。"""
    ticket_info = {"carriage": "08", "seat_num": "1201A"}

    ticket_parser._split_carriage_seat_if_glued(ticket_info)

    assert ticket_info["carriage"] == "08"
    assert ticket_info["seat_num"] == "1201A"


def test_seat_without_glued_carriage_is_left_untouched():
    """不符合粘连格式的座位号保持原样。"""
    ticket_info = {"seat_num": "1A"}

    ticket_parser._split_carriage_seat_if_glued(ticket_info)

    assert "carriage" not in ticket_info
    assert ticket_info["seat_num"] == "1A"
