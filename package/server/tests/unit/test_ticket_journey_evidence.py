import pytest
from app.service.ticket_journey import enrich_journey, repair_station_names, resolve_code_candidates, parse_ticket_datetime
from types import SimpleNamespace
from datetime import datetime

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def test_ocr_reversed_year_far_in_the_future_is_not_a_ticket_datetime():
    with pytest.raises(ValueError):
        parse_ticket_datetime('5052年02月05日 09:15',datetime(2025,1,1))


def test_ticket_duration_overrides_nearest_history():
    result = enrich_journey({'total_time': 130, 'total_mileage':250,'stop_stations':[]},
        {'match':'nearest','matched_date':'2026-10-25','distance_source':'gps-haversine-x1.2'},
        {'duration_minutes':125,'duration_source':'ticket-duration'},'G123')
    assert result['total_time'] == 125
    assert result['sources']['duration_source'] == 'ticket-duration'
    assert result['sources']['match'] == 'nearest'


def test_unmatched_route_duration_is_explicit_estimate():
    result = enrich_journey({'total_time':None,'total_mileage':300,'stop_stations':[]},
        {'match':'endpoints'}, {}, 'K123')
    assert result['total_time'] == 300
    assert result['sources']['duration_source'] == 'estimated-distance-speed'
    assert result['sources']['assumed_speed_kmh'] == 60
    assert result['stop_stations'] == []


@pytest.mark.parametrize('duration',[-1,0,True,99999,'123'])
def test_invalid_ocr_duration_does_not_replace_history(duration):
    result = enrich_journey({'total_time':130,'total_mileage':250},
        {'match':'exact'}, {'duration_minutes':duration,'duration_source':'ticket-duration'},'G123')
    assert result['total_time'] == 130
    assert result['sources']['duration_source'] == 'railway-history'


def test_missing_coordinates_do_not_produce_fake_distance_or_duration():
    result = enrich_journey({'total_time':None,'total_mileage':None}, {'match':'endpoints'}, {},'G123')
    assert result['total_time'] is result['total_mileage'] is None


def test_station_ocr_repair_requires_unique_ordered_train_segment():
    class Cache:
        def stations(self,name):return [name] if name in ('包头','大板') else []
        def resolve(self,code,day,*endpoints):
            if not endpoints:return {'stops':[{'n':'包头'},{'n':'大板'}]}
            return {'match':'nearest' if endpoints==('包头','大板') else 'endpoints'}
    ticket=SimpleNamespace(train_code='K123',date_time=datetime(2026,1,1),departure_station='句头',arrival_station='大板')
    correction=repair_station_names(ticket,Cache())
    assert correction['departure_station']['resolved']=='包头'
    assert ticket.departure_station=='句头'
    ticket.departure_station='未知城市'
    assert repair_station_names(ticket,Cache()) == {}
    ticket.departure_station='包头';ticket.arrival_station='句头'
    assert repair_station_names(ticket,Cache()) == {}


def test_two_damaged_glyphs_require_both_departure_clock_and_duration():
    class Cache:
        def stations(self,name):return [name] if name in ('泰安','菏泽东') else []
        def resolve(self,code,day,*ends):
            if not ends:return {'stops':[{'n':'泰安','d':'09:58'},{'n':'菏泽东','d':None}]}
            return {'match':'nearest','duration_minutes':102} if ends==('泰安','菏泽东') else {'match':'endpoints'}
    ticket=SimpleNamespace(train_code='G5523',date_time=datetime(2025,9,30,9,58),departure_station='寿宏',arrival_station='菏泽东')
    assert repair_station_names(ticket,Cache()) == {}
    assert repair_station_names(ticket,Cache(),{'duration_minutes':102})['departure_station']['resolved']=='泰安'
    assert repair_station_names(ticket,Cache(),{'duration_minutes':222}) == {}


def test_ocr_code_candidates_require_a_unique_ordered_route():
    class Cache:
        def resolve(self,code,day,*ends):return {'match':'nearest' if code=='G1713' else 'endpoints'}
    info={'train_code':'','train_code_candidates':['G1713','G7138'],
          'departure_station':'天津西','arrival_station':'洛阳龙门'}
    assert resolve_code_candidates(info,datetime(2025,1,1),Cache())=='G1713'


@pytest.mark.asyncio
async def test_missing_intermediate_gps_falls_back_to_known_endpoints():
    from unittest.mock import AsyncMock,patch
    from app.service.tasks import tickets
    ticket=SimpleNamespace(train_code='G123',date_time=datetime(2026,1,1),departure_station='北京南',arrival_station='上海虹桥')
    history={'distance_km':None,'duration_minutes':120,'stops':[],'match':'nearest'}
    with patch.object(tickets,'get_schedule_info',new=AsyncMock(return_value=history)), \
         patch.object(tickets,'get_endpoint_distance',new=AsyncMock(return_value=1000)):
        result=await tickets.calculate_ticket_mileage_and_time(ticket,evidence={})
    assert result['total_mileage']==1000
    assert result['sources']['distance_source']=='gps-endpoints-haversine-x1.2'
    assert result['total_time']==120


def test_yearless_leap_day_uses_latest_possible_year_and_is_marked_inferred():
    value,inferred=parse_ticket_datetime('02月29日 08:41',datetime(2026,10,25))
    assert value==datetime(2024,2,29,8,41) and inferred
    with pytest.raises(ValueError):parse_ticket_datetime('2025年02月29日 08:41',datetime(2026,10,25))
