"""Real SQLite and compressed feed contracts; no network or production databases."""
import gzip
import hashlib
import json
from datetime import date

import pytest

from railway.history_cache import HistoryCache

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def station(code, name, lat, lng, old=None):
    return {'telecode':code,'names':[{'name':n,'first':'2026-10-01','last':'2026-10-02'} for n in ([old,name] if old else [name])],
            'status':'active','versions':[{'first':'2026-10-01','last':'2026-10-02',
            'data':{'name':name,'gps':{'latitude':str(lat),'longitute':str(lng)},'future_field':{'a':1}}}]}


def version(hash, days, departure='23:50', arrival='01:00'):
    return {'no':'1234','f':'新站','t':'终点','h':hash,'fd':min(days),'ld':max(days),'dates':days,
            's':[{'n':'新站','c':'AAA','a':None,'d':departure,'dd':0},
                 {'n':'终点','c':'BBB','a':arrival,'d':None,'dd':1}]}


def pack(sequence, rows, full=False):
    stations, versions, observations = [], [], []
    for key, value in rows.items():
        if key.startswith('station:'):
            stations.append(value)
        elif key.startswith('train:'):
            for v in value['versions']:
                versions.append({'code':value['code'], 'value':{k:x for k,x in v.items() if k not in ('dates','fd','ld','observed_at')}})
                observations.append({'code':value['code'], 'hash':v['h'], 'dates':v.get('dates') or [v['fd'],v['ld']]})
        else:
            raise ValueError('Unknown test entity')
    return v2pack(sequence, stations, versions, observations, full)


def v2pack(sequence, stations=(), versions=(), observations=(), full=False):
    data=gzip.compress(json.dumps({'schema_version':2,'sequence':sequence,'full':full,
                                  'stations':stations, 'train_versions':versions, 'observations':observations}).encode())
    sha=hashlib.sha256(data).hexdigest()
    return {'sequence':sequence,'file':f'packs/{sha}.json.gz','bytes':len(data),'sha256':sha}, data


def feed(sequence, rows, previous=None):
    descriptor,data=pack(sequence,rows,True)
    return {'schema_version':2,'sequence':sequence,'snapshot':descriptor,
            'deltas':([*previous['deltas'],descriptor] if previous else [descriptor])}, {descriptor['file']:data}


@pytest.fixture
def initial(tmp_path, monkeypatch):
    from railway import history_seed
    monkeypatch.setattr(history_seed, 'station_metadata', lambda: {})
    monkeypatch.setenv('RAILWAY_DB_URL','sqlite:///:memory:')
    cache=HistoryCache(tmp_path/'history.sqlite')
    rows={'station:AAA':station('AAA','新站',39.9,116.4,'旧站'),
          'station:BBB':station('BBB','终点',31.2,121.5),
          'train:G1':{'code':'G1','versions':[version('A',['2026-10-01','2026-10-03']),version('B',['2026-10-02'])]}}
    manifest,files=feed(1,rows)
    cache.sync(manifest,files.__getitem__)
    return cache,rows,manifest,files


def test_exact_nearest_and_reversion_do_not_bridge_unobserved_gaps(initial):
    cache,*_=initial
    assert cache.resolve('g1',date(2026,10,2))['version']=='B'
    assert cache.resolve('G1','2026-10-03')['version']=='A'
    nearest=cache.resolve('G1','2026-09-20')
    assert nearest['match']=='nearest' and nearest['matched_date']=='2026-10-01'
    assert nearest['duration_minutes']==70
    assert nearest['distance_km']>1000


def test_historical_alias_and_unknown_endpoints(initial):
    cache,*_=initial
    assert cache.stations('旧站')[0]['versions'][0]['data']['future_field']=={'a':1}
    known=cache.resolve('G1','2026-10-01','旧站','终点')
    assert len(known['stops'])==2
    unknown=cache.resolve('G99999','2026-10-01','旧站','终点')
    assert unknown['match']=='endpoints' and unknown['train_no'] is None
    assert unknown['stops']==[] and unknown['duration_minutes'] is None
    assert unknown['distance_km']>0
    assert cache.resolve('G99999','2026-10-01','未知站','终点')['distance_km'] is None


def test_incremental_sync_and_idempotency_fetch_only_new_packs(initial):
    cache,rows,first,_=initial
    desc,data=pack(2,{'station:CCC':station('CCC','新建站',30,115)})
    snapshot,_=pack(2,dict(rows, **{'station:CCC':station('CCC','新建站',30,115)}),True)
    manifest={'schema_version':2,'sequence':2,'snapshot':snapshot,'deltas':first['deltas']+[desc]}
    calls=[]
    def load(file): calls.append(file);return data
    cache.sync(manifest,load)
    assert cache.status()['sequence']==2 and cache.status()['stations']==3
    assert calls==[desc['file']]
    cache.sync(manifest,lambda _:pytest.fail('duplicate sync downloaded data'))
    assert cache.status()['versions']==2


