"""Nightly coverage for GET /annual-report/location (2026-10-24).

之前该端点只被「带向量」的 sqlite 测试间接覆盖到：城市去重统计、Top Cities、
经纬度聚合点、最远城市判定这几段分支全部没有断言。本文件用真实 SQLite 会话
补齐这些分支（happy / edge / error 三类），不依赖 Postgres。
"""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import annual_report
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.dependencies import get_db


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]

RANGE = {"start_time": "2025-01-01T00:00:00", "end_time": "2025-12-31T23:59:59"}


@pytest.fixture
def report_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_photo(db, owner_id, photo_time, city=None, province=None, lat=None, lng=None):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, file_path=f"/{uuid4()}.jpg",
        photo_time=photo_time, file_type=FileType.image,
        image_type=ImageType.CAMERA, is_deleted=False, size=1024,
    )
    db.add(photo)
    db.add(PhotoMetadata(
        photo_id=photo.id, city=city, province=province,
        latitude=lat, longitude=lng,
    ))
    db.commit()
    return photo


def _client(db, owner_id):
    app = FastAPI()
    app.include_router(annual_report.router, prefix="/annual-report")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner_id)
    return TestClient(app)


def test_location_metrics_aggregate_cities_and_find_farthest_city(report_session):
    db = report_session
    owner_id = uuid4()
    shanghai_a = add_photo(db, owner_id, datetime(2025, 3, 1), "上海", "上海市", 31.2304, 121.4737)
    add_photo(db, owner_id, datetime(2025, 4, 1), "上海", "上海市", 31.2404, 121.4837)
    beijing = add_photo(db, owner_id, datetime(2025, 5, 1), "北京", "北京市", 39.9042, 116.4074)

    with _client(db, owner_id) as client:
        response = client.get("/annual-report/location", params=RANGE)

    assert response.status_code == 200
    data = response.json()
    assert data["lightenProvinceNum"] == 2
    assert data["lightenCityNum"] == 2
    assert data["topCities"][0]["cityName"] == "上海"
    assert data["topCities"][0]["photoCount"] == 2
    assert data["topCities"][0]["provinceName"] == "上海市"

    points = {p["name"]: p for p in data["locationPoints"]}
    assert set(points) == {"上海", "北京"}
    assert points["上海"]["count"] == 2
    assert points["上海"]["lat"] == pytest.approx(31.2354, abs=1e-3)
    assert points["上海"]["lng"] == pytest.approx(121.4787, abs=1e-3)
    assert str(shanghai_a.id) in points["上海"]["coverUrl"]

    # 上海照片更多 -> 作为「当前城市」；北京是最远城市。
    assert data["farthestCity"] == "北京"
    assert data["farthestDistance"] > 0
    assert str(beijing.id) in {str(p["id"]) for p in data["farthestCityPhotos"]}


def test_location_metrics_empty_range_returns_zeroed_payload(report_session):
    db = report_session
    owner_id = uuid4()

    with _client(db, owner_id) as client:
        response = client.get("/annual-report/location", params=RANGE)

    assert response.status_code == 200
    data = response.json()
    assert data["lightenProvinceNum"] == 0
    assert data["lightenCityNum"] == 0
    assert data["topCities"] == []
    assert data["locationPoints"] == []
    assert data["farthestCity"] is None
    assert data["farthestDistance"] == 0
    assert data["farthestCityPhotos"] == []


def test_location_metrics_exclude_other_owners_and_out_of_range_photos(report_session):
    db = report_session
    owner_id = uuid4()
    other_owner = uuid4()
    add_photo(db, owner_id, datetime(2025, 3, 1), "上海", "上海市", 31.2304, 121.4737)
    add_photo(db, other_owner, datetime(2025, 3, 2), "广州", "广东省", 23.1291, 113.2644)
    add_photo(db, owner_id, datetime(2024, 3, 1), "深圳", "广东省", 22.5431, 114.0579)

    with _client(db, owner_id) as client:
        response = client.get("/annual-report/location", params=RANGE)

    assert response.status_code == 200
    data = response.json()
    assert data["lightenCityNum"] == 1
    assert [p["name"] for p in data["locationPoints"]] == ["上海"]
    assert data["farthestCity"] is None


def test_location_points_skip_city_without_coordinates(report_session):
    db = report_session
    owner_id = uuid4()
    add_photo(db, owner_id, datetime(2025, 3, 1), "上海", "上海市", 31.2304, 121.4737)
    # 有城市名但没有经纬度：应计入城市统计，但不产生地图点位。
    add_photo(db, owner_id, datetime(2025, 3, 2), "南京", "江苏省")

    with _client(db, owner_id) as client:
        response = client.get("/annual-report/location", params=RANGE)

    assert response.status_code == 200
    data = response.json()
    assert data["lightenCityNum"] == 2
    assert [p["name"] for p in data["locationPoints"]] == ["上海"]
    # 只有一个有坐标的城市 -> 无「最远城市」
    assert data["farthestCity"] is None
