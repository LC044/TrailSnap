"""Nightly gap-fill tests for low-coverage API routers.

Targets (priority by nightly scan + §4.5 ordering):
* api/photo.py      (31.4% -> aim +20 percentage points)
* api/settings.py   (28.4% -> aim +20 pp)
* api/media.py      (42.5% -> aim +15 pp)
* api/face.py       (42.4% -> aim +15 pp)
* api/album.py      (50.8% -> aim +10 pp)

All endpoints are exercised through their handlers with `app.crud` / `db` /
`config_manager` patched so no Postgres / disk / network is touched.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

import app.crud.photo
from app.api import album as album_api
from app.api import face as face_api
from app.api import media as media_api
from app.api import photo as photo_api
from app.api import settings as settings_api
from app.core import config_manager as core_config_manager
from app.crud import album as crud_album
from app.crud import face as crud_face


pytestmark = pytest.mark.smoke


def _user(uid=None, *, is_superuser=False):
    return SimpleNamespace(id=uid or uuid4(), is_superuser=is_superuser)


# =====================================================================
# api/photo.py — batch_create_photos, delete_photo_tag, add_photo_tag
# =====================================================================


def test_batch_create_photos_normalises_items_and_delegates():
    db = MagicMock()
    user = _user()
    item = SimpleNamespace(
        photo={"title": "x"},
        file_path="/tmp/x.jpg",
        photo_id=uuid4(),
    )

    payload = SimpleNamespace(items=[item])
    with patch.object(
        app.crud.photo, "batch_create_photos", return_value=["id-1", "id-2"]
    ) as call:
        result = photo_api.batch_create_photos(
            batch_data=payload, db=db, current_user=user
        )

    call.assert_called_once()
    forwarded = call.call_args.args[1]
    assert forwarded[0]["photo"] == {"title": "x"}
    assert forwarded[0]["file_path"] == "/tmp/x.jpg"
    assert forwarded[0]["photo_id"] == item.photo_id
    assert call.call_args.kwargs["user_id"] == user.id
    assert "2" in result.data["message"]


def test_delete_photo_tag_rejects_non_owner():
    db = MagicMock()
    owner = _user()
    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4())  # different owner

    with patch.object(app.crud.photo, "get_photo", return_value=photo):
        with pytest.raises(HTTPException) as exc:
            photo_api.delete_photo_tag(
                photo_id=photo.id, tag_id=uuid4(), db=db, current_user=owner
            )

    assert exc.value.status_code == 403


def test_add_photo_tag_returns_404_for_missing_photo():
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(tag_name="beach", confidence=0.9)

    with patch.object(app.crud.photo, "get_photo", return_value=None):
        with pytest.raises(HTTPException) as exc:
            photo_api.add_photo_tag(
                photo_id=uuid4(), tag_data=payload, db=db, current_user=user
            )

    assert exc.value.status_code == 404


# =====================================================================
# api/settings.py — read_storage_root, update_storage_root,
#                   apply_filter, get_directories, add_directory, remove_directory
# =====================================================================


def test_read_storage_root_returns_helper_payload():
    db = MagicMock()
    user = _user()

    with patch.object(settings_api, "get_storage_root", return_value="D:/photos"):
        result = settings_api.read_storage_root(db=db, current_user=user)

    assert result == {"storage_root": "D:/photos"}


def test_update_storage_root_rejects_non_string_path():
    db = MagicMock()
    user = _user()

    with pytest.raises(HTTPException) as exc:
        settings_api.update_storage_root(
            payload={"storage_root": 123}, db=db, current_user=user
        )

    assert exc.value.status_code == 400


def test_update_storage_root_rejects_missing_directory():
    db = MagicMock()
    user = _user()

    with patch("app.api.settings.os.path.isdir", return_value=False):
        with pytest.raises(HTTPException) as exc:
            settings_api.update_storage_root(
                payload={"storage_root": "Z:/nope"}, db=db, current_user=user
            )

    assert exc.value.status_code == 400


def test_apply_filter_enqueues_background_task():
    user = _user()
    bg = BackgroundTasks()

    result = settings_api.apply_filter(background_tasks=bg, current_user=user)

    assert result == {"status": "started", "message": "Filter application started in background"}
    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    assert task.func is settings_api.apply_filter_task_bg
    assert task.args == (str(user.id),)


def test_get_directories_returns_primary_and_external_for_owner():
    db = MagicMock()
    user = _user()
    user.settings = {"storage": {"external_directories": ["/mnt/photos"]}}

    with patch.object(settings_api, "get_storage_root", return_value="/data/photos"):
        result = settings_api.get_directories(db=db, current_user=user, user_id="ignored")

    assert result == {"primary": "/data/photos", "external": ["/mnt/photos"]}


def test_add_directory_rejects_non_superuser():
    db = MagicMock()
    user = _user(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        settings_api.add_directory(
            payload={"path": "/data/x"}, db=db, current_user=user
        )

    assert exc.value.status_code == 403


def test_remove_directory_returns_current_when_no_settings():
    db = MagicMock()
    user = _user(is_superuser=True)
    user.settings = None

    with patch.object(settings_api, "get_storage_root", return_value="/data/photos"):
        result = settings_api.remove_directory(
            payload={"path": "/data/x"}, db=db, current_user=user
        )

    assert result == {"primary": "/data/photos", "external": []}


# =====================================================================
# api/media.py — _get_thumbnail_path prefers webp, falls back to jpg
# =====================================================================


def test_thumbnail_path_prefers_webp_when_present(tmp_path):
    db = MagicMock()
    user_id = uuid4()
    photo_id = uuid4()
    compact = str(photo_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    webp = base / f"{compact}-thumb.webp"
    webp.write_bytes(b"RIFF")

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        path = media_api._get_thumbnail_path(user_id, photo_id, db, size="small")

    assert path.endswith("-thumb.webp")


def test_thumbnail_path_falls_back_to_jpg(tmp_path):
    db = MagicMock()
    user_id = uuid4()
    photo_id = uuid4()
    compact = str(photo_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    jpg = base / f"{compact}-thumb.jpg"
    jpg.write_bytes(b"\xff\xd8")

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        path = media_api._get_thumbnail_path(user_id, photo_id, db, size="small")

    assert path.endswith("-thumb.jpg")


# =====================================================================
# api/face.py — list_identities, remove_photos_from_identity, rescan_identity
# =====================================================================


def test_list_identities_forwards_owner_and_paging():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(face_recognition_min_photos=2))

    with patch.object(
        core_config_manager.config_manager, "get_user_config", return_value=cfg
    ), patch.object(
        crud_face, "get_identities_with_details", return_value=["i1", "i2"]
    ) as call:
        result = face_api.list_identities(
            skip=5, limit=10, types=["named"], min_photos=3,
            db=db, current_user=user,
        )

    call.assert_called_once()
    kwargs = call.call_args.kwargs
    assert kwargs["owner_id"] == user.id
    assert kwargs["skip"] == 5
    assert kwargs["limit"] == 10
    assert result.code == 200
    assert result.data == ["i1", "i2"]


def test_list_identities_uses_config_min_when_unset():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(face_recognition_min_photos=4))

    with patch.object(
        core_config_manager.config_manager, "get_user_config", return_value=cfg
    ), patch.object(
        crud_face, "get_identities_with_details", return_value=[]
    ) as call:
        face_api.list_identities(
            skip=0, limit=20, types=["named"], min_photos=None,
            db=db, current_user=user,
        )

    assert call.call_args.kwargs["min_photos"] == 4


def test_remove_photos_from_identity_returns_404_when_missing():
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(photo_ids=[uuid4()])

    with patch.object(crud_face, "get_identity", return_value=None):
        result = face_api.remove_photos_from_identity(
            id=uuid4(), payload=payload, db=db, current_user=user
        )

    assert result.code == 404


def test_rescan_identity_returns_404_for_unknown_identity():
    db = MagicMock()
    user = _user()

    with patch.object(crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc:
            face_api.rescan_identity(id=uuid4(), db=db, current_user=user)

    assert exc.value.status_code == 404


# =====================================================================
# api/album.py — read_photos date filter, set_album_cover 404 paths,
#                delete_photo 403 path
# =====================================================================


def test_album_read_photos_forwards_date_filters():
    db = MagicMock()
    user = _user()
    album_id = uuid4()
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 31)

    with patch.object(
        app.crud.photo, "get_photos", return_value=["p1"]
    ) as call:
        result = album_api.read_photos(
            album_id=album_id, skip=0, limit=10,
            start_time=start, end_time=end,
            db=db, current_user=user,
        )

    kwargs = call.call_args.kwargs
    assert kwargs["start_time"] is start
    assert kwargs["end_time"] is end
    assert kwargs["album_id"] == album_id
    assert result.data == ["p1"]


def test_album_set_album_cover_returns_404_when_album_missing():
    db = MagicMock()
    user = _user()
    album_id = uuid4()

    with patch.object(crud_album, "get_album", return_value=None):
        result = album_api.set_album_cover(
            album_id=album_id, payload={"photo_id": str(uuid4())},
            db=db, current_user=user,
        )

    assert result.code == 404


def test_album_delete_photo_returns_403_for_non_owner():
    db = MagicMock()
    user = _user()
    album = SimpleNamespace(id=uuid4(), owner_id=uuid4())  # different owner

    with patch.object(crud_album, "get_album", return_value=album):
        result = album_api.delete_photo(
            album_id=album.id, photo_id=uuid4(), db=db, current_user=user
        )

    assert result.code == 403
