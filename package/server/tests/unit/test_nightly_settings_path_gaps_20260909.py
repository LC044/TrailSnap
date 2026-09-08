"""2026-09-09 nightly tests for settings path and storage-root helpers."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import settings as settings_api

pytestmark = [pytest.mark.smoke]


def test_path_validator_rejects_empty_and_traversal():
    for value, fragment in [("", "Invalid path"), ("../secret", "traversal detected")]:
        with pytest.raises(HTTPException) as exc:
            settings_api.PathValidator.validate(value)
        assert exc.value.status_code == 400
        assert fragment in exc.value.detail


def test_path_validator_requires_existing_directory(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(HTTPException) as missing_exc:
        settings_api.PathValidator.validate(str(missing))
    assert missing_exc.value.status_code == 400
    assert "does not exist" in missing_exc.value.detail

    target = tmp_path / "photos"
    target.mkdir()
    assert settings_api.PathValidator.validate(f"  {target}  ") == str(target.resolve())

    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(HTTPException) as file_exc:
        settings_api.PathValidator.validate(str(file_path))
    assert "not a directory" in file_exc.value.detail


def test_get_storage_root_falls_back_to_uploads_and_closes_db():
    db = MagicMock()
    config = MagicMock()
    config.storage.photo_storage_path = ""
    settings_api.config_manager.get_user_config = MagicMock(return_value=config)

    assert settings_api.get_storage_root("user-id", db) == "uploads"
    db.close.assert_called_once()

    config.storage.photo_storage_path = "/photos/root"
    assert settings_api.get_storage_root("user-id", db) == "/photos/root"
