"""Unit tests covering 2026-08-12 nightly coverage gap scan (round 7).

Modules exercised (MagicMock + async runner):
* app/api/photo.py -- batch_transfer_photos (move/copy/collision/403),
  replace_photo_file (404/403/400-video/success),
  batch_update_photos_tags (add/remove/skip-non-owned),
  update_photo (404/success)
* app/api/settings.py -- get_directories_tree (no-path roots / traversal 403 /
  subdir leaf detection)

All routers were either not previously exercised or only had 30-40% line
coverage; these tests are pure unit tests with MagicMock dependency injection,
no DB / filesystem access outside pytest tmp_path.
"""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api import photo as photo_api
from app.api import settings as settings_api

pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4(), is_superuser=False)


def _run(coro):
    """Run an async coroutine with a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# app/api/photo.py::batch_transfer_photos
# ---------------------------------------------------------------------------


def test_batch_transfer_move_succeeds_and_updates_path(tmp_path):
    user = _user()
    photo_id = uuid4()
    src_file = tmp_path / "source.jpg"
    src_file.write_bytes(b"raw")
    user_root = tmp_path / "users" / str(user.id)
    target_dir = user_root / "uploads" / "dest"
    photo = SimpleNamespace(
        id=photo_id,
        file_path=str(src_file),
        filename="source.jpg",
        owner_id=user.id,
    )
    db = MagicMock()
    cfg = SimpleNamespace(
        storage=SimpleNamespace(
            photo_storage_path=str(tmp_path),
            external_directories=[],
        )
    )
    data = SimpleNamespace(
        photo_ids=[photo_id],
        target_path=str(target_dir),
        action="move",
    )
    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg) as gc, \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(user_root)), \
         patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]) as gpb:
        result = photo_api.batch_transfer_photos(data=data, db=db, current_user=user)
    gc.assert_called_once_with(user.id, db)
    gpb.assert_called_once_with(db, data.photo_ids, user_id=user.id)
    assert result.code == 0
    assert data.action in result.data["message"]
    moved = target_dir / "source.jpg"
    assert moved.exists()
    assert photo.file_path == str(moved)


def test_batch_transfer_rejects_target_outside_allowed_roots(tmp_path):
    user = _user()
    data = SimpleNamespace(
        photo_ids=[uuid4()],
        target_path=str(tmp_path / "outside_target"),
        action="move",
    )
    cfg = SimpleNamespace(
        storage=SimpleNamespace(
            photo_storage_path=str(tmp_path / "primary"),
            external_directories=[],
        )
    )
    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_transfer_photos(data=data, db=MagicMock(), current_user=user)
    assert exc.value.status_code == 403
    assert "not allowed" in exc.value.detail.lower()


def test_batch_transfer_collision_appends_uuid_suffix(tmp_path):
    user = _user()
    photo_id = uuid4()
    src_file = tmp_path / "dup.jpg"
    src_file.write_bytes(b"raw")
    user_root = tmp_path / "users" / str(user.id)
    target_dir = user_root / "uploads" / "dest"
    target_dir.mkdir(parents=True)
    existing = target_dir / "dup.jpg"
    existing.write_bytes(b"old")
    photo = SimpleNamespace(
        id=photo_id,
        file_path=str(src_file),
        filename="dup.jpg",
        owner_id=user.id,
    )
    db = MagicMock()
    cfg = SimpleNamespace(
        storage=SimpleNamespace(
            photo_storage_path=str(tmp_path),
            external_directories=[],
        )
    )
    data = SimpleNamespace(
        photo_ids=[photo_id],
        target_path=str(target_dir),
        action="move",
    )
    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(user_root)), \
         patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]):
        photo_api.batch_transfer_photos(data=data, db=db, current_user=user)
    # original target file remains untouched (suffix applied)
    assert existing.read_bytes() == b"old"
    matches = list(target_dir.glob("dup_*.jpg"))
    assert len(matches) == 1
    assert matches[0].read_bytes() == b"raw"
    assert photo.file_path == str(matches[0])


# ---------------------------------------------------------------------------
# app/api/photo.py::replace_photo_file
# ---------------------------------------------------------------------------


def test_replace_photo_file_404_when_photo_missing():
    db = MagicMock()
    user = _user()
    photo_id = uuid4()
    upload = SimpleNamespace(filename="a.jpg")
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=None):
        with pytest.raises(HTTPException) as exc:
            _run(photo_api.replace_photo_file(photo_id=photo_id, file=upload, db=db, current_user=user))
    assert exc.value.status_code == 404


def test_replace_photo_file_403_when_not_owner():
    db = MagicMock()
    owner_id = uuid4()
    attacker = _user()
    photo_id = uuid4()
    db_photo = SimpleNamespace(
        id=photo_id,
        owner_id=owner_id,
        file_type=SimpleNamespace(value="image"),
    )
    upload = SimpleNamespace(filename="a.jpg")
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=db_photo):
        with pytest.raises(HTTPException) as exc:
            _run(photo_api.replace_photo_file(photo_id=photo_id, file=upload, db=db, current_user=attacker))
    assert exc.value.status_code == 403


def test_replace_photo_file_400_when_video():
    from app.db.models.photo import FileType

    db = MagicMock()
    user = _user()
    photo_id = uuid4()
    db_photo = SimpleNamespace(
        id=photo_id,
        owner_id=user.id,
        file_type=FileType.video,
    )
    upload = SimpleNamespace(filename="clip.mp4")
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=db_photo):
        with pytest.raises(HTTPException) as exc:
            _run(photo_api.replace_photo_file(photo_id=photo_id, file=upload, db=db, current_user=user))
    assert exc.value.status_code == 400
    assert "video" in exc.value.detail.lower()


def test_replace_photo_file_success_returns_replaced_record():
    from app.db.models.photo import FileType

    db = MagicMock()
    user = _user()
    photo_id = uuid4()
    new_path = "/tmp/replaced/file.jpg"
    replaced_record = SimpleNamespace(id=photo_id, file_path=new_path)
    db_photo = SimpleNamespace(
        id=photo_id,
        owner_id=user.id,
        file_type=FileType.image,
    )
    upload = SimpleNamespace(filename="file.jpg")
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=db_photo), \
         patch.object(photo_api.storage, "save_upload_file", return_value=new_path) as save, \
         patch.object(photo_api.app.crud.photo, "replace_photo_file", return_value=replaced_record) as replace:
        result = _run(photo_api.replace_photo_file(photo_id=photo_id, file=upload, db=db, current_user=user))
    save.assert_called_once()
    replace.assert_called_once_with(db, db_photo, new_path, user.id)
    assert result.code == 0
    assert result.data is replaced_record


# ---------------------------------------------------------------------------
# app/api/photo.py::batch_update_photos_tags
# ---------------------------------------------------------------------------


def test_batch_update_tags_add_calls_tag_crud_per_tag():
    user = _user()
    owned = SimpleNamespace(id=uuid4(), owner_id=user.id)
    db = MagicMock()
    data = SimpleNamespace(
        photo_ids=[owned.id],
        action="add",
        tags=["sunset", "travel"],
    )
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=owned) as gp, \
         patch.object(photo_api.crud_tag, "add_tag_to_photo", return_value=None) as add:
        result = photo_api.batch_update_photos_tags(data=data, db=db, current_user=user)
    gp.assert_called_once_with(db, owned.id)
    assert add.call_count == 2
    add.assert_any_call(db, owned.id, "sunset", 1.0, owner_id=user.id)
    add.assert_any_call(db, owned.id, "travel", 1.0, owner_id=user.id)
    assert result.code == 0
    assert "Successfully updated" in result.data["message"]


def test_batch_update_tags_remove_skips_unregistered_tag():
    user = _user()
    owned = SimpleNamespace(id=uuid4(), owner_id=user.id)
    db = MagicMock()
    data = SimpleNamespace(
        photo_ids=[owned.id],
        action="remove",
        tags=["missing-tag"],
    )
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=owned), \
         patch.object(photo_api.crud_tag, "get_tag_by_name", return_value=None) as gtn, \
         patch.object(photo_api.crud_tag, "remove_tag_from_photo") as rm:
        photo_api.batch_update_photos_tags(data=data, db=db, current_user=user)
    gtn.assert_called_once_with(db, "missing-tag")
    rm.assert_not_called()


def test_batch_update_tags_skips_photos_not_owned():
    user = _user()
    foreign = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    db = MagicMock()
    data = SimpleNamespace(
        photo_ids=[foreign.id],
        action="add",
        tags=["x"],
    )
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=foreign), \
         patch.object(photo_api.crud_tag, "add_tag_to_photo") as add:
        result = photo_api.batch_update_photos_tags(data=data, db=db, current_user=user)
    add.assert_not_called()
    assert "0 photos" in result.data["message"]


# ---------------------------------------------------------------------------
# app/api/photo.py::update_photo
# ---------------------------------------------------------------------------


def test_update_photo_404_when_crud_returns_none():
    db = MagicMock()
    user = _user()
    photo_id = uuid4()
    payload = SimpleNamespace(filename="new.jpg")
    with patch.object(photo_api.app.crud.photo, "update_photo", return_value=None) as up:
        with pytest.raises(HTTPException) as exc:
            photo_api.update_photo(photo_id=photo_id, photo=payload, db=db, current_user=user)
    up.assert_called_once_with(db, photo_id, payload, user_id=user.id)
    assert exc.value.status_code == 404


def test_update_photo_success_returns_record():
    db = MagicMock()
    user = _user()
    photo_id = uuid4()
    payload = SimpleNamespace(filename="new.jpg")
    record = SimpleNamespace(id=photo_id, filename="new.jpg")
    with patch.object(photo_api.app.crud.photo, "update_photo", return_value=record):
        result = photo_api.update_photo(photo_id=photo_id, photo=payload, db=db, current_user=user)
    assert result.code == 0
    assert result.data is record


# ---------------------------------------------------------------------------
# app/api/settings.py::get_directories_tree
# ---------------------------------------------------------------------------


def test_get_directories_tree_no_path_returns_roots(tmp_path):
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    primary = user_root / "uploads"
    primary.mkdir(parents=True)
    external = tmp_path / "extra"
    external.mkdir()
    db = MagicMock()
    cfg = SimpleNamespace(storage=SimpleNamespace(external_directories=[str(external)]))
    with patch.object(settings_api, "_get_storage_root", return_value=str(user_root)), \
         patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        result = settings_api.get_directories_tree(path=None, db=db, current_user=user)
    assert "directories" in result
    paths = {d["path"] for d in result["directories"]}
    assert os.path.abspath(str(primary)) in paths
    assert os.path.abspath(str(external)) in paths
    for d in result["directories"]:
        assert d["is_leaf"] is False


def test_get_directories_tree_rejects_path_traversal(tmp_path):
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    primary = user_root / "uploads"
    primary.mkdir(parents=True)
    db = MagicMock()
    cfg = SimpleNamespace(storage=SimpleNamespace(external_directories=[]))
    with patch.object(settings_api, "_get_storage_root", return_value=str(user_root)), \
         patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc:
            settings_api.get_directories_tree(path=str(tmp_path / "outside"), db=db, current_user=user)
    assert exc.value.status_code == 403
    assert "not allowed" in exc.value.detail.lower()


def test_get_directories_tree_404_for_missing_dir(tmp_path):
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    primary = user_root / "uploads"
    primary.mkdir(parents=True)
    db = MagicMock()
    cfg = SimpleNamespace(storage=SimpleNamespace(external_directories=[]))
    with patch.object(settings_api, "_get_storage_root", return_value=str(user_root)), \
         patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc:
            settings_api.get_directories_tree(path=str(primary / "ghost"), db=db, current_user=user)
    assert exc.value.status_code == 404


def test_get_directories_tree_subdir_returns_inner_dirs(tmp_path):
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    uploads = user_root / "uploads"
    primary = uploads / "vacation"
    primary.mkdir(parents=True)
    (primary / "beach").mkdir()
    (primary / "mountain").mkdir()
    (primary / "raw.jpg").write_bytes(b"raw")
    db = MagicMock()
    cfg = SimpleNamespace(storage=SimpleNamespace(external_directories=[]))
    with patch.object(settings_api, "_get_storage_root", return_value=str(user_root)), \
         patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        result = settings_api.get_directories_tree(path=str(primary), db=db, current_user=user)
    names = {d["name"] for d in result["directories"]}
    assert {"beach", "mountain"}.issubset(names)
