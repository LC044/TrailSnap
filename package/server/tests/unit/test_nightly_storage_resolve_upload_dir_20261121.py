"""Upload directory resolution guards and the screenshot move placeholder."""
import os
from uuid import uuid4

import pytest

from app.api.storage import move_screenshots_to_non_archive
from app.service import storage as storage_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_resolve_upload_directory_defaults_to_year_month_buckets(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "_get_storage_root", lambda user_id, db=None: str(tmp_path))
    result = storage_service._resolve_upload_directory(uuid4(), None)
    parts = os.path.normpath(result).split(os.sep)
    assert parts[-3] == "uploads"
    assert len(parts[-2]) == 4 and parts[-2].isdigit()
    assert len(parts[-1]) == 2 and parts[-1].isdigit()


def test_resolve_upload_directory_appends_relative_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "_get_storage_root", lambda user_id, db=None: str(tmp_path))
    result = storage_service._resolve_upload_directory(uuid4(), "trip/2026")
    assert os.path.normpath(result) == os.path.normpath(
        os.path.join(str(tmp_path), "uploads", "trip", "2026")
    )


def test_resolve_upload_directory_rejects_parent_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "_get_storage_root", lambda user_id, db=None: str(tmp_path))
    with pytest.raises(ValueError):
        storage_service._resolve_upload_directory(uuid4(), "../escape")


def test_resolve_upload_directory_accepts_absolute_folder_inside_external_root(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "get_external_upload_roots", lambda user_id, db=None: [str(tmp_path)])
    target = tmp_path / "gallery"
    result = storage_service._resolve_upload_directory(uuid4(), str(target))
    assert os.path.normpath(result) == os.path.normpath(str(target))


def test_resolve_upload_directory_rejects_absolute_folder_outside_external_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "get_external_upload_roots", lambda user_id, db=None: [str(tmp_path)])
    with pytest.raises(ValueError):
        storage_service._resolve_upload_directory(uuid4(), str(tmp_path.parent / "elsewhere"))


def test_move_screenshots_to_non_archive_returns_success_payload():
    response = move_screenshots_to_non_archive([uuid4()], None, None)
    assert response.code == 0
    assert response.data == {"message": "Moved successfully"}