def test_checksum_or_mid_transaction_failure_cannot_advance_cursor(initial):
    cache,_,first,_=initial
    desc,data=v2pack(2, [station('CCC','新建站',30,115)], observations=[{'code':'missing','hash':'x','dates':['2026-10-02']}])
    snapshot=dict(first['snapshot'],sequence=2)
    manifest={'schema_version':2,'sequence':2,'snapshot':snapshot,'deltas':first['deltas']+[desc]}
    with pytest.raises(ValueError,match='checksum'):
        cache.sync(manifest,lambda _:data+b'bad')
    with pytest.raises(ValueError,match='missing'):
        cache.sync(manifest,lambda _:data)
    assert cache.status()['sequence']==1 and not cache.stations('CCC')


def test_unknown_schema_rollback_and_unsafe_path_refused(initial):
    cache,_,manifest,_=initial
    with pytest.raises(ValueError,match='schema'):
        cache.sync(dict(manifest,schema_version=3),lambda _:b'')
    with pytest.raises(ValueError,match='rollback'):
        cache.sync(dict(manifest,sequence=0),lambda _:b'')
    desc={'sequence':2,'file':'../secret','bytes':0,'sha256':'a'*64}
    with pytest.raises(ValueError,match='path'):
        cache.sync(dict(manifest,sequence=2,deltas=[desc]),lambda _:pytest.fail('unsafe file fetched'))


def test_missing_gps_and_midnight_departure(initial):
    cache,rows,first,_=initial
    v=version('C',['2026-10-04'],departure='00:05',arrival='01:00')
    v['s'][0].update(a='23:55',dd=0)
    v['s'][1]['dd']=1
    rows['train:G1']['versions'].append(v)
    rows['station:BBB']['versions'][0]['data']['gps']['latitude']='nan'
    second,files=feed(2,rows,first)
    cache.sync(second,files.__getitem__)
    result=cache.resolve('G1','2026-10-04')
    assert result['duration_minutes']==55
    assert result['distance_km'] is None


def test_enumeration_only_has_endpoints_and_prefers_detailed_history(initial):
    cache,rows,first,_=initial
    sparse=version('sparse',['2026-10-05']);sparse['s']=[]
    rows['train:G1']['versions'].append(sparse)
    rows['train:1234']={'code':'1234','versions':[sparse]}
    second,files=feed(2,rows,first);cache.sync(second,files.__getitem__)
    assert cache.resolve('G1','2026-10-05')['matched_date']=='2026-10-03'
    result=cache.resolve('1234','2026-10-05')
    assert result['departure_station']=='新站' and result['arrival_station']=='终点'
    assert result['duration_minutes'] is None and result['stops']==[]

