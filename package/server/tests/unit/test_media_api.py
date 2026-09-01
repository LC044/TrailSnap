"""Focused unit coverage for media thumbnail helpers and responses."""

import base64
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi import UploadFile

from app.api import media as media_api
from app.db.models.photo import FileType


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_thumbnail_path_falls_back_to_jpeg(tmp_path):
    owner_id = uuid4()
    photo_id = uuid4()

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)), patch.object(
        media_api.os.path, "exists", return_value=False
    ):
        result = media_api._get_thumbnail_path(owner_id, photo_id, MagicMock(), "small")

    assert result.endswith(f"{photo_id.hex}-thumb.jpg")
    assert str(tmp_path) in result


@pytest.mark.parametrize(
    ("image_name", "video_name", "expected_suffix"),
    [
        ("IMG_0001.HEIC", "IMG_0001.MOV", "IMG_0001.MOV"),
        ("IMG_0002.jpg", "IMG_0002.mp4", "IMG_0002.mp4"),
        ("IMG_0003.jpeg", "IMG_0003.mov", "IMG_0003.mov"),
    ],
)
def test_live_photo_video_path_uses_supported_pair_convention(tmp_path, image_name, video_name, expected_suffix):
    result = media_api._live_photo_video_path(str(tmp_path / image_name), video_name)
    assert result.endswith(expected_suffix)


def test_live_photo_video_path_rejects_unsupported_companion(tmp_path):
    with pytest.raises(ValueError):
        media_api._live_photo_video_path(str(tmp_path / "IMG_0001.jpg"), "IMG_0001.avi")


def test_backup_check_distinguishes_existing_complete_and_live_photo(tmp_path):
    owner_id = uuid4()
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"image")
    live_image = tmp_path / "live.jpg"
    live_image.write_bytes(b"image")
    live_image.with_suffix(".mp4").write_bytes(b"video")
    incomplete_live = tmp_path / "incomplete.jpg"
    incomplete_live.write_bytes(b"image")

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        ("photo", FileType.image, str(photo)),
        ("live", FileType.live_photo, str(live_image)),
        ("incomplete-live", FileType.live_photo, str(incomplete_live)),
        ("missing", FileType.image, str(tmp_path / "missing.jpg")),
    ]

    result = media_api.check_mobile_backup_assets(
        {"keys": ["photo", "live", "incomplete-live", "missing"]},
        db=db,
        current_user=SimpleNamespace(id=owner_id),
    )

    assert set(result.data["existing"]) == {"photo", "live", "incomplete-live", "missing"}
    assert set(result.data["complete"]) == {"photo", "live", "incomplete-live"}
    assert result.data["live_photos"] == ["live"]


def test_attach_live_photo_video_replaces_companion_atomically(tmp_path):
    image = tmp_path / "IMG_0001.jpg"
    image.write_bytes(b"image")
    photo = SimpleNamespace(
        id=uuid4(), filename=image.name, file_path=str(image), file_type=FileType.image,
    )
    upload = UploadFile(filename="IMG_0001.mp4", file=io.BytesIO(b"new-video"))
    db = MagicMock()

    with patch.object(media_api, "_existing_backup_photo", return_value=None), \
         patch.object(media_api.storage, "validate_target_path"):
        result = media_api._attach_live_photo_video(db, photo, upload, None, uuid4())

    assert result == str(tmp_path / "IMG_0001.mp4")
    assert (tmp_path / "IMG_0001.mp4").read_bytes() == b"new-video"
    assert photo.file_type == FileType.live_photo


def test_attach_live_photo_video_keeps_old_companion_when_copy_fails(tmp_path):
    image = tmp_path / "IMG_0001.jpg"
    companion = tmp_path / "IMG_0001.mp4"
    image.write_bytes(b"image")
    companion.write_bytes(b"old-video")
    photo = SimpleNamespace(
        id=uuid4(), filename=image.name, file_path=str(image), file_type=FileType.live_photo,
    )
    upload = UploadFile(filename="IMG_0001.mp4", file=io.BytesIO(b"broken-video"))
    db = MagicMock()

    with patch.object(media_api, "_existing_backup_photo", return_value=None), \
         patch.object(media_api.storage, "validate_target_path"), \
         patch.object(media_api.shutil, "copyfileobj", side_effect=OSError("copy failed")):
        with pytest.raises(OSError, match="copy failed"):
            media_api._attach_live_photo_video(db, photo, upload, None, uuid4())

    assert companion.read_bytes() == b"old-video"
    assert not list(tmp_path.glob("*.uploading"))


def test_replace_backup_file_overwrites_bytes_and_marks_metadata_stale(tmp_path):
    target = tmp_path / "IMG_0001.jpg"
    target.write_bytes(b"redacted")
    photo = SimpleNamespace(
        id=uuid4(), file_path=str(target), processed_tasks={"metadata": True},
        size=8, width=1, height=1, duration=None,
    )
    db = MagicMock()
    upload = UploadFile(filename="IMG_0001.jpg", file=io.BytesIO(b"original-with-gps"))

    with patch.object(media_api.storage, "validate_target_path"), patch.object(
        media_api.storage, "delete_thumbnails"
    ), patch.object(media_api.storage, "generate_thumbnail"), patch.object(
        media_api.storage, "get_image_dimensions", return_value=(20, 10, None)
    ):
        media_api._replace_backup_file(db, photo, upload, uuid4())

    assert target.read_bytes() == b"original-with-gps"
    assert photo.processed_tasks["metadata"] is False
    assert (photo.width, photo.height, photo.size) == (20, 10, len(b"original-with-gps"))


@pytest.mark.asyncio
async def test_get_thumbnail_returns_base64_payload(tmp_path):
    photo_id = uuid4()
    thumbnail = tmp_path / "thumb.jpg"
    thumbnail.write_bytes(b"thumbnail-bytes")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(owner_id=uuid4())

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(thumbnail)):
        result = await media_api.get_thumbnail(photo_id, format="base64", db=db)

    assert result == {"base64": base64.b64encode(b"thumbnail-bytes").decode("utf-8")}


@pytest.mark.asyncio
async def test_get_thumbnail_rejects_unknown_photo():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await media_api.get_thumbnail(uuid4(), db=db)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Photo not found"
