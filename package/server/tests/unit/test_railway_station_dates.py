"""Compact station updates and the legacy-v2 fallback operate on real SQLite."""
import copy

import pytest

from railway.history_cache import HistoryCache
from tests.unit.test_railway_history import initial, pack, v2pack, version

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def compact_feed(rows, first, patch):
    rows = copy.deepcopy(rows)
    value = rows['station:AAA']
    value['last_seen'] = '2026-10-04'
    value['names'][-1]['last'] = '2026-10-04'
    value['versions'][-1]['last'] = '2026-10-04'
    delta, delta_bytes = v2pack(2, station_dates=[patch])
    snapshot, snapshot_bytes = pack(2, rows, True)
    manifest = dict(first, sequence=2, snapshot=snapshot, station_dates_version=1,
                    compact_deltas=[delta])
    return manifest, {delta['file']: delta_bytes, snapshot['file']: snapshot_bytes}, rows


def date_patch():
    return {'telecode': 'AAA', 'last_seen': '2026-10-04',
            'name_last': ['2026-10-02', '2026-10-04'], 'version_last': ['2026-10-04']}


def test_compact_dates_equal_full_snapshot_and_old_v2_safely_falls_back(initial, tmp_path):
    cache, rows, first, original = initial
    manifest, files, expected = compact_feed(rows, first, date_patch())
    fetched = []
    cache.sync(manifest, lambda name: (fetched.append(name), files[name])[1])
    assert fetched == [manifest['compact_deltas'][0]['file']]
    assert cache.stations('AAA')[0] == expected['station:AAA']
    assert cache.stations('旧站')[0]['names'][-1]['last'] == '2026-10-04'
    full = HistoryCache(tmp_path / 'full.sqlite')
    full.sync(manifest, files.__getitem__)
    assert full.stations('AAA') == cache.stations('AAA')
    # A legacy v2 reader knows only the original manifest keys. Its unchanged
    # gap detection must fetch the complete snapshot, never the compact delta.
    legacy = HistoryCache(tmp_path / 'legacy.sqlite')
    legacy.sync(first, original.__getitem__)
    legacy_manifest = {k: v for k, v in manifest.items() if k not in ('compact_deltas', 'station_dates_version')}
    fetched.clear()
    legacy.sync(legacy_manifest, lambda name: (fetched.append(name), files[name])[1])
    assert fetched == [manifest['snapshot']['file']]
    assert legacy.stations('AAA') == cache.stations('AAA')
    cache.sync(manifest, lambda _: pytest.fail('up-to-date cache must not download'))
    # An old client upgraded after taking a full snapshot can resume compact sync.
    row = date_patch(); row.update(last_seen='2026-10-05', name_last=['2026-10-02', '2026-10-05'], version_last=['2026-10-05'])
    delta, raw = v2pack(3, station_dates=[row])
    snapshot = dict(manifest['snapshot'], sequence=3)
    third = dict(manifest, sequence=3, snapshot=snapshot, compact_deltas=manifest['compact_deltas'] + [delta])
    legacy.sync(third, lambda name: raw if name == delta['file'] else pytest.fail('upgrade should use delta'))
    assert legacy.stations('AAA')[0]['last_seen'] == '2026-10-05'


@pytest.mark.parametrize('change', [
    {'telecode': 'XXX'}, {'telecode': '../'}, {'name_last': []}, {'version_last': []},
    {'last_seen': '2026-02-30'}, {'last_seen': '2026-10-01'},
    {'version_last': ['2026-09-30']}, {'version_last': ['2026-10-05']},
])
def test_bad_station_dates_roll_back_pack_and_cursor(initial, change):
    cache, rows, first, _ = initial
    patch = dict(date_patch(), **change)
    manifest, files, _ = compact_feed(rows, first, patch)
    before = cache.stations('AAA')
    with pytest.raises(ValueError):
        cache.sync(manifest, files.__getitem__)
    assert cache.status()['sequence'] == 1
    assert cache.stations('AAA') == before


@pytest.mark.parametrize('code', ['N123', 'V456', '1234'])
def test_nv_and_numeric_history_queries_and_candidate_recovery(initial, code):
    from app.service.ticket_journey import resolve_code_candidates
    cache, rows, first, _ = initial
    rows['train:' + code] = {'code': code, 'versions': [version('NV', ['2026-10-04'])]}
    snapshot, raw = pack(2, rows, True)
    cache.sync(dict(first, sequence=2, snapshot=snapshot, deltas=[]), lambda _: raw)
    assert cache.resolve(code.lower(), '2026-10-04')['match'] == 'exact'
    if code[0] in 'NV':
        info = {'train_code_candidates': [code], 'departure_station': '新站', 'arrival_station': '终点'}
        assert resolve_code_candidates(info, '2026-10-04', cache) == code
