"""REQ-159: synthetic OCR only; never include passenger screenshots."""
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.services.ticket_parser import parse_ticket_info, resolve_train_code
from app.services.fly_ticket_parser import extract_flight_info

pytestmark = pytest.mark.smoke


def parse(*blocks):
    texts, polys = [], []
    for text, x, y in blocks:
        texts.append(text)
        polys.append([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])
    return parse_ticket_info(texts, polys)


def test_detail_without_passenger_or_year():
    result = parse(('复兴号', 200, 40), ('智能动车', 200, 65),
                   ('10月5日', 20, 100), ('16:41', 20, 140),
                   ('西安东>', 20, 180), ('汉口>', 360, 180))
    assert (result['departure_station'], result['arrival_station']) == ('西安东', '汉口')
    assert result['datetime'] == '10月05日 16:41'
    for key in ('name', 'price', 'seat_type', 'carriage', 'seat_num', 'train_code'):
        assert result[key] == ''


@pytest.mark.parametrize('code,dep,arr,date,time,seat,car,num', [
    ('G3926', '西安东', '汉口', '2026/10/05', '16:41', '04車09B號', '04', '09B'),
    ('G3915', '汉口', '西安东', '2027/10/07', '18:12', '07车15D号', '07', '15D'),
])
def test_separate_cards(code, dep, arr, date, time, seat, car, num):
    result = parse((code, 200, 80), (date, 20, 120), (time, 20, 150),
                   (dep, 20, 180), (arr, 360, 180), (seat, 20, 240))
    assert (result['train_code'], result['departure_station'], result['arrival_station']) == (code, dep, arr)
    assert result['datetime'] == date.replace('/', '年', 1).replace('/', '月') + '日 ' + time
    assert (result['carriage'], result['seat_num']) == (car, num)
    assert result['name'] == result['price'] == result['seat_type'] == ''


def test_travel_service_labeled_name_and_advert_year():
    result = parse(('G3915', 200, 80), ('10月7日 18:12', 20, 120),
                   ('汉口', 20, 180), ('西安东', 360, 180),
                   ('07 車 15 D 號二等座', 20, 220), ('乘车人', 20, 270),
                   ('林小明', 120, 270), ('2026年会员活动', 20, 600), ('复兴号', 200, 50))
    assert result['name'] == '林小明'
    assert result['datetime'] == '10月07日 18:12'
    assert (result['carriage'], result['seat_num'], result['seat_type']) == ('07', '15D', '二等座')


def test_new_station_requires_route_evidence_and_geometry_orders_stations():
    result = parse(('G123', 180, 80), ('汉口>', 360, 150), ('云川新城>', 20, 150), ('智能动车', 0, 20))
    assert (result['departure_station'], result['arrival_station']) == ('云川新城', '汉口')
    assert parse(('随意文字', 0, 0), ('其他文字', 0, 200))['departure_station'] == ''


def test_paper_ticket_identity_name():
    result = parse(('北京南站', 20, 80), ('G123', 180, 80), ('上海虹桥站', 360, 80),
                   ('2027年01月02日 08:30', 20, 120), ('110101********1234林小明', 20, 200))
    assert result['name'] == '林小明'
    assert result['train_code'] == 'G123'
    assert result['departure_station'] == '北京南'


def test_service_change_is_departure_specific():
    texts = ['G3927/G3926', '西安东起车次变更为 G3926']
    assert resolve_train_code(texts, '西安东') == 'G3926'
    assert resolve_train_code(texts, '汉口') == ''
    assert resolve_train_code(['G3927/G3926']) == ''


def test_current_station_note_uses_nearest_preceding_stop():
    texts = ['G3927/G3926', '汉口', '西安东', '本次列车自当前车站起车次号变更为G3926']
    polys = [[[x, y], [x + 80, y], [x + 80, y + 20], [x, y + 20]]
             for x, y in [(200, 0), (20, 400), (20, 500), (20, 540)]]
    assert resolve_train_code(texts, '西安东', polys) == 'G3926'
    assert resolve_train_code(texts, '汉口', polys) == ''
    assert resolve_train_code(texts, '西安东') == ''


def test_flight_missing_year_is_marked_inferred():
    result = extract_flight_info(['CA1234', '10月7日 18:12', '上海 → 北京'])
    assert result['datetime'] == f'{datetime.now().year}-10-07 18:12'
    assert result['year_source'] == 'inferred_current_year'


def test_status_bar_and_stop_date_do_not_override_departure():
    result = parse(('09:00', 0, 0), ('G3915', 180, 100),
                   ('10月7日', 20, 150), ('18:12', 20, 180),
                   ('汉口', 20, 220), ('西安东', 360, 220),
                   ('经停 2027/10/08 03:00', 20, 400), ('广告 2028/10/09', 20, 500))
    assert result['datetime'] == '10月07日 18:12'


def test_flight_explicit_slash_year_and_status_bar():
    result = extract_flight_info(['09:00', 'CA1234', '2027/10/07', '18:12', '广告 2028/01/01'])
    assert result['datetime'] == '2027-10-07 18:12'


def test_railway_reclassification_requires_multiple_signals():
    from app.services.ticket_service import has_railway_evidence
    assert has_railway_evidence(['G3915', '复兴号', '07車15D號', '二等座'])
    assert not has_railway_evidence(['CA1234', '机场', '经济舱'])
    assert not has_railway_evidence(['G3915', '航班', '机场', '12306'])


def test_supplement_changes_only_code_and_failure_keeps_fields():
    from app.services.ticket_service import supplement_train_code
    info = {'departure_station': '西安东', 'train_code': '', 'name': ''}
    ocr = Mock(return_value=[([], 'G3927/G3926'), ([], '西安东起车次变更为 G3926'), ([], '乘车人林小明')])
    supplement_train_code(info, object(), ocr)
    assert info == {'departure_station': '西安东', 'train_code': 'G3926', 'name': ''}
    before = info.copy()
    supplement_train_code(info, object(), Mock(side_effect=RuntimeError('OCR unavailable')))
    assert info == before
