"""Nightly watch 2026-11-22 · app/crud/footprint.py::_visits / _sample_routes 盲区。

_visits 用窗口函数把照片序列切成「一次停留」，_sample_routes 再把停留之间的
移动边抽稀成有限的路线点。这两段 SQL 决定了足迹地图上的停留数与路线数，
一旦口径漂移，用户看到的轨迹就会凭空多出或少掉城市。

本文件覆盖：
- 同一城市、间隔小于 7 天 -> 合成一次停留（happy）
- 同一城市但间隔超过 7 天 -> 拆成两次停留（edge）
- 不同城市 -> 各自独立成停留（happy）
- 路线只连接不同城市且间隔在阈值内（happy）
- 同城不产生路线（edge）
- 路线数量超过 max_points 时被抽稀并标记截断（edge）
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.crud.footprint import _sample_routes, _source, _visits
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def footprint_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def owner():
    return uuid4()


@pytest.fixture
def photo(footprint_db, owner):
    def add(*, city="成都市", lat=30.67, lng=104.06, at="2024-01-01T12:00:00"):
        item = Photo(id=uuid4(), owner_id=owner, filename="footprint.jpg",
                     file_path="/isolated/footprint.jpg", file_type=FileType.image,
                     size=123, photo_time=datetime.fromisoformat(at))
        footprint_db.add(item)
        footprint_db.add(PhotoMetadata(photo_id=item.id, country="中国", province="四川省",
                                      city=city, district="", latitude=lat, longitude=lng))
        footprint_db.flush()
        return item
    return add


def _visits_of(db, owner_id):
    source = _source(db, owner_id, None)
    visits = _visits(db, source)
    return db.execute(select(visits).order_by(visits.c.visit_no)).mappings().all()


def test_visits_merge_photos_of_one_city_inside_the_gap(footprint_db, photo, owner):
    photo(at="2024-01-01T10:00:00")
    photo(at="2024-01-02T10:00:00")

    rows = _visits_of(footprint_db, owner)

    assert len(rows) == 1
    assert rows[0]["photo_count"] == 2


def test_visits_split_the_same_city_after_seven_days(footprint_db, photo, owner):
    photo(at="2024-01-01T10:00:00")
    photo(at="2024-01-15T10:00:00")

    rows = _visits_of(footprint_db, owner)

    assert len(rows) == 2
    assert {row["photo_count"] for row in rows} == {1}


def test_visits_keep_different_cities_apart(footprint_db, photo, owner):
    photo(city="成都市", at="2024-01-01T10:00:00")
    photo(city="重庆市", lat=29.56, lng=106.55, at="2024-01-01T11:00:00")

    rows = _visits_of(footprint_db, owner)

    assert len(rows) == 2
    assert {row["name"] for row in rows} == {"成都市", "重庆市"}


def test_routes_connect_two_different_cities(footprint_db, photo, owner):
    photo(city="成都市", lat=30.67, lng=104.06, at="2024-01-01T10:00:00")
    photo(city="重庆市", lat=29.56, lng=106.55, at="2024-01-01T11:00:00")

    source = _source(footprint_db, owner, None)
    routes, truncated = _sample_routes(footprint_db, _visits(footprint_db, source), 300)

    assert truncated is False
    assert len(routes) == 1
    assert routes[0]["from_name"] == "成都市"
    assert routes[0]["to_name"] == "重庆市"
    assert routes[0]["from"] == [104.06, 30.67]
    assert routes[0]["to"] == [106.55, 29.56]


def test_routes_skip_a_stay_inside_the_same_city(footprint_db, photo, owner):
    photo(at="2024-01-01T10:00:00")
    photo(at="2024-01-01T12:00:00")

    source = _source(footprint_db, owner, None)
    routes, truncated = _sample_routes(footprint_db, _visits(footprint_db, source), 300)

    assert routes == []
    assert truncated is False


def test_routes_are_thinned_out_and_flagged_when_they_exceed_max_points(footprint_db, photo, owner):
    cities = [("甲", 30.0, 104.0), ("乙", 31.0, 105.0), ("丙", 32.0, 106.0), ("丁", 33.0, 107.0)]
    for index, (city, lat, lng) in enumerate(cities):
        photo(city=city, lat=lat, lng=lng, at=f"2024-01-0{index + 1}T10:00:00")

    source = _source(footprint_db, owner, None)
    routes, truncated = _sample_routes(footprint_db, _visits(footprint_db, source), 2)

    assert truncated is True
    assert len(routes) <= 2
    assert all(route["from"] and route["to"] for route in routes)
