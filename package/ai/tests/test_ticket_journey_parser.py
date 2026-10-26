"""Synthetic cards only: no passenger data or real screenshots."""
import pytest

from app.services.ticket_journey_parser import extract_journey_time, apply_shared_ticket_date, apply_section_ticket_dates
from app.services.ticket_parser import parse_ticket_info, parse_ticket_cards

pytestmark = pytest.mark.smoke


def card(*blocks):
    texts, polys = [], []
    for text, x, y in blocks:
        texts.append(text)
        polys.append([[x, y], [x+60, y], [x+60, y+20], [x, y+20]])
    return texts, polys


def test_explicit_duration_does_not_use_transfer_wait():
    texts, polys = card(('G123', 180, 100), ('历时3时17分', 180, 60), ('同站换乘1时22分', 180, 300))
    assert extract_journey_time(texts, polys, {'train_code': 'G123'}) == {
        'duration_minutes': 197, 'duration_source': 'ticket-duration'}


@pytest.mark.parametrize('start,end,minutes', [('23:40','01:10',90), ('08:20','10:00+1天',1540)])
def test_route_clocks_ignore_phone_status_bar_and_keep_next_day(start, end, minutes):
    texts, polys = card(('12:39', 0, 0), ('北京南',20,300),('上海虹桥',360,300),
                        (start,20,260),(end,360,260))
    assert extract_journey_time(texts,polys,{'departure_station':'北京南','arrival_station':'上海虹桥'}) == {
        'duration_minutes':minutes,'duration_source':'ticket-clocks'}


def test_single_clock_is_not_an_elapsed_time():
    texts,polys=card(('北京南',20,100),('上海虹桥',360,100),('08:20',20,70))
    assert extract_journey_time(texts,polys,{'departure_station':'北京南','arrival_station':'上海虹桥'}) == {}


def test_duration_includes_days_and_does_not_parse_chinese_departure_clock():
    texts,polys=card(('2026年10月5日8时30分开',20,100),('历时1天2小时15分',180,150))
    assert extract_journey_time(texts,polys,{})['duration_minutes'] == 1575


def test_status_bar_hd_and_service_timetable_label_are_not_duration():
    texts,polys=card(('22:47 HD',20,0),('G123时刻表',180,100))
    assert extract_journey_time(texts,polys,{'train_code':'G123'}) == {}


def test_route_labels_and_position_icons_are_not_stations():
    texts,polys=card(('天津站①',20,100),('①大同站',360,100),('K888',180,100),
        ('车次',20,150),('座席',360,150),('今天',360,70))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station']) == ('天津','大同')


def test_vertical_merged_clock_station_rows_preserve_direction():
    texts,polys=card(('12:50 北京站',20,100),('13:54 唐山站',20,140),
                    ('G8807',20,230),('车次',20,190),('座席',130,190),('01月20日',20,50))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station']) == ('北京','唐山')
    assert result['duration_minutes'] == 64


def test_compact_order_route_and_badge_before_code():
    texts,polys=card(('G3177南京南一西安北',20,40),('发车时间:2026-01-21 周三07:57开',20,80))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station']) == ('南京南','西安北')
    texts,polys=card(('0G3148',180,100),('连云港',20,100),('商丘',360,100))
    assert parse_ticket_info(texts,polys)['train_code'] == 'G3148'


def test_merged_two_clock_station_line():
    texts,polys=card(('10:14 珠海站 - 16:37 信阳东站',20,100),('G1044',20,140),('02月01日',20,70))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station']) == ('珠海','信阳东')


def test_shared_date_only_applies_when_unambiguous_and_codes_are_present():
    tickets=[{'train_code':'G7084','datetime':'08:37'},{'train_code':'D3068','datetime':'09:32'}]
    apply_shared_ticket_date(['7月27日周六','G7084','D3068'],tickets)
    assert tickets[1]['datetime']=='7月27日 09:32'
    ambiguous=[{'train_code':'G7084','datetime':'08:37'}]
    apply_shared_ticket_date(['7月27日','7月28日','G7084'],ambiguous)
    assert ambiguous[0]['datetime']=='08:37'


def test_labeled_header_supplies_year_for_same_departure_day():
    texts,polys=card(('乘车日期：2025年1月16日周四',20,30),('K4716',180,100),
        ('上海',20,120),('达州',360,120),('1月16日',20,100),('11:32',20,80),
        ('14:53',360,80),('+1',390,100))
    result=parse_ticket_info(texts,polys)
    assert result['datetime']=='2025年01月16日 11:32'
    assert result['duration_minutes']==1641


def test_compact_order_list_splits_complete_cards_without_field_mixing():
    texts,polys=card(('G3177南京南一西安北',20,40),('发车时间：2026-01-21 07:57',20,80),
        ('G123北京南一上海虹桥',20,240),('发车时间：2025-11-14 08:00',20,280))
    cards=parse_ticket_cards(texts,polys)
    assert len(cards)==2
    assert cards[0]['train_code']=='G3177' and cards[0]['departure_station']=='南京南'
    assert cards[1]['train_code']=='G123' and cards[1]['datetime']=='2025年11月14日 08:00'


