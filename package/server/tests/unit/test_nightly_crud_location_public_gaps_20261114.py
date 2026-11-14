# -*- coding: utf-8 -*-
"""Nightly watch 2026-11-14 round2 · 覆盖盲区补测（app/crud/location.py）。

相对 2026-11-13 覆盖率基线，此前完全未触达的分支：
- get_time_compare_summary：没有 scene_id 也没有 photo_id、照片不存在、场景不可见时都返回 None。
- get_location_photos：未知层级直接返回空列表；province 层级按省份过滤；
  place_key 与查询条件不一致时抛 400。
- get_timeline_nodes：province / district 层级分别落到对应的空值处理表达式，
  并按起止日期过滤照片。
- get_location_distribution：按起止日期过滤照片后分组统计。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.crud import location as location_crud
from app.service.relations import region_key
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.user import User

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def owner(face_sqlite_session):
    db = face_sqlite_session
    user = User(id=uuid.uuid4(), username="location-owner", hashed_password="x", is_active=True)
    db.add(user)
    db.commit()
    return user


def _add_photo(db, owner, name, when, city="西安", province="陕西", district="雁塔区",
               latitude=34.2, longitude=108.9, scene_id=None):
    photo = Photo(id=uuid.uuid4(), owner_id=owner.id, filename=name, file_path=name,
                  file_type=FileType.image, photo_time=when, is_deleted=False)
    db.add(photo)
    db.flush()
    db.add(PhotoMetadata(photo_id=photo.id, city=city, province=province, district=district,
                         latitude=latitude, longitude=longitude, scene_id=scene_id))
    db.flush()
    return photo


# --------------------------------------------------------------------------- #
# get_time_compare_summary
# --------------------------------------------------------------------------- #


def test_time_compare_summary_returns_none_without_any_anchor(face_sqlite_session, owner):
    assert location_crud.get_time_compare_summary(face_sqlite_session, owner.id) is None


def test_time_compare_summary_returns_none_for_an_unknown_photo(face_sqlite_session, owner):
    assert location_crud.get_time_compare_summary(
        face_sqlite_session, owner.id, photo_id=uuid.uuid4()) is None


def test_time_compare_summary_returns_none_for_a_scene_owned_by_someone_else(face_sqlite_session, owner):
    db = face_sqlite_session
    stranger = User(id=uuid.uuid4(), username="location-stranger", hashed_password="x", is_active=True)
    db.add(stranger)
    db.flush()
    scene = Scene(id=uuid.uuid4(), name="别人的场景", owner_id=stranger.id)
    db.add(scene)
    db.commit()

    assert location_crud.get_time_compare_summary(db, owner.id, scene_id=scene.id) is None


# --------------------------------------------------------------------------- #
# get_location_photos
# --------------------------------------------------------------------------- #


def test_location_photos_returns_empty_for_an_unknown_level(face_sqlite_session, owner):
    assert location_crud.get_location_photos(face_sqlite_session, owner.id, "西安", level="country") == []


def test_location_photos_filters_by_province(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0), province="陕西")
    _add_photo(db, owner, "b.jpg", datetime(2024, 5, 1, 11, 0), province="甘肃")
    db.commit()

    photos = location_crud.get_location_photos(db, owner.id, "陕西", level="province")

    assert [p.filename for p in photos] == ["a.jpg"]


def test_location_photos_rejects_a_mismatched_place_key(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0))
    db.commit()

    with pytest.raises(HTTPException) as excinfo:
        location_crud.get_location_photos(db, owner.id, "西安", level="city", place_key=region_key("city", ["CN", "Shaanxi", "北京"]))
    assert excinfo.value.status_code == 400


# --------------------------------------------------------------------------- #
# get_timeline_nodes
# --------------------------------------------------------------------------- #


def test_timeline_nodes_supports_the_province_level(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0), city="西安", province="陕西")
    db.commit()

    response = location_crud.get_timeline_nodes(db, owner.id, level="province")

    assert response.nodes
    assert response.nodes[0].locationName == "陕西"


def test_timeline_nodes_supports_the_district_level(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0), district="雁塔区")
    db.commit()

    response = location_crud.get_timeline_nodes(db, owner.id, level="district")

    assert response.nodes
    assert response.nodes[0].locationName == "雁塔区"


def test_timeline_nodes_filters_by_the_date_range(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0))
    _add_photo(db, owner, "b.jpg", datetime(2024, 6, 1, 10, 0))
    db.commit()

    response = location_crud.get_timeline_nodes(db, owner.id, level="city",
                                             start_date="2024-06-01", end_date="2024-06-30")

    assert len(response.nodes) == 1
    assert response.nodes[0].photoCount == 1


# --------------------------------------------------------------------------- #
# get_location_distribution
# --------------------------------------------------------------------------- #


def test_location_distribution_filters_by_the_date_range(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0), city="西安")
    _add_photo(db, owner, "b.jpg", datetime(2024, 6, 1, 10, 0), city="北京")
    db.commit()

    rows = location_crud.get_location_distribution(db, owner.id, level="city",
                                                   start_date="2024-06-01", end_date="2024-06-30")

    assert rows == [{"name": "北京", "count": 1, "level": "city"}]

@pytest.mark.asyncio
async def test_timeline_nodes_merges_the_time_range_of_the_same_location(face_sqlite_session, owner):
    db = face_sqlite_session
    _add_photo(db, owner, "a.jpg", datetime(2024, 5, 1, 10, 0), city="西安")
    _add_photo(db, owner, "b.jpg", datetime(2024, 5, 3, 18, 0), city="西安")
    db.commit()

    response = location_crud.get_timeline_nodes(db, owner.id, level="city")

    assert len(response.nodes) == 1
    node = response.nodes[0]
    assert node.startDate == "2024-05-01"
    assert node.endDate == "2024-05-03"
    assert node.startTime == datetime(2024, 5, 1, 10, 0)
    assert node.endTime == datetime(2024, 5, 3, 18, 0)
