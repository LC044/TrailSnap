"""2026-10-30 nightly coverage for the request-validation guards in
``app/api/media.py``.

The 2026-10-30 backend scan still reported ``api/media.py`` at 87.4% with 103
uncovered lines.  Most of them sit in the **input validation** of the mobile
backup / upload endpoints and in the static thumbnail route:

* ``check_mobile_backup_assets`` — validates ``keys`` / ``hashes`` /
  ``source_times`` before the mobile client may skip an upload;
* ``create_upload_folder`` — validates the target folder before creating it
  on disk;
* ``upload_missing_live_content`` — validates the live-photo manifest;
* ``upload_chunk`` — validates the chunk index;
* ``get_static_thumbnail`` — validates size / format and the storage root.

These guards are the boundary between a buggy mobile client and the user's
photo library, so the tests pin the exact status codes and messages.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _media():
    from app.api import media

    return media


def _user():
    return SimpleNamespace(id=uuid.uuid4())


def _db():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.first.return_value = None
    return db


# ---------------------------------------------------------------------------
# check_mobile_backup_assets
# ---------------------------------------------------------------------------


def test_backup_check_rejects_keys_that_are_not_a_string_array():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": "nope"}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert "keys must be a string array" in excinfo.value.detail


def test_backup_check_rejects_more_than_two_hundred_keys():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": [f"k{i}" for i in range(201)]}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert "keys must be a string array" in excinfo.value.detail


def test_backup_check_rejects_a_non_string_key():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": [42]}, _db(), _user())

    assert excinfo.value.status_code == 400


def test_backup_check_rejects_hashes_that_are_not_a_string_array():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": [], "hashes": {"a": 1}}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert "hashes must be a string array" in excinfo.value.detail


def test_backup_check_rejects_more_than_two_hundred_hashes():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets(
            {"keys": [], "hashes": [f"h{i}" for i in range(201)]}, _db(), _user()
        )

    assert excinfo.value.status_code == 400
    assert "hashes must be a string array" in excinfo.value.detail


def test_backup_check_rejects_source_times_that_are_not_an_object():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": [], "source_times": []}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert "source_times must be an object" in excinfo.value.detail


def test_backup_check_rejects_more_than_two_hundred_source_times():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets(
            {"keys": [], "source_times": {f"k{i}": "2024-01-01T00:00:00" for i in range(201)}},
            _db(), _user(),
        )

    assert excinfo.value.status_code == 400
    assert "source_times must be an object" in excinfo.value.detail


def test_backup_check_rejects_an_unparsable_source_time():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets(
            {"keys": [], "source_times": {"k": "not-a-date"}}, _db(), _user()
        )

    assert excinfo.value.status_code == 400
    assert "invalid datetime" in excinfo.value.detail


def test_backup_check_rejects_a_non_string_source_time_value():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_mobile_backup_assets({"keys": [], "source_times": {"k": 123}}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert "invalid datetime" in excinfo.value.detail


def test_backup_check_accepts_an_empty_manifest():
    media = _media()

    response = media.check_mobile_backup_assets({"keys": [], "hashes": []}, _db(), _user())

    assert response.data == {"existing": [], "complete": [], "live_photos": [], "hashes": []}


def test_backup_check_accepts_an_iso_source_time_with_a_z_suffix():
    media = _media()

    response = media.check_mobile_backup_assets(
        {"keys": [], "source_times": {"k": "2024-05-01T09:00:00Z"}}, _db(), _user()
    )

    assert response.data == {"existing": [], "complete": [], "live_photos": [], "hashes": []}


# ---------------------------------------------------------------------------
# create_upload_folder
# ---------------------------------------------------------------------------


def test_create_upload_folder_requires_a_path():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.create_upload_folder({"path": "   "}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Folder path is required"


def test_create_upload_folder_rejects_a_traversal_path():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.create_upload_folder({"path": "../escape"}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid folder path"


def test_create_upload_folder_rejects_an_absolute_path():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.create_upload_folder({"path": os.path.abspath("outside")}, _db(), _user())

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid folder path"


def test_create_upload_folder_creates_the_folder(tmp_path):
    media = _media()
    user = _user()

    with patch.object(media, "_upload_root", return_value=str(tmp_path)):
        response = media.create_upload_folder({"path": "trip/2024"}, _db(), user)

    assert response.data == {"path": "trip/2024"}
    assert (tmp_path / "trip" / "2024").is_dir()


# ---------------------------------------------------------------------------
# upload_missing_live_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_upload_rejects_a_content_hash_that_is_not_an_md5():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.upload_missing_live_content(
            image_md5="not-a-hash", video_md5="b" * 32, video_name="clip.mp4", backup_key="k",
            db=_db(), current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert "32-character hexadecimal MD5" in excinfo.value.detail


@pytest.mark.asyncio
async def test_live_upload_rejects_an_overlong_backup_key():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.upload_missing_live_content(
            image_md5="a" * 32, video_md5="b" * 32, video_name="clip.mp4", backup_key="k" * 256,
            db=_db(), current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid live photo manifest"


@pytest.mark.asyncio
async def test_live_upload_rejects_an_unsupported_video_name():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.upload_missing_live_content(
            image_md5="a" * 32, video_md5="b" * 32, video_name="clip.txt", backup_key="k",
            db=_db(), current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid live photo video name"


# ---------------------------------------------------------------------------
# upload_chunk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_chunk_rejects_a_negative_chunk_index():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.upload_chunk(
            upload_id=uuid.uuid4(), chunk_index=-1, file=MagicMock(),
            db=_db(), current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid chunk index"


@pytest.mark.asyncio
async def test_upload_chunk_rejects_an_unknown_upload_session():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.upload_chunk(
            upload_id=uuid.uuid4(), chunk_index=0, file=MagicMock(),
            db=_db(), current_user=_user(),
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Upload session not found"


# ---------------------------------------------------------------------------
# get_static_thumbnail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_thumbnail_rejects_an_unknown_size():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.get_static_thumbnail(uuid.uuid4(), uuid.uuid4(), size="huge")

    assert excinfo.value.status_code == 400
    assert "Invalid size" in excinfo.value.detail


@pytest.mark.asyncio
async def test_static_thumbnail_reports_a_missing_storage_root():
    media = _media()

    with patch.object(media.user_storage, "get_cached_storage_base", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            await media.get_static_thumbnail(uuid.uuid4(), uuid.uuid4())

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Thumbnail owner not found"


@pytest.mark.asyncio
async def test_static_thumbnail_reports_a_missing_file(tmp_path):
    media = _media()
    owner = uuid.uuid4()

    with patch.object(media.user_storage, "get_cached_storage_base", return_value="base"), \
            patch.object(media.user_storage, "get_user_root", return_value=str(tmp_path)), \
            patch.object(media, "_get_thumbnail_path", return_value=str(tmp_path / "missing.webp")):
        with pytest.raises(HTTPException) as excinfo:
            await media.get_static_thumbnail(owner, uuid.uuid4())

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Thumbnail not found"


@pytest.mark.asyncio
async def test_static_thumbnail_rejects_an_unknown_format(tmp_path):
    media = _media()
    owner = uuid.uuid4()
    thumbnail = tmp_path / "thumb.webp"
    thumbnail.write_bytes(b"webp-bytes")

    with patch.object(media.user_storage, "get_cached_storage_base", return_value="base"), \
            patch.object(media.user_storage, "get_user_root", return_value=str(tmp_path)), \
            patch.object(media, "_get_thumbnail_path", return_value=str(thumbnail)):
        with pytest.raises(HTTPException) as excinfo:
            await media.get_static_thumbnail(owner, uuid.uuid4(), format="tiff")

    assert excinfo.value.status_code == 400
    assert "Invalid format" in excinfo.value.detail


@pytest.mark.asyncio
async def test_static_thumbnail_can_return_base64(tmp_path):
    media = _media()
    owner = uuid.uuid4()
    thumbnail = tmp_path / "thumb.webp"
    thumbnail.write_bytes(b"webp-bytes")

    with patch.object(media.user_storage, "get_cached_storage_base", return_value="base"), \
            patch.object(media.user_storage, "get_user_root", return_value=str(tmp_path)), \
            patch.object(media, "_get_thumbnail_path", return_value=str(thumbnail)):
        payload = await media.get_static_thumbnail(owner, uuid.uuid4(), format="base64")

    assert payload["base64"] == "d2VicC1ieXRlcw=="