def test_selling_station_header_does_not_reverse_the_ticket_route():
    texts,polys=card(('秦皇岛站',400,30),('秦皇岛唐山',20,100),('Y224次',350,110),
                    ('1998年05月08日 08:07',20,180))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station'])==('秦皇岛','唐山')


def test_glued_month_day_and_departure_clock_are_separated():
    texts,polys=card(('衡山西长沙南',20,60),('02-0214:38至15:07',20,100),('车次G264',20,140))
    result=parse_ticket_info(texts,polys)
    assert result['datetime']=='02月02日 14:38'
    assert result['duration_minutes']==29


def test_section_date_does_not_borrow_the_following_groups_date():
    texts,polys=card(('乘车日期：2023年9月28日周四',20,0),('15:11',20,80),
                    ('23:47',20,200),('乘车日期：2023年10月5日周四',20,300))
    tickets=[{'datetime':'23:47'}]
    apply_section_ticket_dates(texts,polys,tickets)
    assert tickets[0]['datetime']=='2023年9月28日 23:47'


def test_fare_must_not_become_numeric_service():
    texts,polys=card(('武汉站',20,100),('郑州东站',360,100),('13:35',20,70),('二等座¥292',20,150))
    assert parse_ticket_info(texts,polys)['train_code'] == ''


def test_bare_numeric_service_still_parses():
    texts,polys=card(('1462',180,100),('北京站',20,100),('上海站',360,100))
    assert parse_ticket_info(texts,polys)['train_code'] == '1462'


@pytest.mark.parametrize('code',['N994次','Y224次','L123次','S101','5803次','307次','游5次'])
def test_legacy_and_suburban_service_formats(code):
    texts,polys=card((code,180,100),('北京站',20,100),('上海站',360,100))
    assert parse_ticket_info(texts,polys)['train_code']==code.removesuffix('次')


def test_gate_letter_does_not_create_a_second_train_service():
    texts,polys=card(('A11检票口',20,30),('N3',20,60),('G123',180,100),
                    ('北京南',20,100),('上海虹桥',360,100))
    assert parse_ticket_info(texts,polys)['train_code']=='G123'


def test_five_digit_ocr_code_is_only_proposed_as_candidates():
    texts,polys=card(('G17138',180,100),('天津西',20,100),('洛阳龙门',360,100))
    result=parse_ticket_info(texts,polys)
    assert result['train_code']==''
    assert result['train_code_candidates']==['G1713','G7138']


def test_paper_route_arrow_and_embedded_numeric_service():
    texts,polys=card(('烟台一郑州',20,100),('2130次',300,100),('大连',400,20))
    result=parse_ticket_info(texts,polys)
    assert (result['departure_station'],result['arrival_station'])==('烟台','郑州')
    texts,polys=card(('沈阳北',20,100),('齐齐哈尔2061次',300,100))
    result=parse_ticket_info(texts,polys)
    assert result['train_code']=='2061'
    assert (result['departure_station'],result['arrival_station'])==('沈阳北','齐齐哈尔')


def test_adjacent_split_station_glyphs_need_geometry():
    texts,polys=card(('青',20,100),('岛站',84,100),('G172',180,100),('天津西站',360,100))
    assert parse_ticket_info(texts,polys)['departure_station']=='青岛'
    texts,polys=card(('青',20,20),('岛站',84,100),('G172',180,100),('天津西站',360,100))
    assert parse_ticket_info(texts,polys)['departure_station']!='青岛'


def test_printed_romanization_confirms_one_damaged_station_glyph():
    texts,polys=card(('鄂邑站',20,100),('Huyi',20,130),('G308',180,100),('西安北站',360,100),
                    ("Xi'anbei",360,130))
    result=parse_ticket_info(texts,polys)
    assert result['departure_station']=='鄠邑'
    texts,polys=card(('鄂邑站',20,100),('Dawu',20,130),('G308',180,100),('西安北站',360,100))
    assert parse_ticket_info(texts,polys)['departure_station']!='鄠邑'


def test_noisy_station_and_serial_do_not_hide_a_glued_service():
    texts,polys=card(('民B0权站71K361',20,100),('西安站',360,100),('2020年08月29日20:54开',20,150))
    result=parse_ticket_info(texts,polys)
    assert result['train_code']=='K361'
    assert (result['departure_station'],result['arrival_station'])==('民权','西安')
    texts,polys=card(('Gi42',180,100),('曲阜东站',20,100),('北京南站',360,100))
    assert parse_ticket_info(texts,polys)['train_code']=='G142'


@pytest.mark.parametrize('label',['去看看','时刻表','其他问题','年月日日'])
def test_interface_labels_and_date_fragments_are_not_stations(label):
    texts,polys=card(('G123',180,100),('北京南',20,100),(label,360,100))
    result=parse_ticket_info(texts,polys)
    assert label not in (result['departure_station'],result['arrival_station'])
