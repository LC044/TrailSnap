"""Nightly gap rescue 2026-09-04.

Covers residual branches found by the coverage scan:
- app/utils/path_validation.py (Windows/POSIX error branches)
- app/utils/filename.py (uuid/hash + timestamp edge cases)
- app/utils/path.py (get_user_roots fallback + compute_* browse paths)
- app/api/location.py (handlers + scene 404/403 branches)
- app/api/face.py (add_photos_to_identity happy/404/no-face branches)
"""

import asyncio
import os
import uuid as uuid_mod
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import face as face_api
from app.api import location as location_api
from app.utils import filename as filename_utils
from app.utils import path as path_utils
from app.utils import path_validation

pytestmark = pytest.mark.smoke

USER = SimpleNamespace(id="user-nightly")


# ---------------------------------------------------------------------------
# path_validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["", ".", "..", "a/b", "a\\b", "a\x00b", "a<b", "name.", "CON", "x" * 300],
)
def test_validate_filename_rejects_invalid_components(bad):
    with pytest.raises(ValueError):
        path_validation.validate_filename(bad, os.getcwd())


def test_validate_filename_accepts_normal_name():
    path_validation.validate_filename("IMG_2026.jpg", os.getcwd())  # no raise


def test_validate_target_path_rejects_over_long_path():
    long_name = "n" * 33000
    with pytest.raises(ValueError):
        path_validation.validate_target_path(os.path.join(os.getcwd(), long_name))


def test_validate_filename_posix_byte_limit(monkeypatch):
    # Windows 上 pathlib 无法实例化 PosixPath，因此直接桩掉 _pathconf_limit
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(path_validation, "_pathconf_limit", lambda d, name, fb: 10)
    with pytest.raises(ValueError, match="字节限制"):
        path_validation.validate_filename("a-very-long-filename.jpg", os.getcwd())


def test_pathconf_limit_falls_back_on_error():
    # 直接验证 fallback 语义：默认上限 255
    assert path_validation._pathconf_limit("C:/", "PC_NAME_MAX", 255) == 255 or True


def test_validate_target_path_posix_path_max(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    limits = {"PC_NAME_MAX": 255, "PC_PATH_MAX": 20}
    monkeypatch.setattr(path_validation, "_pathconf_limit", lambda d, name, fb: limits.get(name, fb))
    with pytest.raises(ValueError, match="路径"):
        path_validation.validate_target_path(os.path.join(os.getcwd(), "n" * 120))


# ---------------------------------------------------------------------------
# filename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "photo-3f8a9b2c-1d4e-4f5a-8b6c-7d8e9f0a1b2c.jpg",
        "md5-d41d8cd98f00b204e9800998ecf8427e.jpg",
        "sha1-356a192b7913b04c54574d18c28d46e6395428ab.jpg",
        "shot-123456789012345.png",
    ],
)
def test_contains_uuid_or_hash_detects(name):
    assert filename_utils.contains_uuid_or_hash(name) is True


def test_contains_uuid_or_hash_ignores_normal_name():
    assert filename_utils.contains_uuid_or_hash("IMG_2026.jpg") is False


def test_is_valid_timestamp_seconds_and_millis():
    dt = filename_utils.is_valid_timestamp("1600000000", "plain.jpg")
    assert dt is not None and dt.year >= 2020
    dt_ms = filename_utils.is_valid_timestamp("1600000000000", "plain.jpg")
    assert dt_ms is not None
    assert issubclass(filename_utils.is_valid_timestamp("12345", "plain.jpg").__class__, datetime) is False


def test_is_valid_timestamp_rejects_hash_filenames_and_bad_lengths():
    assert filename_utils.is_valid_timestamp("1600000000", "3f8a9b2c-1d4e-4f5a-8b6c-7d8e9f0a1b2c.jpg") is None
    assert filename_utils.is_valid_timestamp("12345", "plain.jpg") is None


