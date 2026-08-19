"""Unit tests for 2026-08-18 nightly coverage gap scan.

Module exercised: ``app/service/tasks/metadata.py``.

Coverage before this file: 54.3% (91 missed lines out of 199).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _strategy():
    from app.service.tasks.metadata import ExtractMetadataStrategy
    return ExtractMetadataStrategy()


def _task(payload):
    return SimpleNamespace(payload=payload)


# === determine_image_type ===

def test_determine_image_type_flags_filename_screenshot_keywords():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    for keyword in ("screenshot", "Screenshot", "QQ\u622a\u56fe", "\u5c4f\u5e55\u622a\u56fe"):
        out = determine_image_type(f"my_{keyword}_demo.png", 4000, 3000, {"Make": "Canon"})
        assert out == ImageType.SCREENSHOT, keyword


def test_determine_image_type_flags_known_phone_resolution_as_screenshot():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    out = determine_image_type("IMG_0001.HEIC", 1290, 2796, {})
    assert out == ImageType.SCREENSHOT


def test_determine_image_type_returns_camera_when_exif_make_present():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    out = determine_image_type("IMG_0001.jpg", 4000, 3000, {"Make": "Canon", "Model": "EOS R5"})
    assert out == ImageType.CAMERA


def test_determine_image_type_returns_camera_when_only_model_present():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    out = determine_image_type("IMG_0001.jpg", 4000, 3000, {"Make": "", "Model": "iPhone 14 Pro"})
    assert out == ImageType.CAMERA


def test_determine_image_type_falls_back_to_other():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    out = determine_image_type("holiday.png", 5184, 3888, {})
    assert out == ImageType.OTHER


def test_determine_image_type_handles_none_dimensions_gracefully():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import determine_image_type
    out = determine_image_type("doc.png", None, None, {})
    assert out == ImageType.OTHER


# === haversine_distance ===

def test_haversine_distance_zero_when_points_match():
    from app.service.tasks.metadata import haversine_distance
    assert haversine_distance(39.9042, 116.4074, 39.9042, 116.4074) == pytest.approx(0.0, abs=1e-6)


def test_haversine_distance_known_pair_within_tolerance():
    # Beijing -> Shanghai: ~1,067 km
    from app.service.tasks.metadata import haversine_distance
    distance = haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
    assert 1_060_000 <= distance <= 1_080_000


def test_haversine_distance_symmetric():
    from app.service.tasks.metadata import haversine_distance
    a = haversine_distance(40.0, 116.0, 41.0, 117.0)
    b = haversine_distance(41.0, 117.0, 40.0, 116.0)
    assert a == pytest.approx(b, abs=1e-6)


# === is_point_in_polygon ===

def test_is_point_in_polygon_inside_simple_square():
    from app.service.tasks.metadata import is_point_in_polygon
    square = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]
    assert is_point_in_polygon(5.0, 5.0, square) is True


def test_is_point_in_polygon_outside_simple_square():
    from app.service.tasks.metadata import is_point_in_polygon
    square = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]
    assert is_point_in_polygon(15.0, 15.0, square) is False


def test_is_point_in_polygon_returns_false_for_too_small_polygon():
    from app.service.tasks.metadata import is_point_in_polygon
    assert is_point_in_polygon(1.0, 1.0, [[0.0, 0.0], [1.0, 1.0]]) is False
    assert is_point_in_polygon(1.0, 1.0, []) is False


def test_is_point_in_polygon_handles_non_rectangular_shape():
    from app.service.tasks.metadata import is_point_in_polygon
    triangle = [[0.0, 0.0], [0.0, 5.0], [5.0, 0.0]]
    assert is_point_in_polygon(1.0, 1.0, triangle) is True
    assert is_point_in_polygon(4.0, 4.0, triangle) is False


# === identify_scene ===

def test_identify_scene_matches_polygon_first_when_polygon_scene_listed_first():
    from app.service.tasks.metadata import identify_scene
    polygon_scene = SimpleNamespace(
        id="polygon-scene",
        polygon=json.dumps([[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]),
        radius=None, latitude=None, longitude=None,
    )
    radius_scene = SimpleNamespace(
        id="radius-scene",
        polygon=None, radius=50_000, latitude=5.0, longitude=5.0,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [polygon_scene, radius_scene]
    assert identify_scene(db, 5.0, 5.0) == "polygon-scene"


def test_identify_scene_falls_back_to_radius_when_polygon_empty():
    from app.service.tasks.metadata import identify_scene
    inside = SimpleNamespace(
        id="inside",
        polygon=None, radius=10_000, latitude=5.0, longitude=5.0,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [inside]
    assert identify_scene(db, 5.001, 5.001) == "inside"


def test_identify_scene_returns_none_when_no_match():
    from app.service.tasks.metadata import identify_scene
    scene = SimpleNamespace(
        id="far",
        polygon=json.dumps([[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0]]),
        radius=None, latitude=None, longitude=None,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]
    assert identify_scene(db, 50.0, 50.0) is None


def test_identify_scene_swallow_broken_polygon_json():
    from app.service.tasks.metadata import identify_scene
    broken = SimpleNamespace(
        id="broken",
        polygon="{this is not json",
        radius=None, latitude=None, longitude=None,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [broken]
    assert identify_scene(db, 0.0, 0.0) is None


def test_identify_scene_accepts_preparsed_polygon_list():
    from app.service.tasks.metadata import identify_scene
    triangle = [[0.0, 0.0], [0.0, 10.0], [10.0, 0.0]]
    scene = SimpleNamespace(
        id="pre-parsed",
        polygon=triangle,
        radius=None, latitude=None, longitude=None,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]
    assert identify_scene(db, 5.0, 1.0) == "pre-parsed"


# === rebuild_metadata_cpu_job / sync_rebuild_metadata_cpu_job ===

def test_rebuild_metadata_cpu_job_returns_meta_dict_on_success():
    from app.service.tasks.metadata import rebuild_metadata_cpu_job
    expected = {"photo_time": "2024-01-01T00:00:00", "exif_info": {"Make": "Canon"}}
    with patch("app.service.tasks.metadata.exif.extract_metadata", return_value=expected) as extract:
        result = rebuild_metadata_cpu_job("/tmp/x/y.jpg", uuid4())
    assert result == {"success": True, "meta": expected}
    extract.assert_called_once_with("/tmp/x/y.jpg", "y.jpg")


def test_rebuild_metadata_cpu_job_wraps_exceptions():
    from app.service.tasks.metadata import rebuild_metadata_cpu_job
    with patch("app.service.tasks.metadata.exif.extract_metadata", side_effect=OSError("disk full")):
        result = rebuild_metadata_cpu_job("/tmp/x/y.jpg", uuid4())
    assert result["success"] is False
    assert "disk full" in result["error"]


def test_sync_rebuild_metadata_cpu_job_returns_meta_dict():
    from app.service.tasks.metadata import sync_rebuild_metadata_cpu_job
    expected = {"photo_time": None, "exif_info": None}
    with patch("app.service.tasks.metadata.exif.extract_metadata", return_value=expected):
        result = _run(sync_rebuild_metadata_cpu_job("/tmp/a/b.png", uuid4()))
    assert result == {"success": True, "meta": expected}


def test_sync_rebuild_metadata_cpu_job_reports_failure():
    from app.service.tasks.metadata import sync_rebuild_metadata_cpu_job
    with patch("app.service.tasks.metadata.exif.extract_metadata", side_effect=ValueError("corrupt header")):
        result = _run(sync_rebuild_metadata_cpu_job("/tmp/a/b.png", uuid4()))
    assert result["success"] is False
    assert "corrupt header" in result["error"]


# === ExtractMetadataStrategy.process ===

def test_extract_strategy_skips_when_photo_id_missing():
    strategy = _strategy()
    out = _run(strategy.process(worker=MagicMock(), task=_task({}), db=MagicMock()))
    assert out == {"status": "skipped", "reason": "missing photo_id"}


def test_extract_strategy_skips_when_photo_not_found():
    strategy = _strategy()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    out = _run(strategy.process(worker=MagicMock(), task=_task({"photo_id": str(uuid4())}), db=db))
    assert out == {"status": "skipped", "reason": "photo not found"}


def test_extract_strategy_returns_failed_on_invalid_uuid():
    strategy = _strategy()
    out = _run(strategy.process(worker=MagicMock(), task=_task({"photo_id": "not-a-uuid"}), db=MagicMock()))
    assert out == {"status": "failed", "reason": "invalid uuid"}


def test_extract_strategy_success_uses_payload_file_path_and_updater(monkeypatch):
    strategy = _strategy()
    photo_id = uuid4()
    owner_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id, owner_id=owner_id,
        file_path="/should/not/be/used.jpg",
        filename="IMG_0001.jpg",
        width=4000, height=3000,
        photo_time=None, image_type=None, processed_tasks=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    captured = {}

    async def fake_sync(file_path, _file_id):
        captured["file_path"] = file_path
        return {"success": True, "meta": {"photo_time": None, "exif_info": {"Make": "Canon"}}}

    monkeypatch.setattr("app.service.tasks.metadata.sync_rebuild_metadata_cpu_job", fake_sync)
    update_calls = []

    def fake_update(target_db, target_photo, meta):
        update_calls.append((target_db, target_photo, meta))
        return None

    monkeypatch.setattr("app.service.tasks.metadata.update_photo_metadata_from_extract", fake_update)
    out = _run(strategy.process(
        worker=MagicMock(),
        task=_task({"photo_id": str(photo_id), "file_path": "/payload/file.jpg"}),
        db=db,
    ))
    assert out == {"status": "success"}
    assert captured == {"file_path": "/payload/file.jpg"}
    assert len(update_calls) == 1
    assert update_calls[0][0] is db
    assert update_calls[0][1] is photo


def test_extract_strategy_falls_back_to_photo_file_path():
    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id, owner_id=None,
        file_path="/library/file.jpg",
        filename="file.jpg",
        width=4000, height=3000,
        photo_time=None, image_type=None, processed_tasks=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    seen = {}

    async def fake_sync(file_path, _file_id):
        seen["file_path"] = file_path
        return {"success": False, "error": "downstream failure"}

    with patch("app.service.tasks.metadata.sync_rebuild_metadata_cpu_job", fake_sync):
        with pytest.raises(Exception, match="downstream failure"):
            _run(strategy.process(worker=MagicMock(), task=_task({"photo_id": str(photo_id)}), db=db))
    assert seen == {"file_path": "/library/file.jpg"}


# === update_photo_metadata_from_extract ===

def _make_photo():
    return SimpleNamespace(
        id=uuid4(),
        owner_id=None,
        filename="IMG_0001.jpg",
        width=4000, height=3000,
        photo_time=None, image_type=None, processed_tasks=None,
    )


def _make_db_with_metadata(metadata_row=None):
    db = MagicMock()

    def _query_side_effect(model):
        if model.__name__ == "PhotoMetadata":
            chain = MagicMock()
            chain.filter.return_value.first.return_value = metadata_row
            return chain
        return MagicMock()

    db.query.side_effect = _query_side_effect
    return db


def test_update_photo_metadata_writes_exif_camera_and_shooting_params():
    from app.db.models.photo import ImageType
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    meta = {
        "exif_info": {
            "Make": "Canon",
            "Model": "EOS R5",
            "FNumber": 2.8,
            "ExposureTime": "1/250",
            "ISOSpeedRatings": 200,
            "FocalLength": 50.0,
            "FocalLengthIn35mmFilm": 50,
        },
        "photo_time": None,
    }
    photo = _make_photo()
    db_meta = SimpleNamespace(
        photo_id=photo.id,
        exif_info=None, make=None, model=None, shooting_params=None,
        latitude=None, longitude=None,
        city=None, district=None, province=None, country=None, address=None,
        scene_id=None,
    )
    db = _make_db_with_metadata(metadata_row=db_meta)
    update_photo_metadata_from_extract(db, photo, meta)
    assert db_meta.make == "Canon"
    assert db_meta.model == "EOS R5"
    assert db_meta.shooting_params["f_number"] == "2.8"
    assert db_meta.shooting_params["exposure_time"] == "1/250"
    assert db_meta.shooting_params["iso"] == "200"
    assert db_meta.shooting_params["focal_length"] == "50.0"
    assert db_meta.shooting_params["focal_length_35mm"] == "50"
    assert json.loads(db_meta.exif_info)["Make"] == "Canon"
    assert photo.image_type == ImageType.CAMERA
    assert photo.processed_tasks == {"metadata": True}
    db.commit.assert_called_once()


def test_update_photo_metadata_records_location_details_and_scene_id():
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    meta = {
        "exif_info": None,
        "location_details": {
            "latitude": 39.9042, "longitude": 116.4074,
            "city": "Beijing", "district": "Dongcheng", "province": "Beijing",
            "country": "CN", "address": "Tiananmen",
        },
        "photo_time": "2024-10-01T12:00:00",
    }
    photo = _make_photo()
    db_meta = SimpleNamespace(
        photo_id=photo.id,
        exif_info=None, make=None, model=None, shooting_params=None,
        latitude=None, longitude=None,
        city=None, district=None, province=None, country=None, address=None,
        scene_id=None,
    )
    db = _make_db_with_metadata(metadata_row=db_meta)
    with patch("app.service.tasks.metadata.identify_scene", return_value="scene-42") as identify:
        update_photo_metadata_from_extract(db, photo, meta)
    assert db_meta.latitude == 39.9042
    assert db_meta.longitude == 116.4074
    assert db_meta.city == "Beijing"
    assert db_meta.district == "Dongcheng"
    assert db_meta.province == "Beijing"
    assert db_meta.country == "CN"
    assert db_meta.address == "Tiananmen"
    assert db_meta.scene_id == "scene-42"
    assert photo.photo_time == "2024-10-01T12:00:00"
    identify.assert_called_once_with(db, 39.9042, 116.4074)


def test_update_photo_metadata_swallows_scene_lookup_failure():
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    meta = {
        "exif_info": None,
        "location_details": {"latitude": 1.0, "longitude": 2.0, "city": "X"},
        "photo_time": None,
    }
    photo = _make_photo()
    db_meta = SimpleNamespace(
        photo_id=photo.id,
        exif_info=None, make=None, model=None, shooting_params=None,
        latitude=None, longitude=None,
        city=None, district=None, province=None, country=None, address=None,
        scene_id=None,
    )
    db = _make_db_with_metadata(metadata_row=db_meta)
    with patch("app.service.tasks.metadata.identify_scene", side_effect=RuntimeError("scene service down")):
        update_photo_metadata_from_extract(db, photo, meta)
    assert db_meta.city == "X"
    assert db_meta.scene_id is None
    db.commit.assert_called_once()


def test_update_photo_metadata_creates_metadata_row_when_missing():
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    photo = _make_photo()
    db = _make_db_with_metadata(metadata_row=None)
    update_photo_metadata_from_extract(db, photo, {"exif_info": None, "photo_time": None})
    # db.add is called twice: first for the new PhotoMetadata row, then for the photo.
    assert db.add.call_count == 2
    first_call_args = db.add.call_args_list[0][0]
    new_meta = first_call_args[0]
    assert new_meta.photo_id == photo.id
    assert photo.processed_tasks == {"metadata": True}
    db.commit.assert_called_once()


def test_update_photo_metadata_preserves_existing_processed_tasks():
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    photo = _make_photo()
    photo.processed_tasks = {"thumbnail": True}
    db_meta = SimpleNamespace(
        photo_id=photo.id,
        exif_info=None, make=None, model=None, shooting_params=None,
        latitude=None, longitude=None,
        city=None, district=None, province=None, country=None, address=None,
        scene_id=None,
    )
    db = _make_db_with_metadata(metadata_row=db_meta)
    update_photo_metadata_from_extract(db, photo, {"exif_info": None, "photo_time": None})
    assert photo.processed_tasks == {"thumbnail": True, "metadata": True}


def test_update_photo_metadata_handles_owner_id_with_album_trigger(monkeypatch):
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    photo = _make_photo()
    photo.owner_id = uuid4()
    db_meta = SimpleNamespace(
        photo_id=photo.id,
        exif_info=None, make=None, model=None, shooting_params=None,
        latitude=None, longitude=None,
        city=None, district=None, province=None, country=None, address=None,
        scene_id=None,
    )
    db = _make_db_with_metadata(metadata_row=db_meta)
    called = []

    def fake_trigger(target_db, target_owner_id, photo_ids):
        called.append((target_db, target_owner_id, list(photo_ids)))

    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", fake_trigger)
    update_photo_metadata_from_extract(db, photo, {"exif_info": None, "photo_time": None})
    assert len(called) == 1
    assert called[0][0] is db
    assert called[0][1] == photo.owner_id
    assert called[0][2] == [photo.id]
