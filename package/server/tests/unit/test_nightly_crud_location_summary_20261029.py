"""2026-10-29 nightly coverage for ``app/crud/location.py``.

The nightly coverage scan reported ``crud/location.py`` at 85% with 66
uncovered lines.  The dark half is the location *summary* surface:

* ``_valid_coordinates`` -- the guard every geo query depends on;
* ``get_map_markers`` -- the pins on the map (it must drop photos without a
  fix and honour the date window);
* ``get_location_distribution`` -- the "where have I been" histogram, which
  groups by city / province / district / scene and rejects unknown levels;
* ``get_location_statistics`` -- the distinct counts shown above the map;
* ``search_locations`` -- the type-ahead suggestions.

A wrong group-by or a dropped ``None`` would put a photo under the wrong
place, so the tests assert on the exact buckets that come back.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.crud import location as location_crud
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _owner(db):
    user = User(id=uuid4(), username="loc-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user.id


def _photo(db, owner_id, filename="p.jpg", **kwargs):
    photo = Photo(
        id=kwargs.pop("id", uuid4()),
        owner_id=owner_id,
        filename=filename,
        file_path=kwargs.pop("file_path", filename),
        file_type=FileType.image,
        is_deleted=kwargs.pop("is_deleted", False),
        size=1,
        width=10,
        height=10,
        **kwargs,
    )
    db.add(photo)
    db.commit()
    return photo


def _metadata(db, photo, **kwargs):
    row = PhotoMetadata(photo_id=photo.id, **kwargs)
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# _valid_coordinates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (30.5, 114.3, True),
        (0, 0, True),
        (-90, -180, True),
        (90, 180, True),
        (None, 114.3, False),
        (30.5, None, False),
        (91, 114.3, False),
        (-91, 114.3, False),
        (30.5, 181, False),
        (30.5, -181, False),
    ],
)
def test_valid_coordinates_rejects_out_of_range_values(latitude, longitude, expected):
    assert location_crud._valid_coordinates(latitude, longitude) is expected


def test_nearby_time_compare_rows_returns_nothing_without_valid_coordinates(db):
    owner = _owner(db)
    assert location_crud._nearby_time_compare_rows(db, owner, None, None) == []
    assert location_crud._nearby_time_compare_rows(db, owner, 999, 114.3) == []


# ---------------------------------------------------------------------------
# get_map_markers
# ---------------------------------------------------------------------------


def test_map_markers_drop_the_photos_without_a_fix(db):
    owner = _owner(db)
    located = _photo(db, owner, "located.jpg")
    _metadata(db, located, latitude=30.5, longitude=114.3)
    unlocated = _photo(db, owner, "unlocated.jpg")
    _metadata(db, unlocated, city="武汉市")

    markers = location_crud.get_map_markers(db, owner)

    assert [marker["id"] for marker in markers] == [str(located.id)]
    assert markers[0]["lat"] == 30.5
    assert markers[0]["lng"] == 114.3


def test_map_markers_honour_the_date_window(db):
    owner = _owner(db)
    inside = _photo(db, owner, "inside.jpg", photo_time=None)
    _metadata(db, inside, latitude=30.5, longitude=114.3)

    markers = location_crud.get_map_markers(
        db, owner, start_date="2024-01-01", end_date="2024-12-31"
    )

    # The photo has no capture time, so it falls outside the window.
    assert markers == []


def test_map_markers_exclude_deleted_photos(db):
    owner = _owner(db)
    gone = _photo(db, owner, "gone.jpg", is_deleted=True)
    _metadata(db, gone, latitude=30.5, longitude=114.3)

    assert location_crud.get_map_markers(db, owner) == []


# ---------------------------------------------------------------------------
# get_location_distribution
# ---------------------------------------------------------------------------


def test_location_distribution_rejects_an_unknown_level(db):
    owner = _owner(db)
    photo = _photo(db, owner)
    _metadata(db, photo, city="武汉市")

    assert location_crud.get_location_distribution(db, owner, level="country") == []


def test_location_distribution_groups_by_city(db):
    owner = _owner(db)
    first = _photo(db, owner, "a.jpg")
    _metadata(db, first, city="武汉市", province="湖北省", district="武昌区")
    second = _photo(db, owner, "b.jpg")
    _metadata(db, second, city="武汉市", province="湖北省", district="洪山区")
    third = _photo(db, owner, "c.jpg")
    _metadata(db, third, city="宜昌市", province="湖北省", district="西陵区")

    distribution = location_crud.get_location_distribution(db, owner, level="city")

    buckets = {item["name"]: item["count"] for item in distribution}
    assert buckets == {"武汉市": 2, "宜昌市": 1}
    assert all(item["level"] == "city" for item in distribution)


def test_location_distribution_groups_by_province_and_district(db):
    owner = _owner(db)
    photo = _photo(db, owner)
    _metadata(db, photo, city="武汉市", province="湖北省", district="武昌区")

    by_province = location_crud.get_location_distribution(db, owner, level="province")
    by_district = location_crud.get_location_distribution(db, owner, level="district")

    assert [item["name"] for item in by_province] == ["湖北省"]
    assert [item["name"] for item in by_district] == ["武昌区"]


def test_location_distribution_groups_by_scene(db):
    owner = _owner(db)
    scene = Scene(id=uuid4(), name="黄鹤楼", owner_id=owner)
    db.add(scene)
    db.commit()
    photo = _photo(db, owner)
    _metadata(db, photo, city="武汉市", scene_id=scene.id)

    distribution = location_crud.get_location_distribution(db, owner, level="scene")

    assert [item["name"] for item in distribution] == ["黄鹤楼"]


def test_location_distribution_ignores_blank_and_missing_names(db):
    owner = _owner(db)
    blank = _photo(db, owner, "blank.jpg")
    _metadata(db, blank, city="")
    missing = _photo(db, owner, "missing.jpg")
    _metadata(db, missing, province="湖北省")
    named = _photo(db, owner, "named.jpg")
    _metadata(db, named, city="武汉市")

    distribution = location_crud.get_location_distribution(db, owner, level="city")

    assert [item["name"] for item in distribution] == ["武汉市"]


def test_location_distribution_excludes_deleted_photos(db):
    owner = _owner(db)
    gone = _photo(db, owner, "gone.jpg", is_deleted=True)
    _metadata(db, gone, city="武汉市")

    assert location_crud.get_location_distribution(db, owner, level="city") == []


def test_location_statistics_counts_the_distinct_places(db):
    owner = _owner(db)
    first = _photo(db, owner, "a.jpg")
    _metadata(db, first, city="武汉市", province="湖北省", district="武昌区", country="中国")
    second = _photo(db, owner, "b.jpg")
    _metadata(db, second, city="宜昌市", province="湖北省", district="西陵区", country="中国")

    stats = location_crud.get_location_statistics(db, owner)

    assert stats["province_count"] == 1
    assert stats["city_count"] == 2
    assert stats["district_count"] == 2
    assert stats["country_count"] == 1


def test_location_statistics_are_zero_without_any_photos(db):
    owner = _owner(db)
    stats = location_crud.get_location_statistics(db, owner)
    assert stats == {
        "province_count": 0,
        "city_count": 0,
        "district_count": 0,
        "country_count": 0,
    }


# ---------------------------------------------------------------------------
# search_locations
# ---------------------------------------------------------------------------


def test_search_locations_suggests_a_matching_province(db):
    owner = _owner(db)
    photo = _photo(db, owner)
    _metadata(db, photo, province="湖北省", city="武汉市")

    suggestions = location_crud.search_locations(db, owner, "湖北")

    labels = [item["label"] for item in suggestions]
    assert "湖北省" in labels
    province = next(item for item in suggestions if item["label"] == "湖北省")
    assert province["value"] == {"province": "湖北省", "city": "", "district": ""}


def test_search_locations_returns_nothing_when_nothing_matches(db):
    owner = _owner(db)
    photo = _photo(db, owner)
    _metadata(db, photo, province="湖北省", city="武汉市")

    assert location_crud.search_locations(db, owner, "不存在的省") == []


def test_search_locations_does_not_repeat_a_label(db):
    owner = _owner(db)
    first = _photo(db, owner, "a.jpg")
    _metadata(db, first, province="湖北省", city="武汉市")
    second = _photo(db, owner, "b.jpg")
    _metadata(db, second, province="湖北省", city="宜昌市")

    suggestions = location_crud.search_locations(db, owner, "湖北")

    labels = [item["label"] for item in suggestions]
    assert len(labels) == len(set(labels))