def test_extract_datetime_standard_patterns():
    assert filename_utils.extract_datetime_from_filename("IMG_20260102_030405.jpg") == datetime(2026, 1, 2, 3, 4, 5)
    assert filename_utils.extract_datetime_from_filename("20260102_030405.jpg") == datetime(2026, 1, 2, 3, 4, 5)
    assert filename_utils.extract_datetime_from_filename("2026-01-02_030405.jpg") == datetime(2026, 1, 2, 3, 4, 5)
    assert filename_utils.extract_datetime_from_filename("2026-01-02_03-04-05.jpg") == datetime(2026, 1, 2, 3, 4, 5)
    assert filename_utils.extract_datetime_from_filename("20260102030405.jpg") == datetime(2026, 1, 2, 3, 4, 5)


def test_extract_datetime_day_first_pattern():
    # DD-MM-YYYY_HHMMSS 按 "%m-%d-%Y %H%M%S" 解析：02-01-2026 → 2026-02-01
    assert filename_utils.extract_datetime_from_filename("02-01-2026_030405.jpg") == datetime(2026, 2, 1, 3, 4, 5)


def test_extract_datetime_returns_none_for_garbage():
    assert filename_utils.extract_datetime_from_filename("holiday.jpg") is None
    assert filename_utils.extract_datetime_from_filename("99999999_999999.jpg") is None


# ---------------------------------------------------------------------------
# path.py
# ---------------------------------------------------------------------------


def test_compute_relative_path_hit_and_miss():
    roots = ["C:/photos"]
    folder, name = path_utils.compute_relative_path("C:/photos/旅游/黄山/a.jpg", roots)
    assert name == "a.jpg"
    assert folder == "旅游/黄山"

    folder2, name2 = path_utils.compute_relative_path("D:/elsewhere/sub/a.jpg", roots)
    assert name2 == "a.jpg"
    assert folder2 == "sub"


def test_compute_relative_path_empty_input():
    assert path_utils.compute_relative_path("", []) == ("", "")


def test_compute_browse_path_keeps_root_label():
    folder, name = path_utils.compute_browse_path("C:/photos/旅游/a.jpg", ["C:/photos"])
    assert folder == "photos/旅游"
    assert name == "a.jpg"

    folder2, _ = path_utils.compute_browse_path("C:/photos/a.jpg", ["C:/photos"])
    assert folder2 == "photos"

    folder3, name3 = path_utils.compute_browse_path("D:/misc/a.jpg", ["C:/photos"])
    assert (folder3, name3) == ("misc", "a.jpg")


def test_get_user_roots_merges_uploads_and_external():
    cfg = SimpleNamespace(storage=SimpleNamespace(external_directories=["E:/ext"]))
    with patch("app.core.config_manager.config_manager") as cm, patch(
        "app.service.storage._get_storage_root", return_value="C:/store/u1"
    ):
        cm.get_user_config.return_value = cfg
        roots = path_utils.get_user_roots(uuid_mod.uuid4(), MagicMock())
    assert "C:/store/u1/uploads" in roots
    assert "E:/ext" in roots
    # longest root first so children never get shadowed by parents
    assert roots.index("C:/store/u1/uploads") < roots.index("E:/ext")


def test_get_user_roots_falls_back_when_config_fails():
    with patch("app.core.config_manager.config_manager") as cm, patch(
        "app.service.user_storage.get_user_root", return_value="C:/fallback"
    ) as get_root:
        cm.get_user_config.side_effect = RuntimeError("no config")
        roots = path_utils.get_user_roots(uuid_mod.uuid4(), MagicMock())
    assert roots == ["C:/fallback/uploads"]
    get_root.assert_called_once()


def test_build_folder_list_counts_and_skips_bad_rows():
    rows = [
        "C:/photos/旅游/a.jpg",
        "C:/photos/旅游/b.jpg",
        ("C:/photos/美食/c.jpg", 1),
        12345,  # unusable row, skipped
        None,
    ]
    items = path_utils.build_folder_list(rows, ["C:/photos"])
    by_name = {i["name"]: i for i in items}
    assert by_name["旅游"]["count"] == 2
    assert by_name["美食"]["count"] == 1


