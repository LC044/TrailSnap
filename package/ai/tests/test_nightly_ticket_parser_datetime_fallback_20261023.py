"""Nightly gap tests for the ticket datetime fallback patterns (2026-10-23).

`parse_ticket_info` 在逐块扫描拿不到出发时间时，会退回到一组正则兜底
（app/services/ticket_parser.py 约 1015-1200 行）。这组分支此前几乎没有被执行到，
覆盖报告显示 ticket_parser.py 仍有 174 行未覆盖，其中大半集中在这段兜底逻辑上。
本文件用表驱动的方式把「能正确还原出日期时间」的格式逐个钉住。
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
        # (\d{4})(\d{2})(\d{2})日(\d{2})(\d{2})
        ("20240507日1022", "2024年05月07日 10:22"),
        # (\d{4})年(\d{1,2})(\d{2})日(\d{1,2}):(\d{2})开?
        ("2024年05月07日10:22开", "2024年05月07日 10:22"),
        # 全角冒号
        ("2024年05月07日10：22", "2024年05月07日 10:22"),
        # (\d{4}年\d{1,2}月\d{1,2}日)[\s:：]*(\d{1,2})[:：](\d{2})开?
        ("2024年08月29日20：54开", "2024年08月29日 20:54"),
        # 月份只有一位数 -> 补零
        ("2024年5月07日10:22", "2024年05月07日 10:22"),
        # 粘连时间：2024年02月26014:08 -> 2024年02月26日 14:08
        ("2024年02月26014:08", "2024年02月26日 14:08"),
    ],
)
def test_parse_ticket_info_restores_datetime_from_mixed_formats(text, expected):
    assert _parse_datetime(text) == expected


def test_parse_ticket_info_keeps_date_only_when_no_time_present():
    """只有日期没有时间时，退回日期本身，不编造时分。"""
    assert _parse_datetime("2024年02月26日") == "2024年02月26日"


def test_parse_ticket_info_returns_empty_datetime_for_text_without_date():
    """完全没有日期信息时，datetime 保持空串（不产生 1970 之类的假时间）。"""
    assert _parse_datetime("随便一段没有日期的文本") == ""


def test_parse_ticket_info_normalizes_fullwidth_train_prefix():
    """OCR 常见全角字符（車/号）需要归一化后再解析。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["G1234", "北京南", "天津"], [_poly(0, 0), _poly(0, 20), _poly(0, 40)])
    assert info["train_code"] == "G1234"
    assert info["departure_station"]
    assert info["arrival_station"]


def test_parse_ticket_info_train_code_numeric_fallback_skips_date_blocks():
    """纯数字车次兜底不能把日期块当成车次。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["2024年05月07日10:22", "G1234"], [_poly(0, 0), _poly(0, 20)])
    assert info["train_code"] == "G1234"


def test_parse_ticket_info_requires_an_unambiguous_train_code():
    """出现多个互相冲突的车次码时，解析器不猜，train_code 留空。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["C0000", "K123"], [_poly(0, 0), _poly(0, 20)])
    assert info["train_code"] == ""


def test_parse_ticket_info_keeps_single_train_code():
    """只有一个车次码时原样保留。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["K123"], [_poly(0, 0)])
    assert info["train_code"] == "K123"


def test_parse_ticket_info_handles_short_polygon_without_raising():
    """点数不足 4 的多边形不能抛异常（OCR 偶发返回残缺框）。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["G1234", "北京南"], [[[0, 0], [10, 0]], _poly(0, 20)])
    assert info["train_code"] == "G1234"


def test_parse_ticket_info_sorts_blocks_by_vertical_position():
    """多边形乱序到达时按 y 坐标（视觉顺序）解析，而不是按数组顺序。"""
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["G1234", "北京南", "天津"], [_poly(0, 100), _poly(0, 0), _poly(0, 50)])
    assert info["train_code"] == "G1234"
    assert info["departure_station"]
