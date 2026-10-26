"""Consolidated index upgrades retain data and accept local prototype revisions."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy import Enum
from sqlalchemy.orm import Session

pytestmark = [pytest.mark.smoke, pytest.mark.module_location]
ROOT = Path(__file__).parents[2]


def test_consolidated_sqlite_upgrade_accepts_local_intermediate_revision(tmp_path, monkeypatch):
    url='sqlite:///'+(tmp_path/'local-prototype.sqlite').as_posix()
    monkeypatch.setenv('TS_DB_URL',url)
    config=Config()
    config.set_main_option('script_location',str(ROOT/'alembic_sqlite'))
    config.set_main_option('sqlalchemy.url',url)
    command.upgrade(config,'portable_sqlite_0020')
    engine=create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE INDEX ix_photos_owner_deleted_time_id ON photos(owner_id,is_deleted,photo_time,id)')
            connection.exec_driver_sql("CREATE INDEX ix_tasks_pending_error_type ON tasks(type,status) WHERE status='pending' AND error IS NOT NULL")
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='d82e5a031b42'")
            connection.execute(text("INSERT INTO photos(id,filename,file_path,file_type,is_deleted) VALUES (:id,'retained.jpg','/original/retained.jpg','image',0)"),{'id':str(uuid4())})
        command.upgrade(config,'head')
        command.upgrade(config,'head')
        with engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()=='e205c1a0b002'
            assert connection.exec_driver_sql('SELECT filename,file_path FROM photos').one()==('retained.jpg','/original/retained.jpg')
            assert 'ix_photo_metadata_location_summary' in {i['name'] for i in inspect(connection).get_indexes('photo_metadata')}
        command.downgrade(config,'portable_sqlite_0020')
        assert 'ix_photos_owner_deleted_time_id' not in {i['name'] for i in inspect(engine).get_indexes('photos')}
    finally:
        engine.dispose()


def test_revision_compatibility_does_not_rewrite_unknown_versions():
    from app.db.migration_compat import normalize_local_index_revision
    engine=create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            normalize_local_index_revision(connection,'d82e5a031b42','portable_sqlite_0020')
            connection.exec_driver_sql('CREATE TABLE alembic_version (version_num varchar(50))')
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('unknown')")
            normalize_local_index_revision(connection,'d82e5a031b42','portable_sqlite_0020')
            assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()=='unknown'
    finally:
        engine.dispose()


def exercise(connection, folder, filename):
    spec = importlib.util.spec_from_file_location('summary_migration', ROOT/folder/'versions'/filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection.exec_driver_sql('CREATE TABLE photo_metadata (photo_id varchar(36) PRIMARY KEY, province varchar(100), city varchar(100), district varchar(100), country varchar(100), scene_id varchar(36), latitude numeric, longitude numeric, exif_info text)')
    connection.exec_driver_sql('CREATE INDEX preceding_city_index ON photo_metadata(city)')
    connection.exec_driver_sql('CREATE TABLE photos (id varchar(36), owner_id varchar(36), is_deleted boolean, photo_time timestamp)')
    connection.exec_driver_sql('CREATE TABLE tasks (type varchar(50), status varchar(20), error text, priority integer, created_at timestamp)')
    connection.exec_driver_sql('CREATE INDEX ix_tasks_type_status ON tasks(type,status)')
    connection.exec_driver_sql('CREATE INDEX ix_tasks_type_status_priority_created ON tasks(type,status,priority,created_at)')
    connection.exec_driver_sql('CREATE INDEX ix_tasks_status_priority_created ON tasks(status,priority,created_at)')
    connection.execute(text('INSERT INTO photo_metadata(photo_id,city,exif_info) VALUES (:id,:city,:exif)'), dict(id=str(uuid4()),city='城市',exif='x'*100000))
    with Operations.context(MigrationContext.configure(connection)):
        for _ in range(2):
            migration.upgrade()
            indexes = {row['name']:row for row in inspect(connection).get_indexes('photo_metadata')}
            assert indexes['ix_photo_metadata_location_summary']['column_names'] == ['photo_id','province','city','district','country','scene_id','latitude','longitude']
            assert connection.execute(text('SELECT city,length(exif_info) FROM photo_metadata')).one() == ('城市',100000)
            migration.downgrade()
            assert {row['name'] for row in inspect(connection).get_indexes('photo_metadata')} == {'preceding_city_index'}


def test_location_summary_sqlite_upgrade_downgrade():
    engine=create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            exercise(connection,'alembic_sqlite','b54833411649_cover_location_summary_queries.py')
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_location_summary_postgres_upgrade_downgrade(request):
    if 'postgres' not in request.config.getoption('markexpr'):
        pytest.skip('Select postgres explicitly to use the test server')
    url=os.environ.get('TS_DB_URL') or os.environ.get('DB_URL','')
    if not url.startswith('postgresql'):
        pytest.skip('PostgreSQL test server required')
    engine=create_engine(url,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                schema='location_index_'+uuid4().hex
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                exercise(connection,'alembic','3b51634972a4_cover_location_summary_queries.py')
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_location_queries_execute_on_postgres(request):
    if 'postgres' not in request.config.getoption('markexpr'):
        pytest.skip('Select postgres explicitly to use the test server')
    url=os.environ.get('TS_DB_URL') or os.environ.get('DB_URL','')
    if not url.startswith('postgresql'):
        pytest.skip('PostgreSQL test server required')
    from app.crud.location import get_locations, get_location_statistics, get_location_years
    from app.db.models.photo import Photo, FileType
    from app.db.models.photo_metadata import PhotoMetadata
    from app.db.models.scene import Scene
    from datetime import datetime
    engine=create_engine(url,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                schema='location_query_'+uuid4().hex
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                # Only the three queried tables are needed. Avoid shared enums
                # and foreign keys into the real test database's user tables.
                for model in (Photo, PhotoMetadata, Scene):
                    columns=', '.join('"'+col.name+'" '+('TEXT' if isinstance(col.type,Enum) else str(col.type.compile(dialect=connection.dialect))) for col in model.__table__.columns)
                    connection.exec_driver_sql(f'CREATE TABLE "{model.__tablename__}" ({columns})')
                owner, other, scene_id=uuid4(),uuid4(),uuid4()
                with Session(bind=connection) as db:
                    db.add(Scene(id=scene_id,name='景区',is_custom=True))
                    latest=None
                    for user, deleted, month in [(owner,False,1),(owner,False,2),(owner,True,3),(other,False,4)]:
                        latest_id=uuid4()
                        db.add(Photo(id=latest_id,owner_id=user,filename='photo.jpg',file_path='/isolated/photo.jpg',file_type=FileType.image,photo_time=datetime(2024,month,1),is_deleted=deleted,size=1))
                        db.add(PhotoMetadata(photo_id=latest_id,city='城市',province='省',district='区',country='国家',scene_id=scene_id))
                        if user==owner and not deleted: latest=latest_id
                    db.flush()
                    for level in ('city','province','district','scene'):
                        rows=get_locations(db,owner,level)
                        assert len(rows)==1 and rows[0]['count']==2
                        assert rows[0]['cover'].id==latest
                    filtered=get_locations(db,owner,start_date='2024-01-01',end_date='2024-01-31')
                    assert len(filtered)==1 and filtered[0]['count']==1
                    assert get_location_statistics(db,owner)==dict(province_count=1,city_count=1,district_count=1,country_count=1)
                    assert get_location_years(db,owner)==[2024]
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