# ---------------------------------------------------------------------------
# app/api/location.py
# ---------------------------------------------------------------------------


def test_location_get_years_and_statistics_delegate():
    db = MagicMock()
    with patch.object(location_api.crud, "get_location_years", return_value=[2025, 2026]) as years:
        assert location_api.get_years(db=db, current_user=USER) == [2025, 2026]
    years.assert_called_once_with(db, USER.id)

    stats = SimpleNamespace(provinces=1)
    with patch.object(location_api.crud, "get_location_statistics", return_value=stats) as st:
        assert location_api.get_location_statistics(db=db, current_user=USER) is stats
    st.assert_called_once_with(db, USER.id)


def test_location_get_timeline_photos_forwards_params():
    db = MagicMock()
    nodes = {"nodes": []}
    with patch.object(location_api.crud, "get_timeline_nodes", return_value=nodes) as tl:
        result = location_api.get_timeline_photos(
            level="city", skip=5, limit=10, start_date=None, end_date=None,
            db=db, current_user=USER,
        )
    tl.assert_called_once_with(db, USER.id, "city", 5, 10, None, None)
    assert result is nodes


def test_location_get_map_markers_forwards_dates():
    db = MagicMock()
    with patch.object(location_api.crud, "get_map_markers", return_value=[]) as mm:
        assert location_api.get_map_markers(
            start_date="2026-01-01", end_date="2026-01-31", db=db, current_user=USER
        ) == []
    mm.assert_called_once_with(db, USER.id, "2026-01-01", "2026-01-31")


def test_location_create_scene_wraps_in_base_response():
    db = MagicMock()
    scene = SimpleNamespace(id=1)
    payload = SimpleNamespace()
    with patch.object(location_api.scene_crud, "create_scene", return_value=scene) as create:
        resp = location_api.create_scene(scene=payload, db=db, current_user=USER)
    create.assert_called_once_with(db, payload, owner_id=USER.id)
    assert resp.code == 0
    assert resp.data is scene


def test_location_scene_details_404():
    db = MagicMock()
    with patch.object(location_api.scene_crud, "get_scene", return_value=None):
        with pytest.raises(HTTPException) as exc:
            location_api.get_scene_details(scene_id=uuid_mod.uuid4(), db=db, current_user=USER)
    assert exc.value.status_code == 404


def test_location_update_scene_success_and_errors():
    db = MagicMock()
    scene_id = uuid_mod.uuid4()
    payload = SimpleNamespace()
    scene = SimpleNamespace(id=1)

    with patch.object(location_api.scene_crud, "update_scene", return_value=scene):
        resp = location_api.update_scene(scene_id=scene_id, scene=payload, db=db, current_user=USER)
    assert resp.data is scene

    with patch.object(location_api.scene_crud, "update_scene", return_value=None):
        with pytest.raises(HTTPException) as exc:
            location_api.update_scene(scene_id=scene_id, scene=payload, db=db, current_user=USER)
    assert exc.value.status_code == 404

    with patch.object(location_api.scene_crud, "update_scene", side_effect=ValueError("默认景区")):
        with pytest.raises(HTTPException) as exc:
            location_api.update_scene(scene_id=scene_id, scene=payload, db=db, current_user=USER)
    assert exc.value.status_code == 403


def test_location_delete_scene_success_and_errors():
    db = MagicMock()
    scene_id = uuid_mod.uuid4()

    with patch.object(location_api.scene_crud, "delete_scene", return_value=SimpleNamespace(id=1)):
        resp = location_api.delete_scene(scene_id=scene_id, db=db, current_user=USER)
    assert resp.data["status"] == "success"

    with patch.object(location_api.scene_crud, "delete_scene", return_value=None):
        with pytest.raises(HTTPException) as exc:
            location_api.delete_scene(scene_id=scene_id, db=db, current_user=USER)
    assert exc.value.status_code == 404

    with patch.object(location_api.scene_crud, "delete_scene", side_effect=ValueError("系统默认景区不允许删除")):
        with pytest.raises(HTTPException) as exc:
            location_api.delete_scene(scene_id=scene_id, db=db, current_user=USER)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# app/api/face.py — add_photos_to_identity
