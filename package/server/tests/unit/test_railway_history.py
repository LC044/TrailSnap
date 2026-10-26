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
    data=gzip.compress(json.dumps({'schema_version':1,'sequence':sequence,'full':full,
                                  'upserts':[{'key':k,'value':v} for k,v in rows.items()]}).encode())
    sha=hashlib.sha256(data).hexdigest()
    return {'sequence':sequence,'file':f'packs/{sha}.json.gz','bytes':len(data),'sha256':sha}, data


def feed(sequence, rows, previous=None):
    descriptor,data=pack(sequence,rows,True)
    return {'schema_version':1,'sequence':sequence,'snapshot':descriptor,
            'deltas':([*previous['deltas'],descriptor] if previous else [descriptor])}, {descriptor['file']:data}


@pytest.fixture
def initial(tmp_path, monkeypatch):
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
    manifest={'schema_version':1,'sequence':2,'snapshot':desc,'deltas':first['deltas']+[desc]}
    calls=[]
    def load(file): calls.append(file);return data
    cache.sync(manifest,load)
    assert cache.status()['sequence']==2 and cache.status()['stations']==3
    assert calls==[desc['file']]
    cache.sync(manifest,lambda _:pytest.fail('duplicate sync downloaded data'))
    assert cache.status()['versions']==2


def test_checksum_or_mid_transaction_failure_cannot_advance_cursor(initial):
    cache,_,first,_=initial
    desc,data=pack(2,{'station:CCC':station('CCC','新建站',30,115),'invalid:bad':{}})
    manifest={'schema_version':1,'sequence':2,'snapshot':desc,'deltas':first['deltas']+[desc]}
    with pytest.raises(ValueError,match='checksum'):
        cache.sync(manifest,lambda _:data+b'bad')
    with pytest.raises(ValueError,match='Unknown'):
        cache.sync(manifest,lambda _:data)
    assert cache.status()['sequence']==1 and not cache.stations('CCC')


def test_unknown_schema_rollback_and_unsafe_path_refused(initial):
    cache,_,manifest,_=initial
    with pytest.raises(ValueError,match='schema'):
        cache.sync(dict(manifest,schema_version=2),lambda _:b'')
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
