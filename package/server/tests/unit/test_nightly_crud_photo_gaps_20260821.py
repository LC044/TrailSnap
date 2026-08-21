"""Unit tests covering 2026-08-21 nightly coverage gap scan.

Targets `app/crud/photo.py` high-miss functions not exercised by the
2026-08-12 nightly round:
* ``batch_create_photos`` -- file_path dedup (existing + in-batch) + bulk
  insert path
* ``save_and_create_photo`` -- file-extension → FileType dispatch
* ``replace_photo_file`` -- delete old file + thumbnail regen + path update

MagicMock-based: avoids the SQLite pollution that breaks real-DB unit
fixtures (see automation memory 2026-08-19). Side-effect helpers that
fan out to other CRUD modules / task manager are patched at their source
module because crud.photo imports them lazily inside function bodies.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke]


def _photo_create(filename="a.jpg"):
    return SimpleNamespace(
        filename=filename,
        photo_time=datetime(2026, 8, 21, 12, 0, 0),
        file_type="image",
        size=1024,
        width=800,
        height=600,
        duration=0.0,
    )


# crud/photo.py does ``from app.crud.album import ...`` lazily inside the
# function bodies, so the patch target must be the source module.
_ALBUM_PATCHES = patch.multiple(
    "app.crud.album",
    trigger_conditional_albums_update=MagicMock(),
    _update_album_photo_count=MagicMock(),
)


def _patch_task_manager():
    """Stub TaskManager.get_instance().add_tasks so replace_photo_file
    doesn't fan out to the task pipeline."""
    fake_mgr = MagicMock()
    fake_mgr.get_instance.return_value = fake_mgr
    return patch("app.service.task_manager.TaskManager", fake_mgr)


# ---------------------------------------------------------------------------
# batch_create_photos
# ---------------------------------------------------------------------------


def test_batch_create_photos_dedupes_existing_and_inbatch():
    """Mixed batch: one already in DB, one duplicate of another in batch,
    one new. dedup keeps b.jpg (first) + c.jpg; only those are inserted."""
    from app.crud import photo as crud_photo

    db = MagicMock()
    user_id = uuid4()
    b_photo_id = uuid4()
    photo_id_new = uuid4()

    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.filter.return_value = chain
    chain.all.return_value = [("/data/a.jpg",)]

    photos_data = [
        {"photo": _photo_create("a.jpg"), "metadata": SimpleNamespace(exif_info="exif-a"),
         "photo_id": uuid4(), "file_path": "/data/a.jpg"},  # already in DB -> skip
        {"photo": _photo_create("b.jpg"), "metadata": None,
         "photo_id": b_photo_id, "file_path": "/data/b.jpg"},  # first occurrence kept
        {"photo": _photo_create("b.jpg"), "metadata": None,
         "photo_id": uuid4(), "file_path": "/data/b.jpg"},  # in-batch dup -> skipped
        {"photo": _photo_create("c.jpg"), "metadata": SimpleNamespace(exif_info="exif-c"),
         "photo_id": photo_id_new, "file_path": "/data/c.jpg"},  # new -> inserted
    ]

    with _ALBUM_PATCHES:
        inserted = crud_photo.batch_create_photos(db, photos_data, user_id=user_id)

    assert inserted == [b_photo_id, photo_id_new]
    # bulk_save_objects called once for photos, once for metadatas (b.jpg had None)
    assert db.bulk_save_objects.call_count == 2
    db.commit.assert_called_once()


def test_batch_create_photos_returns_empty_for_empty_or_all_dup():
    """Empty list and all-duplicate paths return [] without committing."""
    from app.crud import photo as crud_photo

    db = MagicMock()
    assert crud_photo.batch_create_photos(db, []) == []

    db2 = MagicMock()
    chain = db2.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.all.return_value = [("/data/x.jpg",)]
    items = [
        {"photo": _photo_create("x.jpg"), "metadata": None,
         "photo_id": uuid4(), "file_path": "/data/x.jpg"},
    ]
    with _ALBUM_PATCHES:
        result = crud_photo.batch_create_photos(db2, items, user_id=uuid4())
    assert result == []
    db2.bulk_save_objects.assert_not_called()


# ---------------------------------------------------------------------------
# save_and_create_photo
# ---------------------------------------------------------------------------


