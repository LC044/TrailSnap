from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.service import storage, user_storage


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_storage_root_is_isolated_per_user(tmp_path):
    first = uuid4()
    second = uuid4()

    with patch.object(user_storage, "DEFAULT_STORAGE_BASE", str(tmp_path)):
        user_storage._STORAGE_BASE_CACHE.clear()
        first_root = storage._get_storage_root(first)
        second_root = storage._get_storage_root(second)

    assert first_root != second_root
    assert first_root.endswith(f"users{user_storage.os.sep}{first}")
    assert second_root.endswith(f"users{user_storage.os.sep}{second}")
    for root in (first_root, second_root):
        assert (user_storage.os.path.isdir(user_storage.os.path.join(root, "uploads")))
        assert (user_storage.os.path.isdir(user_storage.os.path.join(root, "thumbnails")))
        assert (user_storage.os.path.isdir(user_storage.os.path.join(root, "config")))


def test_save_upload_file_accepts_nested_folder_and_blocks_traversal(tmp_path):
    upload = SimpleNamespace(filename="portrait.jpg", file=MagicMock())
    upload.file.read.side_effect = [b"image", b""]

    with patch.object(storage, "_get_storage_root", return_value=str(tmp_path)):
        result = storage.save_upload_file(upload, uuid4(), uuid4(), "家人/小明")

    assert result == str(tmp_path / "uploads" / "家人" / "小明" / "portrait.jpg")
    with pytest.raises(ValueError):
        storage.save_upload_file(upload, uuid4(), uuid4(), "../other-user")


def test_legacy_migration_moves_only_owned_uploads_and_thumbnails(tmp_path):
    user_id = uuid4()
    photo_id = uuid4()
    data_dir = tmp_path / "data"
    legacy_base = data_dir / "uploads"
    settings = {"storage": {"photo_storage_path": "./data/uploads"}}
    legacy_photo = legacy_base / "uploads" / "2025" / "08" / "old.jpg"
    legacy_photo.parent.mkdir(parents=True)
    legacy_photo.write_bytes(b"photo")
    compact = photo_id.hex
    legacy_thumb = legacy_base / "thumbnails" / compact[:2] / compact[2:4] / f"{compact}.webp"
    legacy_thumb.parent.mkdir(parents=True)
    legacy_thumb.write_bytes(b"thumb")
    external = tmp_path / f"external-{photo_id}.jpg"
    external.write_bytes(b"external")

    user = SimpleNamespace(id=user_id, settings=settings)
    uploaded = SimpleNamespace(id=photo_id, owner_id=user_id, file_path=str(legacy_photo))
    external_photo = SimpleNamespace(id=uuid4(), owner_id=user_id, file_path=str(external))
    db = MagicMock()
    db.query.return_value.all.return_value = [user]
    db.query.return_value.filter.return_value.all.return_value = [uploaded, external_photo]

    with (
        patch.object(user_storage, "DEFAULT_STORAGE_BASE", str(data_dir)),
        patch.object(user_storage, "LEGACY_DEFAULT_STORAGE_BASE", str(legacy_base)),
    ):
        result = user_storage.migrate_legacy_user_storage(db)
    user_root = data_dir / "users" / str(user_id)

    assert result["photos"] == 1
    assert uploaded.file_path == str(user_root / "uploads" / "2025" / "08" / "old.jpg")
    assert (user_root / "uploads" / "2025" / "08" / "old.jpg").read_bytes() == b"photo"
    assert (user_root / "thumbnails" / compact[:2] / compact[2:4] / f"{compact}.webp").read_bytes() == b"thumb"
    assert external.read_bytes() == b"external"
    assert (user_root / "config" / "settings.json").is_file()
    assert not (legacy_base / "uploads").exists()
    assert not (legacy_base / "thumbnails").exists()
    assert not legacy_base.exists()
    assert user.settings["storage"]["photo_storage_path"] == str(data_dir)
    assert result["removed_directories"] > 0
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_legacy_cleanup_preserves_nonempty_directories(tmp_path):
    legacy_uploads = tmp_path / "uploads"
    empty_nested = legacy_uploads / "empty" / "nested"
    empty_nested.mkdir(parents=True)
    keep = legacy_uploads / "unknown.bin"
    keep.write_bytes(b"keep")

    removed = user_storage._remove_empty_tree(str(legacy_uploads))

    assert removed == 2
    assert legacy_uploads.is_dir()
    assert keep.read_bytes() == b"keep"


def test_create_and_list_upload_folders_are_user_scoped(tmp_path):
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    root = tmp_path / "users" / str(user.id)

    with patch.object(media_api, "_get_storage_root", return_value=str(root)):
        created = media_api.create_upload_folder({"path": "家人/小明"}, db=db, current_user=user)
        listed = media_api.list_upload_folders(db=db, current_user=user)

    assert created.data == {"path": "家人/小明"}
    assert listed.data == {"folders": ["家人", "家人/小明"]}

    with patch.object(media_api, "_get_storage_root", return_value=str(root)):
        with pytest.raises(HTTPException) as exc_info:
            media_api.create_upload_folder({"path": "../escape"}, db=db, current_user=user)
    assert exc_info.value.status_code == 400


def test_delete_user_layout_removes_only_target_user(tmp_path):
    first = uuid4()
    second = uuid4()
    settings = {"storage": {"photo_storage_path": str(tmp_path)}}
    first_root = user_storage.ensure_user_layout(first, str(tmp_path))
    second_root = user_storage.ensure_user_layout(second, str(tmp_path))

    user_storage.delete_user_layout(first, settings)

    assert not user_storage.os.path.exists(first_root)
    assert user_storage.os.path.isdir(second_root)
