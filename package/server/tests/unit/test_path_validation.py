import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.crud import photo as photo_crud
from app.schemas.photo import PhotoUpdate
from app.utils.path_validation import validate_filename, validate_target_path


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_rejects_path_separator_in_filename(tmp_path):
    with pytest.raises(ValueError, match="路径分隔符"):
        validate_filename("nested/photo.jpg", str(tmp_path))


def test_rejects_filename_over_filesystem_byte_limit(tmp_path):
    with patch("app.utils.path_validation.os.name", "posix"), patch(
        "app.utils.path_validation._pathconf_limit", return_value=10
    ):
        with pytest.raises(ValueError, match="10 字节"):
            validate_filename("四个汉字.jpg", str(tmp_path))


def test_accepts_long_total_path_when_filesystem_limit_allows_it(tmp_path):
    target = os.path.join(str(tmp_path), *("folder" for _ in range(50)), "photo.jpg")
    with patch("app.utils.path_validation.os.name", "posix"), patch(
        "app.utils.path_validation._pathconf_limit", side_effect=[255, 4096]
    ):
        validate_target_path(target)


def test_photo_schema_rejects_filename_over_database_limit():
    with pytest.raises(ValidationError):
        PhotoUpdate(filename="x" * 256)


def test_failed_physical_rename_does_not_change_database_fields(tmp_path):
    source = tmp_path / "old.jpg"
    source.write_bytes(b"photo")
    owner_id = uuid4()
    db_photo = SimpleNamespace(
        owner_id=owner_id,
        file_path=str(source),
        filename="old.jpg",
        photo_time=None,
    )
    db = MagicMock()

    with patch.object(photo_crud, "get_photo", return_value=db_photo), patch.object(
        photo_crud.os, "rename", side_effect=OSError("path too long")
    ):
        with pytest.raises(ValueError, match="修改原文件失败"):
            photo_crud.update_photo(
                db,
                uuid4(),
                PhotoUpdate(filename="new.jpg", modify_original_file=True),
                user_id=owner_id,
            )

    assert db_photo.filename == "old.jpg"
    assert db_photo.file_path == str(source)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_missing_original_file_does_not_create_metadata_only_rename(tmp_path):
    owner_id = uuid4()
    db_photo = SimpleNamespace(
        owner_id=owner_id,
        file_path=str(tmp_path / "missing.jpg"),
        filename="missing.jpg",
        photo_time=None,
    )
    db = MagicMock()

    with patch.object(photo_crud, "get_photo", return_value=db_photo):
        with pytest.raises(ValueError, match="原文件不存在"):
            photo_crud.update_photo(
                db,
                uuid4(),
                PhotoUpdate(filename="new.jpg", modify_original_file=True),
                user_id=owner_id,
            )

    assert db_photo.filename == "missing.jpg"
    db.commit.assert_not_called()