def test_save_and_create_photo_picks_video_for_mp4_extension():
    """A .mp4 filename routes through the video branch: FileType.video."""
    from app.crud import photo as crud_photo
    from app.db.models.photo import FileType

    db = MagicMock()
    photo_id = uuid4()
    user_id = uuid4()

    with _ALBUM_PATCHES, \
         patch.object(crud_photo.storage, "generate_thumbnail") as gen_thumb, \
         patch.object(crud_photo.storage, "get_file_size", return_value=2048), \
         patch.object(crud_photo.storage, "get_image_dimensions", return_value=(1920, 1080, 30.0)), \
         patch.object(crud_photo, "extract_metadata",
                      return_value={"photo_time": datetime(2026, 8, 21, 12, 0, 0)}):
        db_photo = crud_photo.save_and_create_photo(
            db,
            file_path="/data/clip.mp4",
            file_name="clip.mp4",
            album_id=None,
            photo_id=photo_id,
            user_id=user_id,
        )

    gen_thumb.assert_called_once_with(user_id, "/data/clip.mp4", photo_id)
    assert db_photo.id == photo_id
    assert db_photo.file_path == "/data/clip.mp4"
    assert db_photo.filename == "clip.mp4"
    assert db_photo.file_type == FileType.video
    db.add.assert_called_once_with(db_photo)
    # create_photo commits once + save_and_create_photo commits again for
    # PhotoMetadata pre-create, so total commit count is 2.
    assert db.commit.call_count == 2
    db.refresh.assert_called_once_with(db_photo)


def test_save_and_create_photo_defaults_to_image_for_jpg():
    """Non-video extension falls through to the default image branch."""
    from app.crud import photo as crud_photo
    from app.db.models.photo import FileType

    db = MagicMock()
    photo_id = uuid4()

    with _ALBUM_PATCHES, \
         patch.object(crud_photo.storage, "generate_thumbnail"), \
         patch.object(crud_photo.storage, "get_file_size", return_value=512), \
         patch.object(crud_photo.storage, "get_image_dimensions", return_value=(640, 480, 0.0)), \
         patch.object(crud_photo, "extract_metadata",
                      return_value={"photo_time": datetime(2026, 8, 21, 12, 0, 0)}):
        db_photo = crud_photo.save_and_create_photo(
            db,
            file_path="/data/p.jpg",
            file_name="p.jpg",
            album_id=None,
            photo_id=photo_id,
            user_id=None,
        )

    assert db_photo.file_type == FileType.image


# ---------------------------------------------------------------------------
# replace_photo_file
# ---------------------------------------------------------------------------


def test_replace_photo_file_removes_old_and_regenerates_thumbnail(tmp_path):
    """Old path differs and file exists on disk -> deleted; db_photo updated;
    thumbnail regenerated."""
    from app.crud import photo as crud_photo

    old = tmp_path / "old.jpg"
    old.write_bytes(b"old")
    new = tmp_path / "new.jpg"

    db_photo = SimpleNamespace(
        id=uuid4(),
        file_path=str(old),
        filename="old.jpg",
        width=100,
        height=100,
    )
    db = MagicMock()

    with _ALBUM_PATCHES, _patch_task_manager(), \
         patch.object(crud_photo.storage, "delete_thumbnails") as del_thumb, \
         patch.object(crud_photo.storage, "generate_thumbnail") as gen_thumb, \
         patch.object(crud_photo.storage, "get_image_dimensions", return_value=(800, 600, 0.0)), \
         patch.object(crud_photo.storage, "get_file_size", return_value=4096):
        crud_photo.replace_photo_file(db, db_photo, str(new), user_id=uuid4())

    assert not old.exists()
    assert db_photo.file_path == str(new)
    assert db_photo.filename == "new.jpg"
    assert db_photo.width == 800
    assert db_photo.height == 600
    del_thumb.assert_called_once()
    gen_thumb.assert_called_once()
    # At least the replace_photo_file commit + task_manager.add_tasks commit.
    assert db.commit.call_count >= 1


def test_replace_photo_file_noop_delete_when_path_unchanged(tmp_path):
    """If new path == old path, the old file is NOT deleted (delete_thumbnails is still called -- only os.remove is gated on path inequality)."""
    from app.crud import photo as crud_photo

    same = tmp_path / "same.jpg"
    same.write_bytes(b"x")

    db_photo = SimpleNamespace(
        id=uuid4(),
        file_path=str(same),
        filename="same.jpg",
        width=10,
        height=10,
    )
    db = MagicMock()
    user_id = uuid4()

    with _ALBUM_PATCHES, _patch_task_manager(), \
         patch.object(crud_photo.storage, "delete_thumbnails") as del_thumb, \
         patch.object(crud_photo.storage, "generate_thumbnail") as gen_thumb, \
         patch.object(crud_photo.storage, "get_image_dimensions", return_value=(10, 10, 0.0)), \
         patch.object(crud_photo.storage, "get_file_size", return_value=1):
        crud_photo.replace_photo_file(db, db_photo, str(same), user_id=user_id)

    assert same.exists()
    # delete_thumbnails is always invoked -- the thumbnail cache is keyed by
    # photo id and gets invalidated regardless of whether the on-disk path
    # changed.
    del_thumb.assert_called_once_with(user_id, db_photo.id)
    gen_thumb.assert_called_once_with(user_id, str(same), db_photo.id)
    # replace_photo_file always rewrites dimensions / size from new file.
    assert db_photo.width == 10
    assert db_photo.height == 10
    # replace_photo_file commit + (patched) task_manager.add_tasks commit.
    assert db.commit.call_count >= 1
