"""Unit tests for app/api/media.py Range handler, media-type mapping and
live-photo video fallback branches.

Round: 2026-08-25.
Covers the missing ranges reported by the targeted coverage scan:
- app/api/media.py 71% covered (71 missed) coming into this round.
  - get_media_file Range header (197-222), MediaType mapping (181-183)
  - get_live_photo_video extension fall-through (.mp4 / .MOV / thumb .mp4),
    Range header parsing (95-130)
  - get_media_file 404 paths (no photo / no file)

Pattern: MagicMock + tmp_path + `route_in_threadpool` already executes
synchronous lambdas straight on `db`, so the existing pattern is unchanged.
Real files are written into tmp_path so anyio.open_file inside the Range
handler iterfile() can stream from them.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.api import media as media_api


pytestmark = [pytest.mark.smoke]


def _photo(file_path: str, owner_id=None):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=owner_id or uuid4(),
        file_path=file_path,
    )


async def _consume(response):
    """Drain a StreamingResponse body and return it as bytes."""
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# get_media_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_media_file_404_when_photo_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await media_api.get_media_file(
            photo_id=uuid4(), request=request, range=None, db=db
        )
    assert exc.value.status_code == 404
    assert "File not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_media_file_404_when_file_missing(tmp_path):
    photo = _photo(file_path=str(tmp_path / "missing.jpg"))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await media_api.get_media_file(
            photo_id=photo.id, request=request, range=None, db=db
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "expected_media_type"),
    [
        ("snap.jpg", "image/jpeg"),
        ("snap.jpeg", "image/jpeg"),
        ("snap.png", "image/png"),
        ("snap.webp", "image/webp"),
        ("snap.tiff", "image/tiff"),
        ("snap.gif", "image/gif"),
        ("clip.mp4", "video/mp4"),
        ("clip.mov", "video/quicktime"),
        ("clip.mkv", "video/x-matroska"),
        ("clip.avi", "video/avi"),
    ],
)
async def test_get_media_file_media_type_mapping(
    tmp_path, filename, expected_media_type
):
    real_path = tmp_path / filename
    real_path.write_bytes(b"x" * 64)
    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    resp = await media_api.get_media_file(
        photo_id=photo.id, request=request, range=None, db=db
    )
    assert isinstance(resp, FileResponse)
    assert resp.media_type == expected_media_type


@pytest.mark.asyncio
async def test_get_media_file_heic_redirects_to_thumbnail(tmp_path):
    """`.heic` files aren't served directly; the endpoint should swap to a
    medium-sized thumbnail path and stream that file instead."""
    real_path = tmp_path / "snap.heic"
    real_path.write_bytes(b"x" * 32)
    thumb_path = tmp_path / "snap-thumb-medium.webp"
    thumb_path.write_bytes(b"WEBPBIN")

    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(thumb_path)):
        resp = await media_api.get_media_file(
            photo_id=photo.id, request=request, range=None, db=db
        )
    assert isinstance(resp, FileResponse)
    assert resp.path == str(thumb_path)
    # Original .heic has no explicit media-type mapping, so the endpoint
    # leaves the Content-Type at application/octet-stream even after the
    # thumbnail redirect. The important behaviour is the path swap.
    assert resp.media_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_get_media_file_past_end_returns_416(tmp_path):
    real_path = tmp_path / "snap.jpg"
    real_path.write_bytes(b"x" * 16)  # 16 bytes

    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    resp = await media_api.get_media_file(
        photo_id=photo.id,
        request=request,
        range="bytes=100-200",
        db=db,
    )
    # 100 >= 16 (file_size) -> 416 with Content-Range header.
    assert resp.status_code == 416
    assert resp.headers["Content-Range"] == "bytes */16"


@pytest.mark.asyncio
async def test_get_media_file_normal_range_returns_206_with_content(tmp_path):
    real_path = tmp_path / "snap.mp4"
    payload = bytes(range(256))  # 256 bytes
    real_path.write_bytes(payload)

    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    resp = await media_api.get_media_file(
        photo_id=photo.id,
        request=request,
        range="bytes=10-19",
        db=db,
    )
    assert isinstance(resp, StreamingResponse)
    assert resp.status_code == 206
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert resp.headers["Content-Range"] == "bytes 10-19/256"
    assert resp.headers["Content-Length"] == "10"
    assert resp.media_type == "video/mp4"

    body = await _consume(resp)
    assert body == payload[10:20]


@pytest.mark.asyncio
async def test_get_media_file_open_ended_range_uses_file_end(tmp_path):
    real_path = tmp_path / "snap.mp4"
    payload = b"0123456789"
    real_path.write_bytes(payload)

    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    resp = await media_api.get_media_file(
        photo_id=photo.id,
        request=request,
        range="bytes=2-",
        db=db,
    )
    assert resp.status_code == 206
    # Open-ended Range uses file_size-1 as end -> chunk size = 10-2 = 8 bytes
    assert resp.headers["Content-Length"] == "8"
    assert resp.headers["Content-Range"] == "bytes 2-9/10"
    body = await _consume(resp)
    assert body == payload[2:]


@pytest.mark.asyncio
async def test_get_media_file_invalid_range_falls_back_to_full(tmp_path):
    """Malformed Range (ValueError) shouldn't break the endpoint; it falls
    back to the full FileResponse."""
    real_path = tmp_path / "snap.jpg"
    real_path.write_bytes(b"y" * 32)

    photo = _photo(file_path=str(real_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    resp = await media_api.get_media_file(
        photo_id=photo.id,
        request=request,
        range="abc-def",  # ValueError when int("abc")
        db=db,
    )
    assert isinstance(resp, FileResponse)
    assert resp.media_type == "image/jpeg"


# ---------------------------------------------------------------------------
# get_live_photo_video
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_live_photo_video_404_when_photo_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await media_api.get_live_photo_video(
            photo_id=uuid4(), request=request, range=None, db=db
        )
    assert exc.value.status_code == 404
    assert "Video file not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_live_photo_video_jpg_path_uses_mp4_when_exists(tmp_path):
    """`.jpg` extension -> prefer sibling .mp4, then .mov, then thumb .mp4."""
    jpg_path = tmp_path / "snap.jpg"
    jpg_path.write_bytes(b"orig")
    mp4_path = tmp_path / "snap.mp4"
    mp4_path.write_bytes(b"vid")

    photo = _photo(file_path=str(jpg_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(tmp_path / "snap-thumb.mp4")):
        resp = await media_api.get_live_photo_video(
            photo_id=photo.id, request=request, range=None, db=db
        )
    assert isinstance(resp, FileResponse)
    assert resp.path == str(mp4_path)
    assert resp.media_type == "video/mp4"


@pytest.mark.asyncio
async def test_get_live_photo_video_jpg_falls_through_mp4_and_mov_to_thumbnail(tmp_path):
    """When neither sibling .mp4 nor .mov exists, fall back to the thumbnail
    directory's .mp4 path computed via _get_thumbnail_path."""
    jpg_path = tmp_path / "snap.jpg"
    jpg_path.write_bytes(b"orig")
    thumb_path = tmp_path / "snap-thumb.mp4"
    thumb_path.write_bytes(b"thumbvid")

    photo = _photo(file_path=str(jpg_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(thumb_path)):
        resp = await media_api.get_live_photo_video(
            photo_id=photo.id, request=request, range=None, db=db
        )
    assert isinstance(resp, FileResponse)
    assert resp.path == str(thumb_path)
    assert resp.media_type == "video/mp4"


@pytest.mark.asyncio
async def test_get_live_photo_video_non_jpg_uses_MOV(tmp_path):
    """Non-jpg source files (e.g. .HEIC) generate .MOV companion videos."""
    heic_path = tmp_path / "snap.HEIC"
    heic_path.write_bytes(b"orig")
    mov_path = tmp_path / "snap.MOV"
    mov_path.write_bytes(b"movpayload")

    photo = _photo(file_path=str(heic_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(tmp_path / "snap-thumb.mp4")):
        resp = await media_api.get_live_photo_video(
            photo_id=photo.id, request=request, range=None, db=db
        )
    assert isinstance(resp, FileResponse)
    assert resp.path == str(mov_path)
    assert resp.media_type == "video/quicktime"


@pytest.mark.asyncio
async def test_get_live_photo_video_past_end_returns_416(tmp_path):
    jpg_path = tmp_path / "snap.jpg"
    jpg_path.write_bytes(b"orig")
    mp4_path = tmp_path / "snap.mp4"
    mp4_path.write_bytes(b"x" * 20)  # 20-byte video

    photo = _photo(file_path=str(jpg_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(tmp_path / "snap-thumb.mp4")):
        resp = await media_api.get_live_photo_video(
            photo_id=photo.id,
            request=request,
            range="bytes=200-",
            db=db,
        )
    # 200 >= 20 -> 416
    assert resp.status_code == 416
    assert resp.headers["Content-Range"] == "bytes */20"


@pytest.mark.asyncio
async def test_get_live_photo_video_normal_range_returns_206(tmp_path):
    jpg_path = tmp_path / "snap.jpg"
    jpg_path.write_bytes(b"orig")
    mp4_path = tmp_path / "snap.mp4"
    payload = bytes(range(100))
    mp4_path.write_bytes(payload)

    photo = _photo(file_path=str(jpg_path))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    request = MagicMock()

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(tmp_path / "snap-thumb.mp4")):
        resp = await media_api.get_live_photo_video(
            photo_id=photo.id,
            request=request,
            range="bytes=0-9",
            db=db,
        )
    assert isinstance(resp, StreamingResponse)
    assert resp.status_code == 206
    assert resp.headers["Content-Length"] == "10"
    assert resp.media_type == "video/mp4"
    body = await _consume(resp)
    assert body == payload[0:10]