def test_history_http_api_and_batch_stats_use_the_ticket_date(initial, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from railway.api import router, get_db
    cache,*_=initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB',str(cache.file))
    app=FastAPI();app.include_router(router,prefix='/railway')
    app.dependency_overrides[get_db]=lambda:None
    with TestClient(app) as client:
        response=client.get('/railway/history/trains',params={'train_code':'G1','query_date':'2025-01-01'})
        assert response.status_code==200 and response.json()['code']==0
        assert response.json()['data']['match']=='nearest'
        assert response.json()['data']['history_available'] is True
        assert client.get('/railway/history/trains',params={'train_code':'G1','query_date':'invalid'}).status_code==422
        assert client.get('/railway/history/stations',params={'name_or_code':'旧站'}).json()['data'][0]['telecode']=='AAA'
        result=client.post('/railway/stats/batch',json={'items':[{'id':'x','train_code':'G1','departure_station':'旧站',
                'arrival_station':'终点','date_time':'2026-10-01 12:00:00'}]}).json()
        assert result['data'][0]['duration_minutes']==70


def test_legacy_station_projection_preserves_ids_and_local_fields(initial, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from railway.db.models.models import Base, Station
    from railway.db import session
    from railway.history_sync import project_stations
    cache,*_=initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB',str(cache.file))
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    monkeypatch.setattr(session,'SessionLocal',sessions)
    with sessions() as db:
        extra = {'alias_names':['更早的站名']} if hasattr(Station,'alias_names') else {}
        db.add(Station(station_id=99,telecode='AAA',station_name='旧站',station_pinyin='old',station_py='o',city='本地市',province='本地省',**extra))
        db.commit()
    project_stations();project_stations()
    with sessions() as db:
        row=db.query(Station).filter_by(telecode='AAA').one()
        assert row.station_id==99 and row.station_name=='新站'
        if hasattr(Station,'alias_names'):
            assert set(row.alias_names)=={'旧站','更早的站名'}
        assert cache.stations('旧站')[0]['telecode']=='AAA'
        assert row.province=='本地省' and row.city=='本地市'
    engine.dispose()


def test_snapshot_fallback_after_missing_delta_keeps_existing_history(initial):
    cache,rows,first,_=initial
    rows['station:CCC']=station('CCC','新增',30,120)
    third,files=feed(3,rows)
    cache.sync(third,files.__getitem__)
    assert cache.status()['sequence']==3 and cache.status()['stations']==3
    assert cache.resolve('G1','2026-10-01')['version']=='A'

def test_scheduled_sync_skips_packages_and_projection_when_unchanged(initial, monkeypatch):
    from railway import history_cache, history_sync, initialization
    cache,_,manifest,files=initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB',str(cache.file))
    monkeypatch.setattr(initialization,'wait_for_initialization',lambda:None)
    def fetch(**kwargs):
        return kwargs['cache'].sync(manifest,lambda _:pytest.fail('unchanged feed downloaded a pack'))
    monkeypatch.setattr(history_cache,'fetch_feed',fetch)
    projections=[]
    monkeypatch.setattr(history_sync,'project_stations',lambda:projections.append(True))
    history_sync.sync_history()
    assert cache.projected_sequence()==1 and len(projections)==1
    before=cache.file.read_bytes()
    history_sync.sync_history()
    assert len(projections)==1 and cache.file.read_bytes()==before


def test_scheduled_sync_retries_failed_projection_and_applies_next_version(initial, monkeypatch):
    from railway import history_cache, history_sync, initialization
    cache,rows,first,_=initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB',str(cache.file))
    monkeypatch.setattr(initialization,'wait_for_initialization',lambda:None)
    manifest=first
    available={}
    def fetch(**kwargs):
        return kwargs['cache'].sync(manifest,available.__getitem__)
    monkeypatch.setattr(history_cache,'fetch_feed',fetch)
    def fail():raise RuntimeError('projection interrupted')
    monkeypatch.setattr(history_sync,'project_stations',fail)
    history_sync.sync_history()
    assert cache.status()['sequence']==1 and cache.projected_sequence()==0
    calls=[]
    monkeypatch.setattr(history_sync,'project_stations',lambda:calls.append(True))
    history_sync.sync_history()
    rows['station:CCC']=station('CCC','更新站',30,120)
    manifest,available=feed(2,rows,first)
    history_sync.sync_history()
    assert len(calls)==2 and cache.projected_sequence()==2 and cache.stations('CCC')


def test_history_sync_registers_daily_with_startup_check_and_can_be_disabled(monkeypatch):
    from railway.history_sync import register_history_sync
    from unittest.mock import Mock
    from datetime import datetime, timezone
    scheduler=Mock();before=datetime.now(timezone.utc)
    monkeypatch.delenv('RAILWAY_HISTORY_SYNC_SECONDS',raising=False)
    monkeypatch.delenv('RAILWAY_HISTORY_SYNC_ENABLED',raising=False)
    register_history_sync(scheduler)
    kwargs=scheduler.register_interval_job.call_args.kwargs
    assert kwargs['seconds']==86400
    assert 59 <= (kwargs['next_run_time']-before).total_seconds() <= 62
    scheduler.reset_mock();monkeypatch.setenv('RAILWAY_HISTORY_SYNC_ENABLED','0')
    monkeypatch.setenv('RAILWAY_COORDINATE_SYNC_ENABLED','0')
    register_history_sync(scheduler)
    scheduler.register_interval_job.assert_not_called()


def test_fetch_feed_retries_and_switches_github_mirrors(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from railway import history_cache

    cache = HistoryCache(tmp_path / 'history.sqlite')
    manifest, files = feed(1, {'station:AAA': station('AAA', '新站', 39.9, 116.4)})
    responses = [OSError('mirror unavailable'), json.dumps(manifest).encode(), next(iter(files.values()))]
    requested = []

    @contextmanager
    def fake_urlopen(url, timeout):
        requested.append(url)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        yield type('Response', (), {'read': lambda _self, _size: value})()

    monkeypatch.setattr(history_cache, 'urlopen', fake_urlopen)
    result = history_cache.fetch_feed(cache=cache)

    assert result['sequence'] == 1
    assert cache.status()['stations'] == 1
    assert requested[0].startswith('https://gh-proxy.com/https://raw.githubusercontent.com/')
    assert requested[1].startswith('https://gh-proxy.at9.net/https://raw.githubusercontent.com/')
    assert requested[2].startswith('https://gh-proxy.com/https://raw.githubusercontent.com/')
def test_rename_and_new_station_delta_keeps_old_train_and_station_names(initial):
    cache, rows, first, _ = initial
    desc, data = pack(2, {
        'station:AAA': station('AAA', '又改名', 39.9, 116.4),
        'station:CCC': station('CCC', '新增站', 30, 120),
        'train:G1': {'code': 'G1', 'versions': [version('C', ['2026-10-05'])]},
    })
    cache.sync(dict(first, sequence=2, deltas=first['deltas'] + [desc]), lambda _: data)
    assert cache.stations('旧站')[0]['telecode'] == 'AAA'
    assert cache.stations('新增站')[0]['telecode'] == 'CCC'
    old = cache.resolve('G1', '2026-10-01', ' 旧站站 ', '终点站')
    assert old['match'] == 'exact' and old['version'] == 'A'
    assert old['stops'][0]['n'] == '新站'
    assert cache.resolve('G1', '2026-10-05', '又改名', '终点')['version'] == 'C'


def test_projection_keeps_name_only_present_in_local_seed(initial):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from railway.db.models.models import Base, Station
    from railway.history_sync import project_stations
    cache, *_ = initial
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(Station(telecode='AAA', station_name='种子旧名称', station_pinyin='', station_py='', city=''))
        db.commit()
    project_stations(cache=cache, sessions=sessions)
    project_stations(cache=cache, sessions=sessions)
    assert cache.stations('种子旧名称')[0]['telecode'] == 'AAA'
    assert len(cache.resolve('G1', '2026-10-01', '种子旧名称站', '终点')['stops']) == 2
    engine.dispose()


def test_offline_seed_upgrades_without_network_or_rollback(initial, tmp_path):
    from railway.history_seed import import_history_seed
    cache, rows, first, files = initial
    directory = tmp_path / 'bundle'
    def write_bundle(manifest, available):
        directory.mkdir(exist_ok=True)
        (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        for name, raw in available.items():
            target = directory / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(raw)
    write_bundle(first, files)
    fresh = HistoryCache(tmp_path / 'fresh.sqlite')
    import_history_seed(fresh, directory)
    before = fresh.file.read_bytes()
    import_history_seed(fresh, directory)
    assert fresh.file.read_bytes() == before
    assert fresh.resolve('G1', '2026-10-02')['version'] == 'B'
    rows['station:CCC'] = station('CCC', '新增', 30, 120)
    third, available = feed(3, rows)
    write_bundle(third, available)
    import_history_seed(fresh, directory)
    assert fresh.status()['sequence'] == 3 and fresh.stations('CCC')
    write_bundle(first, files)
    import_history_seed(fresh, directory)
    assert fresh.status()['sequence'] == 3


def test_bundle_update_validates_before_replacing_manifest(initial, tmp_path, monkeypatch):
    from railway import history_cache
    from railway.history_seed import update_history_seed
    _, rows, first, files = initial
    directory = tmp_path / 'bundle'
    monkeypatch.setattr(history_cache, 'read_feed', lambda: (first, files.__getitem__))
    assert update_history_seed(directory)['sequence'] == 1
    before = (directory / 'manifest.json').read_bytes()
    second, available = feed(2, rows)
    monkeypatch.setattr(history_cache, 'read_feed', lambda: (second, lambda _: b'corrupt'))
    with pytest.raises(ValueError, match='checksum'):
        update_history_seed(directory)
    assert (directory / 'manifest.json').read_bytes() == before


def test_release_seed_is_valid_and_has_dated_details(initial, tmp_path, monkeypatch):
    from railway import history_cache
    from railway.history_seed import import_history_seed
    _, _, manifest, files = initial
    monkeypatch.setattr(history_cache, 'read_feed', lambda: (manifest, files.__getitem__))
    cache = HistoryCache(tmp_path / 'bundled.sqlite')
    result = import_history_seed(cache)
    assert result['stations'] > 0 and result['trains'] > 0
    result = cache.resolve('G1', '2026-10-02')
    assert result['match'] == 'exact' and len(result['stops']) > 2


@pytest.mark.asyncio
async def test_ticket_enrichment_matches_old_name_and_keeps_ticket_text(initial, monkeypatch):
    from types import SimpleNamespace
    from app.service.tasks import tickets
    cache, *_ = initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB', str(cache.file))
    ticket = SimpleNamespace(train_code='G1', date_time='2026-10-02 23:50:00',
                             departure_station='旧站站', arrival_station='终点')
    result = await tickets.calculate_ticket_mileage_and_time(ticket)
    assert result['total_time'] == 70
    assert result['stop_stations'][0]['station_telecode'] == 'AAA'
    assert ticket.departure_station == '旧站站'


@pytest.mark.parametrize('old_sequence', [0, 99])
def test_offline_startup_projects_before_ready(tmp_path, monkeypatch, old_sequence):
    from urllib import request
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from railway import initialization
    from railway.db import session, dependencies
    from railway.db.models.models import Base, Station, Train, TrainSchedule
    from app.core import paths
    from railway import history_cache
    manifest, files = feed(1, {'station:AAA': station('AAA', '离线种子站', 39, 116)})
    monkeypatch.setattr(history_cache, 'read_feed', lambda: (manifest, files.__getitem__))
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(session, 'SessionLocal', sessions)
    monkeypatch.setattr(dependencies, 'engine', engine)
    monkeypatch.setenv('RAILWAY_DB_URL', 'sqlite:///:memory:')
    monkeypatch.setattr(paths, 'DATA_DIR', str(tmp_path))
    monkeypatch.setenv('RAILWAY_HISTORY_DB', str(tmp_path / 'offline.sqlite'))
    if old_sequence:
        old_cache = HistoryCache(tmp_path / 'offline.sqlite')
        with old_cache.connect() as db:
            old_cache._upsert(db, 'station:AAA', station('AAA', '旧库保留站', 39, 116))
            db.execute("INSERT INTO meta VALUES ('sequence', ?)", (str(old_sequence),))
        old_cache.mark_projected(old_sequence)
    monkeypatch.setattr(request, 'urlopen', lambda *a, **kw: pytest.fail('mocked Release seed attempted network access'))
    monkeypatch.setattr(initialization, '_state', 'pending')
    initialization._initialize()
    initialization.require_ready()
    cache = HistoryCache(tmp_path / 'offline.sqlite')
    assert cache.status()['schema_version'] == 2
    if old_sequence:
        assert cache.stations('旧库保留站')
    assert cache.projected_sequence() == cache.status()['sequence'] > 0
    with sessions() as db:
        assert db.query(Station).count() >= 3404
        assert db.query(Train).count() == db.query(TrainSchedule).count() == 0
        beijing = db.query(Station).filter_by(telecode='VAP').one()
        assert beijing.province == '北京市' and beijing.station_pinyin == 'beijingbei'
        assert db.query(Station).filter_by(telecode='BJB').one().station_name == '滨江'
    engine.dispose()


def test_legacy_read_endpoints_use_history_without_relational_timetables(initial, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from railway.api import router, get_db
    cache, *_ = initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB', str(cache.file))
    app = FastAPI()
    app.include_router(router, prefix='/railway')
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        params = {'train_code': 'G1', 'query_date': '2026-10-02'}
        listing = client.get('/railway/trains', params=dict(params, from_station='旧站')).json()
        assert listing['code'] == 0 and listing['data']['total'] == 1
        assert listing['data']['list'][0]['matched_date'] == '2026-10-02'
        single = client.get('/railway/trains/single', params=params).json()
        assert single['data']['train_no'] == '1234'
        schedules = client.get('/railway/train-schedules', params=dict(params, page_size=1, page=2)).json()
        assert schedules['code'] == 0 and schedules['data']['total'] == 2
        assert schedules['data']['list'][0]['station_name'] == '终点'
        alias = client.get('/railway/train-schedules', params=dict(params, station_name='旧站')).json()
        assert alias['data']['total'] == 1 and alias['data']['list'][0]['sequence'] == 1
        full = client.get('/railway/train-schedules/full/1234', params={'query_date':'2026-10-02'}).json()
        assert len(full['data']) == 2
        by_date = client.get('/railway/trains/G1/schedules', params={'query_date':'2026-09-20'}).json()
        assert by_date['data'][0]['match'] == 'nearest'
        assert by_date['data'][0]['matched_date'] == '2026-10-01'


def test_station_projection_rebuilds_search_and_preserves_local_metadata(initial, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from railway.db.models.models import Base, Station
    from railway.history_sync import project_stations
    from railway.crud import get_station_list, get_station_single
    from railway.schemas import StationListQuery, StationSingleQuery
    cache, *_ = initial
    monkeypatch.setenv('RAILWAY_HISTORY_DB', str(cache.file))
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    metadata = {'AAA': {'names':['更早站名'], 'province':'补充省', 'city':'测试市', 'district':'测试区'},
                'CCC': {'names':['保留旧站'], 'province':'补充省', 'city':'测试市', 'pinyin':'baoliu', 'pinyin_short':'bl'}}
    with sessions() as db:
        db.add(Station(station_id=99, telecode='AAA', station_name='本地名称', station_pinyin='', station_py='',
                       city='', province='用户省份'))
        db.commit()
    project_stations(cache=cache, sessions=sessions, metadata=metadata)
    project_stations(cache=cache, sessions=sessions, metadata=metadata)
    with sessions() as db:
        row = db.query(Station).filter_by(telecode='AAA').one()
        assert row.station_id == 99 and row.province == '用户省份' and row.district == '测试区'
        code, _, data = get_station_list(db, StationListQuery(keyword='更早站名'))
        assert code == 200 and data['total'] == 1
        assert get_station_single(db, StationSingleQuery(station_name='更早站名站'))[2].telecode == 'AAA'
        assert get_station_list(db, StationListQuery(keyword='baoliu'))[2]['total'] == 1
        db.query(Station).delete()
        db.commit()
    project_stations(cache=cache, sessions=sessions, metadata=metadata)
    with sessions() as db:
        assert db.query(Station).count() == 3
    engine.dispose()


def legacy_v1_sync(cache, manifest, files):
    """Frozen v1 reader contract: accepts whole-entity packs, has no feed_schema."""
    if manifest['schema_version'] != 1:
        raise ValueError('Unsupported railway feed schema')
    descriptor = manifest['snapshot']
    raw = files[descriptor['file']]
    assert hashlib.sha256(raw).hexdigest() == descriptor['sha256']
    payload = json.loads(gzip.decompress(raw))
    with cache.connect() as db:
        for item in payload['upserts']:
            cache._upsert(db, item['key'], item['value'])
        db.execute("INSERT OR REPLACE INTO meta VALUES ('sequence', ?)", (str(payload['sequence']),))


def legacy_cache(tmp_path, rows, sequence):
    cache = HistoryCache(tmp_path / 'legacy.sqlite')
    raw = gzip.compress(json.dumps({'schema_version':1, 'sequence':sequence, 'full':True,
        'upserts':[{'key':key, 'value':value} for key,value in rows.items()]}).encode())
    digest = hashlib.sha256(raw).hexdigest()
    descriptor = {'sequence':sequence,'file':f'packs/{digest}.json.gz','bytes':len(raw),'sha256':digest}
    legacy_v1_sync(cache, {'schema_version':1,'snapshot':descriptor}, {descriptor['file']:raw})
    return cache


@pytest.mark.parametrize('old_sequence', [1, 99])
def test_v1_failure_then_automatic_v2_upgrade_independent_of_cursor(initial, tmp_path, old_sequence):
    _, rows, manifest, files = initial
    old = legacy_cache(tmp_path, rows, old_sequence)
    old.mark_projected(old_sequence)
    old.store_coordinates('AAA', 39, 116, 'user', 'WGS84')
    with pytest.raises(ValueError, match='schema'):
        legacy_v1_sync(old, manifest, files)
    assert old.resolve('G1', '2026-10-02')['version'] == 'B'
    assert old.status()['sequence'] == old_sequence
    before = old.file.read_bytes()
    with pytest.raises(ValueError, match='checksum'):
        old.sync(manifest, lambda _: b'corrupt')
    assert old.file.read_bytes() == before
    assert old.projected_sequence() == old_sequence
    requested = []
    def load(file):
        requested.append(file)
        return files[file]
    upgraded = HistoryCache(old.file)
    upgraded.sync(manifest, load)
    assert requested == [manifest['snapshot']['file']]
    assert upgraded.status()['schema_version'] == 2 and upgraded.status()['sequence'] == 1
    assert upgraded.projected_sequence() == 0
    assert upgraded.local_coordinates('AAA')[:2] == (39, 116)
    assert upgraded.stations('旧站')
    assert upgraded.resolve('G1', '2026-10-02')['match'] == 'exact'
    upgraded.sync(manifest, lambda _: pytest.fail('already upgraded'))


def test_upgrade_rolls_back_late_import_failure_and_preserves_local_history(initial, tmp_path):
    _, rows, _, _ = initial
    old = legacy_cache(tmp_path, rows, 88)
    old.mark_projected(88)
    desc, data = v2pack(1, [station('CCC','新增',30,120)], observations=[
        {'code':'missing','hash':'x','dates':['2026-10-04']}], full=True)
    manifest = {'schema_version':2,'sequence':1,'snapshot':desc,'deltas':[]}
    before = old.file.read_bytes()
    with pytest.raises(ValueError, match='missing'):
        old.sync(manifest, lambda _: data)
    assert old.file.read_bytes() == before and old.projected_sequence() == 88
    # A valid complete feed may be older than locally retained observations.
    valid, available = feed(1, {'station:CCC':station('CCC','新增',30,120)})
    old.sync(valid, available.__getitem__)
    assert old.stations('CCC') and old.resolve('G1','2026-10-02')['version'] == 'B'


def test_date_only_v2_delta_has_exact_observation_and_no_repeated_content(initial):
    cache, _, first, _ = initial
    desc, data = v2pack(2, observations=[{'code':'G1','hash':'A','dates':['2026-10-10']}])
    manifest = dict(first, sequence=2, snapshot=dict(first['snapshot'], sequence=2), deltas=[desc])
    with cache.connect() as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM train_version')]
    cache.sync(manifest, lambda _: data)
    result = cache.resolve('G1','2026-10-10')
    assert result['match'] == 'exact' and result['version'] == 'A'
    assert cache.resolve('G1','2026-10-09')['match'] == 'nearest'
    with cache.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM train_version')] == before
    cache.sync(manifest, lambda _: pytest.fail('duplicate download'))


def test_offline_v2_seed_migrates_higher_v1_cursor(initial, tmp_path):
    from railway.history_seed import import_history_seed
    _, rows, manifest, files = initial
    old = legacy_cache(tmp_path, rows, 900)
    directory = tmp_path / 'v2-bundle'
    directory.mkdir()
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    for file, raw in files.items():
        target = directory / file
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
    import_history_seed(old, directory)
    assert old.status()['schema_version'] == 2 and old.status()['sequence'] == 1
    assert old.resolve('G1','2026-10-03')['match'] == 'exact'


def test_many_deltas_choose_smaller_snapshot_and_keep_history(initial):
    cache, rows, first, _ = initial
    manifest, files = feed(4, rows)
    manifest['deltas'] = [dict(manifest['snapshot'], sequence=i) for i in (2,3,4)]
    calls = []
    def load(file):
        calls.append(file)
        return files[file]
    cache.sync(manifest, load)
    assert calls == [manifest['snapshot']['file']]
    assert cache.status()['sequence'] == 4
    assert cache.resolve('G1','2026-10-01')['match'] == 'exact'


def test_collector_v2_history_replay(tmp_path):
    """Optional cross-repository audit of actual TS packs against retained v1 history."""
    import os
    from pathlib import Path
    report_path = os.getenv('RAILWAY_V2_REPLAY_REPORT')
    if not report_path:
        pytest.skip('set RAILWAY_V2_REPLAY_REPORT to a collector replay report')
    report_path = Path(report_path)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    source = Path(report['repository']) / 'data' / 'feed'
    cache = None
    results = []
    for item in report['rows']:
        retained = json.loads(gzip.decompress((source / item['old_snapshot']).read_bytes()))
        rows = {row['key']:row['value'] for row in retained['upserts']}
        if cache is None:
            cache = legacy_cache(tmp_path, rows, 999)
            cache.mark_projected(999)
        manifest = json.loads((report_path.parent / f"manifest-{item['sequence']}.json").read_text(encoding='utf-8'))
        loaded = []
        def load(file):
            loaded.append(file)
            directory = report['snapshots'] if file == manifest['snapshot']['file'] else report['feed']
            return (Path(directory) / file).read_bytes()
        cache.sync(manifest, load)
        assert cache.status()['schema_version'] == 2
        expected_observations = set()
        expected_versions = 0
        with cache.connect() as db:
            for key, value in rows.items():
                if key.startswith('station:'):
                    assert json.loads(db.execute('SELECT body FROM entity WHERE key=?', (key,)).fetchone()[0]) == value
                else:
                    for v in value['versions']:
                        expected_versions += 1
                        actual = json.loads(db.execute('SELECT body FROM train_version WHERE code=? AND hash=?', (value['code'],v['h'])).fetchone()[0])
                        expected = {k:x for k,x in v.items() if k not in ('dates','fd','ld','observed_at')}
                        assert actual == expected
                        for day in v.get('dates') or [v['fd'],v['ld']]:
                            expected_observations.add((value['code'],day,v['h']))
            assert {tuple(row) for row in db.execute('SELECT * FROM observation')} == expected_observations
            assert db.execute('SELECT count(*) FROM train_version').fetchone()[0] == expected_versions
        cache.sync(manifest, lambda _: pytest.fail('replay repeat downloaded data'))
        results.append({'sequence':item['sequence'],'versions':expected_versions,'observations':len(expected_observations),'downloaded':loaded})
    (report_path.parent / 'client-validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


def release_manifest(manifest):
    snapshot = manifest['snapshot']
    digest = snapshot['sha256']
    snapshot['url'] = ('https://github.com/LC044/trailsnap-railway-history/releases/download/'
                       f'snapshot-v2-{digest}/{digest}.json.gz')
    return manifest


def test_release_snapshot_uses_mirrors_then_origin_and_delta_stays_in_git(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from railway import history_cache
    cache = HistoryCache(tmp_path / 'release.sqlite')
    rows = {'station:AAA':station('AAA','新站',39,116),
            'train:G1':{'code':'G1','versions':[version('A',['2026-10-01'])]}}
    manifest, files = feed(1, rows)
    release_manifest(manifest)
    requested = []
    @contextmanager
    def fake_urlopen(url, timeout):
        requested.append(url)
        if url.endswith('/manifest.json'):
            raw = json.dumps(manifest).encode()
        elif '/releases/download/' in url:
            if not url.startswith('https://github.com/'):
                raise OSError('release mirror unavailable')
            raw = files[manifest['snapshot']['file']]
        else:
            raw = next(value for name,value in files.items() if url.endswith(name))
        yield type('Response', (), {'read':lambda _self,_size:raw})()
    monkeypatch.setattr(history_cache, 'urlopen', fake_urlopen)
    history_cache.fetch_feed(cache=cache)
    assert any(url.startswith('https://github.com/') for url in requested)
    assert len([url for url in requested if '/releases/download/' in url]) == 3
    assert not any('/data/feed/packs/' in url for url in requested)
    assert cache.resolve('G1','2026-10-01')['match'] == 'exact'
    requested.clear()
    history_cache.fetch_feed(cache=cache)
    assert len(requested) == 1 and requested[0].endswith('/manifest.json')
    delta, raw = pack(2, {'station:BBB':station('BBB','新增站',30,120)})
    full, full_files = feed(2, dict(rows, **{'station:BBB':station('BBB','新增站',30,120)}))
    manifest = release_manifest(dict(full, deltas=[delta]))
    files = {**full_files, delta['file']:raw}
    requested.clear()
    history_cache.fetch_feed(cache=cache)
    assert cache.status()['sequence'] == 2 and cache.stations('BBB')
    assert any(url.endswith('/data/feed/' + delta['file']) for url in requested)
    assert not any('/releases/download/' in url for url in requested)


@pytest.mark.parametrize('url', ['http://github.com/invalid', 'https://example.com/asset',
    'https://github.com/LC044/trailsnap-railway-history/releases/download/latest/asset.json.gz'])
def test_untrusted_release_url_is_rejected_before_asset_download(initial, monkeypatch, url):
    from contextlib import contextmanager
    from railway import history_cache
    cache, rows, _, _ = initial
    manifest, _ = feed(2, rows)
    manifest['snapshot']['url'] = url
    requested = []
    @contextmanager
    def fake_urlopen(address, timeout):
        requested.append(address)
        assert address.endswith('/manifest.json')
        yield type('Response', (), {'read':lambda _self,_size:json.dumps(manifest).encode()})()
    monkeypatch.setattr(history_cache, 'urlopen', fake_urlopen)
    before = cache.file.read_bytes()
    with pytest.raises(ValueError, match='Release snapshot URL'):
        history_cache.fetch_feed(cache=cache)
    assert len(requested) == 1 and cache.file.read_bytes() == before


def test_release_corruption_then_retry_migrates_v1_and_bundle_stays_offline(initial, tmp_path, monkeypatch):
    from contextlib import contextmanager
    from railway import history_cache, history_seed
    _, rows, manifest, files = initial
    release_manifest(manifest)
    old = legacy_cache(tmp_path, rows, 99)
    corrupt = True
    @contextmanager
    def fake_urlopen(url, timeout):
        if url.endswith('/manifest.json'):
            raw = json.dumps(manifest).encode()
        else:
            assert '/releases/download/' in url
            raw = b'corrupt' if corrupt else files[manifest['snapshot']['file']]
        yield type('Response', (), {'read':lambda _self,_size:raw})()
    monkeypatch.setattr(history_cache, 'urlopen', fake_urlopen)
    before = old.file.read_bytes()
    with pytest.raises(ValueError, match='checksum'):
        history_cache.fetch_feed(cache=old)
    assert old.file.read_bytes() == before
    corrupt = False
    history_cache.fetch_feed(cache=old)
    assert old.status()['sequence'] == 1 and old.status()['schema_version'] == 2
    directory = tmp_path / 'release-bundle'
    history_seed.update_history_seed(directory)
    assert (directory / manifest['snapshot']['file']).exists()
    monkeypatch.setattr(history_cache, 'urlopen', lambda *a,**kw:pytest.fail('offline seed accessed Release'))
    fresh = HistoryCache(tmp_path / 'offline-release.sqlite')
    history_seed.import_history_seed(fresh, directory)
    assert fresh.resolve('G1','2026-10-02')['version'] == 'B'
