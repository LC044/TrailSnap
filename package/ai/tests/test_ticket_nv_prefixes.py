"""Synthetic N/V tickets exercise extraction without loading OCR models."""
import pytest

from app.services.ticket_parser import candidate_train_codes, normalize_ticket_text, parse_ticket_info, resolve_train_code
from app.services.ticket_journey_parser import apply_shared_ticket_date

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize('code', ['N123', 'V456', 'n123', 'v456'])
def test_nv_ticket_code_normalization_and_complete_ticket(code):
    normalized = code.upper()
    assert normalize_ticket_text(code) == normalized
    assert candidate_train_codes([f'车次 {code}']) == {normalized}
    texts = [code, '2026年11月12日 08:30', '北京南站', '上海虹桥站', '04车09B号']
    polys = [[[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]]
             for x, y in [(200, 80), (20, 120), (20, 180), (360, 180), (20, 240)]]
    result = parse_ticket_info(texts, polys)
    assert result['train_code'] == normalized
    assert (result['departure_station'], result['arrival_station']) == ('北京南', '上海虹桥')


def test_nv_slash_change_requires_departure_evidence_and_shared_date_supports_both():
    assert candidate_train_codes(['N123/V456']) == {'N123', 'V456'}
    assert resolve_train_code(['N123/V456']) == ''
    assert resolve_train_code(['N123/V456', '北京南起车次变更为V456'], '北京南') == 'V456'
    tickets = [{'train_code': code, 'datetime': '08:30'} for code in ['N123', 'V456']]
    apply_shared_ticket_date(['乘车日期：2026年11月12日', 'N123', 'V456'], tickets)
    assert all(ticket['datetime'] == '2026年11月12日 08:30' for ticket in tickets)
    assert not candidate_train_codes(['NV123', 'VN456', 'INV123', 'N12345'])


def test_nv_railway_evidence_still_requires_ticket_signals():
    from app.services.ticket_service import has_railway_evidence
    assert has_railway_evidence(['N123', '04车09B号'])
    assert has_railway_evidence(['V456', '12306'])
    assert not has_railway_evidence(['V456', '航班', '机场', '经济舱'])
