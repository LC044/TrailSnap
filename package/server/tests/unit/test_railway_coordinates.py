"""Coordinate persistence, safe matching and migration regressions."""
import json
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from railway.coordinates import TiandituStationGeocoder, backfill_missing_coordinates
from railway.db.models.models import Base, Station
from railway.db.migrations import upgrade_railway_schema
from railway.history_cache import HistoryCache

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def database(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'railway.sqlite'))
    Base.metadata.create_all(engine)
    yield engine,sessionmaker(bind=engine),HistoryCache(tmp_path/'cache.sqlite')
    engine.dispose()


def test_old_and_fresh_database_migration_preserves_ids(database):
    engine,sessions,_=database
    # Reproduce a pre-coordinate station table without touching related tables.
    with engine.begin() as db:
        for column in ('latitude','longitude','coordinate_source','coordinate_system','coordinates_updated_at',
                       'coordinate_status','coordinate_lookup_at','coordinate_retry_after'):
            db.execute(text('ALTER TABLE station DROP COLUMN '+column))
        db.execute(text("INSERT INTO station (station_id,telecode,station_name,station_pinyin,station_py,city,is_high_speed,status) VALUES (42,'AAA','测试','','','',0,1)"))
    upgrade_railway_schema(engine);upgrade_railway_schema(engine)
    with sessions() as db:
        row=db.query(Station).one()
        assert row.station_id==42 and row.latitude is None
    fresh=create_engine('sqlite:///:memory:');Base.metadata.create_all(fresh)
    upgrade_railway_schema(fresh);upgrade_railway_schema(fresh)
    assert 'longitude' in {c['name'] for c in inspect(fresh).get_columns('station')}
    fresh.dispose()


def geocoder(pois=None,**payload):
    response=Mock(status_code=200,ok=True)
    response.json.return_value={'status':{'infocode':1000},'pois':pois or [],**payload}
    return TiandituStationGeocoder(['private-test-key'],request=Mock(return_value=response))


def test_exact_station_matching_rejects_centers_shops_and_ambiguity():
    good={'name':'广阳站','address':'河北省廊坊市','lonlat':'116.7,39.5'}
    assert geocoder([good]).lookup('广阳','廊坊')['latitude']==39.5
    assert geocoder(resultType=3,area={'lonlat':'116,39'}).lookup('广阳','廊坊')['status']=='not_found'
    assert geocoder([{**good,'name':'广阳站便利店'}]).lookup('广阳','廊坊')['status']=='not_found'
    assert geocoder([{**good,'address':'其他市'}]).lookup('广阳','廊坊')['status']=='not_found'
    assert geocoder([good,{**good,'lonlat':'115,38'}]).lookup('广阳','廊坊')['status']=='ambiguous'
    assert geocoder([{**good,'lonlat':'nan,39'}]).lookup('广阳','廊坊')['status']=='not_found'


def test_backfill_cached_skips_existing_and_defers_failures(database):
    _,sessions,cache=database
    with sessions() as db:
        db.add_all([Station(telecode=c,station_name='广阳',station_pinyin='',station_py='',city='廊坊',
                            latitude=30 if c=='AAA' else None,longitude=120 if c=='AAA' else None)
                    for c in ('AAA','BBB','CCC')]);db.commit()
    lookup=geocoder([{'name':'广阳站','address':'廊坊市','lonlat':'116.7,39.5'}])
    result=backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=lookup,sleep=lambda _:None)
    assert result['updated']==2 and lookup.request.call_count==2
    assert cache.distance('AAA','BBB')>0
    result=backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=lookup,sleep=lambda _:None)
    assert result['looked_up']==0
    with sessions() as db:
        assert float(db.query(Station).filter_by(telecode='AAA').one().latitude)==30
        row=db.query(Station).filter_by(telecode='BBB').one();row.latitude=None;db.commit()
    failed=geocoder()
    assert backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=failed,sleep=lambda _:None)['updated']==0
    assert backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=failed,sleep=lambda _:None)['looked_up']==0
    assert TiandituStationGeocoder([]).lookup('测试')['status']=='no_key'


def test_projection_persists_gps_and_read_schema(database):
    from railway.history_sync import project_stations
    from railway.schemas import StationRead
    _,sessions,cache=database
    with cache.connect() as db:
        cache._upsert(db,'station:AAA',{'telecode':'AAA','names':[{'name':'测试'}],'status':'active',
            'versions':[{'data':{'gps':{'latitude':'39.5','longitute':'116.7'}}}]})
    project_stations(cache=cache,sessions=sessions)
    with sessions() as db:
        row=db.query(Station).one()
        assert float(row.latitude)==39.5 and row.coordinate_source=='12306'
        assert StationRead.model_validate(row).model_dump()['longitude']==pytest.approx(116.7)
        row.latitude=40;row.coordinate_source='manual';db.commit()
    project_stations(cache=cache,sessions=sessions)
    assert cache.local_coordinates('AAA')[0]==40


def test_quota_error_stops_batch_without_secret_logging(database,caplog):
    _,sessions,cache=database
    with sessions() as db:
        db.add_all([Station(telecode=c,station_name='测试',station_pinyin='',station_py='',city='') for c in ('AAA','BBB')]);db.commit()
    lookup=geocoder(status={'infocode':1005,'cndesc':'超过配额'})
    result=backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=lookup,sleep=lambda _:None)
    assert result['status']=='rate_limited' and result['looked_up']==1
    assert 'private-test-key' not in caplog.text
    assert backfill_missing_coordinates(sessions=sessions,cache=cache,geocoder=TiandituStationGeocoder([]))['status']=='no_key'


def test_coordinate_scheduler_runs_when_feed_is_disabled(monkeypatch):
    from railway.history_sync import register_history_sync
    scheduler=Mock();monkeypatch.setenv('RAILWAY_HISTORY_SYNC_ENABLED','0')
    monkeypatch.delenv('RAILWAY_COORDINATE_SYNC_ENABLED',raising=False)
    register_history_sync(scheduler)
    assert scheduler.register_interval_job.call_args.args==('railway-coordinate-sync',)
    assert scheduler.register_interval_job.call_args.kwargs['seconds']==3600
