from datetime import datetime
from uuid import uuid4

import pytest

from app.crud.location import get_time_compare_photos, get_time_compare_summary
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.image_vector import ImageVector


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _add_photo(db, owner_id, scene_id, captured_at, filename, latitude=None, longitude=None, width=None, height=None):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename=filename,
        file_path=f"/photos/{filename}",
        file_type=FileType.image,
        size=100,
        width=width,
        height=height,
        photo_time=captured_at,
        is_deleted=False,
    )
    db.add(photo)
    db.add(PhotoMetadata(
        photo_id=photo.id,
        scene_id=scene_id,
        city="杭州",
        district="西湖区",
        latitude=latitude,
        longitude=longitude,
    ))
    return photo


def test_time_compare_groups_only_same_scene_across_years(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    scene = Scene(id=uuid4(), owner_id=owner_id, name="断桥", address="杭州", is_custom=True)
    other_scene = Scene(id=uuid4(), owner_id=owner_id, name="西湖其他位置", address="杭州", is_custom=True)
    db.add_all([scene, other_scene])

    old = _add_photo(db, owner_id, scene.id, datetime(2018, 4, 3, 9), "old.jpg")
    recent = _add_photo(db, owner_id, scene.id, datetime(2026, 9, 18, 16), "recent.jpg")
    _add_photo(db, owner_id, other_scene.id, datetime(2020, 1, 1, 12), "other.jpg")
    db.commit()

    summary = get_time_compare_summary(db, owner_id, scene_id=scene.id)

    assert summary["eligible"] is True
    assert [item["year"] for item in summary["years"]] == [2018, 2026]
    assert summary["first_photo"].id == old.id
    assert summary["latest_photo"].id == recent.id
    assert summary["city"] == "杭州"


def test_time_compare_resolves_scene_from_source_photo(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    scene = Scene(id=uuid4(), owner_id=owner_id, name="操场", is_custom=True)
    db.add(scene)
    source = _add_photo(db, owner_id, scene.id, datetime(2021, 5, 1), "source.jpg")
    _add_photo(db, owner_id, scene.id, datetime(2025, 5, 1), "new.jpg")
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=source.id)
    photos = get_time_compare_photos(db, owner_id, scene.id, 2021)

    assert summary["scene_id"] == scene.id
    assert summary["source_photo_id"] == source.id
    assert summary["source_photo_year"] == 2021
    assert [photo.id for photo in photos] == [source.id]


def test_time_compare_falls_back_to_nearby_gps_across_years(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    anchor = _add_photo(
        db, owner_id, None, datetime(2021, 5, 1), "anchor.jpg", 30.2500000, 120.1500000
    )
    nearby = _add_photo(
        db, owner_id, None, datetime(2025, 5, 1), "nearby.jpg", 30.2504500, 120.1500000
    )
    _add_photo(
        db, owner_id, None, datetime(2019, 5, 1), "too-far.jpg", 30.2520000, 120.1500000
    )
    _add_photo(
        db, uuid4(), None, datetime(2024, 5, 1), "other-owner.jpg", 30.2501000, 120.1500000
    )
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=anchor.id)
    photos = get_time_compare_photos(db, owner_id, photo_id=anchor.id, year=2025)

    assert summary["eligible"] is True
    assert summary["match_type"] == "nearby_gps"
    assert summary["radius_m"] == 200
    assert summary["scene_id"] is None
    assert summary["location_name"] == "西湖区附近"
    assert [item["year"] for item in summary["years"]] == [2021, 2025]
    assert [photo.id for photo in photos] == [nearby.id]


def test_time_compare_gps_requires_coordinates(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    source = _add_photo(db, owner_id, None, datetime(2025, 5, 1), "no-gps.jpg")
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=source.id)

    assert summary["eligible"] is False
    assert summary["reason"] == "precise_location_required"
    assert summary["match_type"] == "nearby_gps"


def test_time_compare_ranks_similar_view_above_closer_unrelated_photo(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    anchor = _add_photo(
        db, owner_id, None, datetime(2025, 5, 1), "anchor.jpg", 30.2500000, 120.1500000
    )
    unrelated = _add_photo(
        db, owner_id, None, datetime(2021, 5, 1), "unrelated.jpg", 30.2500200, 120.1500000
    )
    similar = _add_photo(
        db, owner_id, None, datetime(2021, 5, 1), "similar.jpg", 30.2507000, 120.1500000
    )
    anchor_vector = [1.0, 0.0] + [0.0] * 510
    db.add_all([
        ImageVector(photo_id=anchor.id, embedding=anchor_vector),
        ImageVector(photo_id=unrelated.id, embedding=[0.0, 1.0] + [0.0] * 510),
        ImageVector(photo_id=similar.id, embedding=[0.99, 0.01] + [0.0] * 510),
    ])
    db.commit()

    photos = get_time_compare_photos(
        db,
        owner_id,
        photo_id=anchor.id,
        reference_photo_id=anchor.id,
        year=2021,
    )
    summary = get_time_compare_summary(db, owner_id, photo_id=anchor.id)

    assert [photo.id for photo in photos] == [similar.id, unrelated.id]
    assert summary["first_photo"].id == similar.id
    assert summary["latest_photo"].id == anchor.id


def test_time_compare_rejects_only_unrelated_embedded_views(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    anchor = _add_photo(
        db, owner_id, None, datetime(2025, 5, 1), "anchor.jpg", 30.2500000, 120.1500000
    )
    unrelated = _add_photo(
        db, owner_id, None, datetime(2021, 5, 1), "unrelated.jpg", 30.2500100, 120.1500000
    )
    db.add_all([
        ImageVector(photo_id=anchor.id, embedding=[1.0, 0.0] + [0.0] * 510),
        ImageVector(photo_id=unrelated.id, embedding=[0.0, 1.0] + [0.0] * 510),
    ])
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=anchor.id)

    assert summary["eligible"] is False
    assert summary["reason"] == "similar_view_required"
    assert summary["visual_similarity"] == 0.0


def test_time_compare_supports_different_seasons_in_same_year(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    spring = _add_photo(db, owner_id, None, datetime(2025, 3, 10), "spring.jpg", 30.25, 120.15)
    autumn = _add_photo(db, owner_id, None, datetime(2025, 10, 10), "autumn.jpg", 30.25, 120.15)
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=spring.id)

    assert summary["eligible"] is True
    assert [str(visit["date"]) for visit in summary["visits"]] == ["2025-03-10", "2025-10-10"]
    assert summary["latest_photo"].id == autumn.id


def test_time_compare_groups_same_day_burst_as_one_visit(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    first = _add_photo(db, owner_id, None, datetime(2025, 6, 1, 9), "one.jpg", 30.25, 120.15)
    _add_photo(db, owner_id, None, datetime(2025, 6, 1, 18), "two.jpg", 30.25, 120.15)
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=first.id)

    assert summary["eligible"] is False
    assert summary["reason"] == "multiple_visits_required"
    assert len(summary["visits"]) == 1


def test_time_compare_does_not_pair_landscape_with_portrait(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    landscape = _add_photo(
        db, owner_id, None, datetime(2024, 3, 1), "wide.jpg", 30.25, 120.15, width=1600, height=900
    )
    _add_photo(
        db, owner_id, None, datetime(2025, 3, 1), "tall.jpg", 30.25, 120.15, width=900, height=1600
    )
    db.commit()

    summary = get_time_compare_summary(db, owner_id, photo_id=landscape.id)

    assert summary["eligible"] is False
    assert summary["reason"] == "orientation_match_required"
