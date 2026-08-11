"""Unit tests covering the 2026-08-11 nightly coverage gap scan (round 3).

Modules exercised:
* app/api/media.py -- upload + finish-upload + heic/Range + 416 branch
* app/service/storage.py -- filesystem helper coverage
* app/api/toolbox.py -- duplicate-photos empty list + similar-task 404

All endpoints are exercised against a fully mocked DB and patched
``run_in_threadpool`` so no real Postgres, FS, or AI service is hit.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.api import toolbox as toolbox_api
from app.service import storage as storage_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _photo(file_path="C:/photos/original.jpg"):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        file_path=file_path,
    )


async def _exec(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ============================================================================
# app/api/media.py -- upload + finish-upload + Range/416
# ============================================================================


@pytest.mark.asyncio
async def test_upload_photo_generic_returns_404_when_album_missing():
    user = SimpleNamespace(id=uuid4())
    album_id = uuid4()
    db = MagicMock()

    with patch.object(media_api, "run_in_threadpool", side_effect=_exec):
        with patch.object(media_api.crud_album, "get_album", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await media_api.upload_photo_generic(
                    album_id=album_id,
                    file=SimpleNamespace(filename="o.jpg"),
                    db=db,
                    current_user=user,
                )
    assert exc_info.value.status_code == 404
    assert "Album" in exc_info.value.detail


@pytest.mark.asyncio
async def test_finish_upload_generic_rejects_when_no_chunks(tmp_path):
    user = SimpleNamespace(id=uuid4())
    upload_id = uuid4()
    db = MagicMock()
    chunk_dir = tmp_path / "chunks" / str(upload_id)
    chunk_dir.mkdir(parents=True)

    with patch.object(media_api, "run_in_threadpool", side_effect=_exec):
        with patch.object(media_api.os.path, "exists", return_value=True):
            with patch.object(media_api.os, "listdir", return_value=[]):
                with pytest.raises(HTTPException) as exc_info:
                    await media_api.finish_upload_generic(
                        upload_id=upload_id,
                        file_name="merged.jpg",
                        db=db,
                        current_user=user,
                    )
    assert exc_info.value.status_code == 400
    assert "No chunks" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_media_file_returns_416_when_range_past_end(tmp_path):
    photo_id = uuid4()
    photo = _photo(file_path=str(tmp_path / "sample.jpg"))
    (tmp_path / "sample.jpg").write_bytes(b"abc")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        with patch.object(media_api.os.path, "getsize", return_value=3):
            response = await media_api.get_media_file(
                photo_id, request=MagicMock(), db=db, range="bytes=10-20"
            )
    assert response.status_code == 416
    assert response.headers["Content-Range"] == "bytes */3"


@pytest.mark.asyncio
async def test_get_live_photo_video_jpg_falls_back_to_thumb_path(tmp_path):
    """For .jpg photos, the live-video endpoint must look up the video
    beside the original first and fall back to the thumbnail directory."""
    photo_id = uuid4()
    photo = _photo(file_path=str(tmp_path / "snap.jpg"))

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    # exists() is called several times in jpg path; first original-adjacent .mp4
    # doesn't exist, then .mov doesn't exist, then thumb path also doesn't exist.
    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        with patch.object(media_api.os.path, "exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                await media_api.get_live_photo_video(
                    photo_id, request=MagicMock(), db=db, range=None
                )


# ============================================================================
# app/service/storage.py -- filesystem helper coverage
# ============================================================================


def test_get_file_size_returns_int_for_existing_file(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"hello")
    assert storage_service.get_file_size(str(p)) == 5


def test_get_image_dimensions_reads_disk_file(tmp_path):
    from PIL import Image
    p = tmp_path / "pixel.png"
    Image.new("RGB", (12, 7), color=(255, 0, 0)).save(p)
    width, height, extra = storage_service.get_image_dimensions(str(p))
    assert (width, height) == (12, 7)
    assert extra is None


# ============================================================================
# app/api/toolbox.py -- duplicate-photos empty list + similar-task empty
# ============================================================================


def test_get_duplicate_photos_returns_empty_when_no_duplicate_md5s():
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    # The route queries Photo.md5 having count>1; no rows -> empty data.
    db.query.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

    response = toolbox_api.get_duplicate_photos(db=db, current_user=user)

    assert response.code == 0  # BaseResponse success code is 0
    assert response.data == []


def test_get_similar_task_result_returns_empty_when_no_clusters():
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    # First query is ImageCluster filter; return [] to short-circuit the loop.
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

    response = toolbox_api.get_similar_task_result(
        task_id=uuid4(), db=db, current_user=user
    )

    assert response.code == 0
    assert response.data == []