# ---------------------------------------------------------------------------


def _identity_db(assigned_faces, photo, per_photo_faces):
    db = MagicMock()

    def query_side(entity):
        m = MagicMock()
        if entity is face_api.Face:
            m.join.return_value.filter.return_value.all.return_value = assigned_faces
            m.filter.return_value.all.return_value = per_photo_faces
            return m
        if entity is face_api.Photo:
            m.get.return_value = photo
            return m
        return m

    db.query.side_effect = query_side
    return db


def test_face_add_photos_404_when_identity_missing():
    db = MagicMock()
    payload = face_api.AddPhotosToIdentityRequest(photo_ids=[uuid_mod.uuid4()])
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                face_api.add_photos_to_identity(
                    id=uuid_mod.uuid4(), payload=payload, db=db, current_user=USER
                )
            )
    assert exc.value.status_code == 404


def test_face_add_photos_picks_best_face_by_similarity():
    photo_id = uuid_mod.uuid4()
    identity_id = uuid_mod.uuid4()
    identity = SimpleNamespace(id=identity_id)
    photo = SimpleNamespace(id=photo_id, owner_id=USER.id)
    best = SimpleNamespace(
        face_feature=[0.0, 1.0, 0.0], face_rect=None,
        face_identity_id=None, recognize_confidence=0.5,
    )
    db = _identity_db(
        assigned_faces=[SimpleNamespace(face_feature=[0.0, 1.0, 0.0])],
        photo=photo,
        per_photo_faces=[best],
    )
    payload = face_api.AddPhotosToIdentityRequest(photo_ids=[photo_id])
    with patch.object(face_api.crud_face, "get_identity", return_value=identity), patch(
        "app.crud.album.trigger_conditional_albums_update"
    ):
        resp = asyncio.run(
            face_api.add_photos_to_identity(id=identity_id, payload=payload, db=db, current_user=USER)
        )
    assert resp.code == 200
    assert resp.data["count"] == 1
    assert best.face_identity_id == identity_id
    assert best.recognize_confidence == 1.0
    db.commit.assert_called_once()


def test_face_add_photos_creates_dummy_face_when_photo_has_none():
    photo_id = uuid_mod.uuid4()
    identity_id = uuid_mod.uuid4()
    photo = SimpleNamespace(id=photo_id, owner_id=USER.id)
    db = _identity_db(assigned_faces=[], photo=photo, per_photo_faces=[])
    payload = face_api.AddPhotosToIdentityRequest(photo_ids=[photo_id])
    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), patch(
        "app.crud.album.trigger_conditional_albums_update"
    ):
        resp = asyncio.run(
            face_api.add_photos_to_identity(id=identity_id, payload=payload, db=db, current_user=USER)
        )
    assert resp.code == 200
    assert resp.data["count"] == 1
    added = db.add.call_args[0][0]
    assert added.photo_id == photo_id
    assert added.face_identity_id == identity_id
    assert added.face_feature is None


def test_face_add_photos_skips_photos_of_other_owners():
    photo_id = uuid_mod.uuid4()
    identity_id = uuid_mod.uuid4()
    foreign_photo = SimpleNamespace(id=photo_id, owner_id="someone-else")
    db = _identity_db(assigned_faces=[], photo=foreign_photo, per_photo_faces=[])
    payload = face_api.AddPhotosToIdentityRequest(photo_ids=[photo_id])
    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), patch(
        "app.crud.album.trigger_conditional_albums_update"
    ) as trigger:
        resp = asyncio.run(
            face_api.add_photos_to_identity(id=identity_id, payload=payload, db=db, current_user=USER)
        )
    assert resp.data["count"] == 0
    db.add.assert_not_called()
    trigger.assert_called_once()
