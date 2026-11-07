"""Round 2026-08-26 coverage gaps for app/crud/photo.py update_photo_metadata."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _make_photo(owner_id):
    return SimpleNamespace(id="photo-1", owner_id=owner_id)


def _make_metadata_obj():
    return SimpleNamespace(photo_id=None, exif_info=None)


def test_update_photo_metadata_updates_existing_row_and_skips_trigger_when_no_user():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()
    existing.exif_info = "old"

    update = SimpleNamespace(
        model_dump=lambda exclude_unset=False, exclude=None: {"exif_info": "new"},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id=None)

    assert result is existing
    assert existing.exif_info == "new"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(existing)


def test_update_photo_metadata_returns_none_when_photo_missing():
    from app.crud import photo as crud

    db = MagicMock()

    update = SimpleNamespace(model_dump=lambda exclude_unset=False, exclude=None: {"exif_info": "x"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=None):
        result = crud.update_photo_metadata(db, "missing", update, user_id="u")

    assert result is None
    db.commit.assert_not_called()


def test_update_photo_metadata_creates_new_row_when_metadata_missing():
    from app.crud import photo as crud

    db = MagicMock()
    photo_obj = _make_photo("user-x")

    update = SimpleNamespace(model_dump=lambda exclude_unset=False, exclude=None: {"exif_info": "fresh"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=photo_obj), \
         patch.object(crud, "PhotoMetadata", SimpleNamespace):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id=None)

    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert result is not None


def test_update_photo_metadata_returns_none_when_user_does_not_own_photo():
    from app.crud import photo as crud

    db = MagicMock()
    photo_obj = _make_photo(owner_id="user-other")

    update = SimpleNamespace(model_dump=lambda exclude_unset=False, exclude=None: {"exif_info": "x"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=photo_obj):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id="user-self")

    assert result is None
    db.commit.assert_not_called()


def test_update_photo_metadata_triggers_conditional_albums_update_for_owned_photo():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()

    update = SimpleNamespace(model_dump=lambda exclude_unset=False, exclude=None: {"exif_info": "y"})

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")

    trigger.assert_called_once_with(db, "user-1", ["photo-1"])


# ------------------------- write_to_file GPS 写回联动 -------------------------
# REQ-223：勾选 write_to_file 时数据库更新后尽力写回原文件并同步 md5；
# 未勾选时行为与历史版本完全一致（不触碰文件）。

def test_update_photo_metadata_without_write_to_file_never_touches_files():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()

    update = SimpleNamespace(
        write_to_file=False,
        model_dump=lambda exclude_unset=False, exclude=None: {"latitude": 10.0, "longitude": 20.0},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "write_gps_to_file") as write:
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")

    write.assert_not_called()
    assert getattr(existing, '_write_back', None) is None


def test_update_photo_metadata_write_to_file_marks_written_and_updates_md5(tmp_path):
    from PIL import Image
    from app.crud import photo as crud

    real_file = tmp_path / "a.jpg"
    Image.new("RGB", (4, 4), "red").save(real_file)

    db = MagicMock()
    existing = _make_metadata_obj()
    photo_obj = SimpleNamespace(
        id="photo-1", owner_id="user-1", file_path=str(real_file),
        md5="old", size=10,
    )

    update = SimpleNamespace(
        write_to_file=True,
        model_dump=lambda exclude_unset=False, exclude=None: {"latitude": 10.0, "longitude": 20.0},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "get_photo", return_value=photo_obj), \
         patch.object(crud, "write_gps_to_file") as write, \
         patch.object(crud, "update_photo_md5", return_value="new-md5") as md5:
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")

    write.assert_called_once_with(str(real_file), 10.0, 20.0)
    md5.assert_called_once()
    # 数据库更新已提交；写回成功后再 commit md5
    assert db.commit.call_count >= 2
    assert object.__getattribute__(existing, '_write_back') == 'written'


def test_update_photo_metadata_write_back_failure_does_not_rollback_db(tmp_path):
    from PIL import Image
    from app.crud import photo as crud

    real_file = tmp_path / "a.jpg"
    Image.new("RGB", (4, 4), "red").save(real_file)

    db = MagicMock()
    existing = _make_metadata_obj()
    existing.latitude = 10.0
    photo_obj = SimpleNamespace(id="photo-1", owner_id="user-1", file_path=str(real_file))

    update = SimpleNamespace(
        write_to_file=True,
        model_dump=lambda exclude_unset=False, exclude=None: {"latitude": 10.0, "longitude": 20.0},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "get_photo", return_value=photo_obj), \
         patch.object(crud, "write_gps_to_file", side_effect=RuntimeError("disk error")):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")

    # 数据库字段已更新且不被回滚
    assert result is existing
    assert existing.latitude == 10.0
    assert object.__getattribute__(existing, '_write_back') == 'failed'


def test_update_photo_metadata_write_back_skips_unsupported_or_missing_files():
    from app.crud import photo as crud
    from app.utils.gps_writeback import WriteBackUnsupported

    db = MagicMock()
    existing = _make_metadata_obj()

    update = SimpleNamespace(
        write_to_file=True,
        model_dump=lambda exclude_unset=False, exclude=None: {"latitude": 10.0, "longitude": 20.0},
    )

    # 文件不存在 → skipped，不触发写回异常
    photo_obj = SimpleNamespace(id="photo-1", owner_id="user-1", file_path="D:/ghost.jpg")
    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "get_photo", return_value=photo_obj):
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")
    assert object.__getattribute__(existing, '_write_back') == 'skipped'

    # 不支持的格式（HEIC）→ skipped 而非 failed
    import tempfile, os
    from PIL import Image
    tmp = tempfile.mkdtemp()
    heic = os.path.join(tmp, 'x.heic')
    open(heic, 'wb').write(b'ftypheic')
    photo_obj2 = SimpleNamespace(id="photo-1", owner_id="user-1", file_path=heic)
    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "get_photo", return_value=photo_obj2):
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")
    assert object.__getattribute__(existing, '_write_back') == 'skipped'


def test_update_photo_metadata_write_back_skips_foreign_photo():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()
    # 他人照片：get_photo_metadata 返回 None，get_photo 的 owner 不匹配
    photo_obj = SimpleNamespace(id="photo-1", owner_id="user-other", file_path="D:/Photos/a.jpg")

    update = SimpleNamespace(
        write_to_file=True,
        model_dump=lambda exclude_unset=False, exclude=None: {"latitude": 10.0, "longitude": 20.0},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch.object(crud, "get_photo", return_value=photo_obj), \
         patch.object(crud, "write_gps_to_file") as write:
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-self")

    # 权限不匹配 → skipped，且不发生任何文件写操作
    write.assert_not_called()
    assert object.__getattribute__(existing, '_write_back') == 'skipped'
