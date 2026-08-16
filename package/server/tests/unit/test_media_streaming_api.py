"""Coverage for media streaming / chunked upload / geojson endpoints.

Adds to test_media_api.py (which already covers thumbnail helper + get_thumbnail)
the streaming endpoints (live photo video, media file), chunked upload
lifecycle, and the geojson dispatcher. Keeps the existing test file untouched
per nightly watcher scope rules.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _photo(file_path="C:/photos/original.jpg"):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        file_path=file_path,
    )


# ---------------- get_live_photo_video ----------------


@pytest.mark.asyncio
async def test_get_live_photo_video_returns_404_when_photo_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await media_api.get_live_photo_video(uuid4(), request=MagicMock(), db=db)

    assert exc_info.value.status_code == 404
    assert "Video file" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_live_photo_video_dispatches_full_file_response(tmp_path):
    """No range header -> full FileResponse regardless of extension dispatch."""
    photo_id = uuid4()
    mov = tmp_path / "live.MOV"
    mov.write_bytes(b"video-bytes")
    photo = _photo(file_path=str(mov))

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        response = await media_api.get_live_photo_video(
            photo_id, request=MagicMock(), db=db, range=None
        )

    assert response is not None


# ---------------- get_media_file ----------------


@pytest.mark.asyncio
async def test_get_media_file_404_when_photo_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await media_api.get_media_file(uuid4(), request=MagicMock(), db=db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_media_file_404_when_file_missing(tmp_path):
    photo = _photo(file_path=str(tmp_path / "ghost.jpg"))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        with pytest.raises(HTTPException) as exc_info:
            await media_api.get_media_file(photo.id, request=MagicMock(), db=db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_media_file_heic_resolves_via_thumbnail(tmp_path):
    """For .heic photos, the resolver should call _get_thumbnail_path (regression for tuple bug)."""
    photo_id = uuid4()
    heic = tmp_path / "sample.heic"
    heic.write_bytes(b"heic-bytes")
    photo = _photo(file_path=str(heic))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    expected_thumb = str(tmp_path / "medium-thumb.jpg")

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        with patch.object(media_api, "_get_thumbnail_path", return_value=expected_thumb) as resolver:
            with patch.object(media_api.os.path, "getsize", return_value=42):
                with patch.object(media_api, "FileResponse") as file_response:
                    response = await media_api.get_media_file(
                        photo_id, request=MagicMock(), db=db, range=None
                    )

    resolver.assert_called_once_with(photo.owner_id, photo_id, db, "medium")
    file_response.assert_called_once()
    assert response is not None


# ---------------- chunked upload ----------------


@pytest.mark.asyncio
async def test_init_upload_creates_directory_and_returns_id():
    with patch.object(media_api.os, "makedirs") as makedirs:
        result = await media_api.init_upload()

    assert "upload_id" in result
    makedirs.assert_called_once()
    _, kwargs = makedirs.call_args
    assert kwargs.get("exist_ok") is True


@pytest.mark.asyncio
async def test_upload_chunk_404_when_session_missing():
    with patch.object(media_api.os.path, "exists", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await media_api.upload_chunk(
                upload_id=uuid4(),
                chunk_index=0,
                file=SimpleNamespace(file=MagicMock()),
            )

    assert exc_info.value.status_code == 404
    assert "session not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_chunk_runs_save_in_threadpool(tmp_path):
    """upload_chunk persists chunk bytes through run_in_threadpool."""
    fake_file = MagicMock()

    async def _exec(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch.object(media_api.os.path, "exists", return_value=True):
        with patch.object(media_api, "run_in_threadpool", side_effect=_exec) as runner:
            with patch("builtins.open", mock_open()) as opener:
                with patch.object(media_api.shutil, "copyfileobj") as copier:
                    result = await media_api.upload_chunk(
                        upload_id=uuid4(),
                        chunk_index=7,
                        file=SimpleNamespace(file=fake_file),
                    )

    assert result == {"status": "success"}
    assert runner.call_count == 2
    opener.assert_called_once()
    copier.assert_called_once_with(fake_file, opener())


# ---------------- geojson dispatcher ----------------


@pytest.mark.asyncio
async def test_get_geojson_rejects_invalid_level():
    with pytest.raises(HTTPException) as exc_info:
        await media_api.get_geojson(level="continent")

    assert exc_info.value.status_code == 400
    assert "Invalid level" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_geojson_404_when_file_missing():
    with patch.object(media_api.os.path, "exists", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await media_api.get_geojson(level="city")

    assert exc_info.value.status_code == 404
    assert "GeoJSON file" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_geojson_uses_bundle_root_instead_of_working_directory(tmp_path, monkeypatch):
    bundle_root = tmp_path / "bundle"
    geo_dir = bundle_root / "resources" / "geo_data"
    geo_dir.mkdir(parents=True)
    geo_file = geo_dir / "中国_省.geojson"
    geo_file.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    working_dir = tmp_path / "desktop-data"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(media_api, "BUNDLE_ROOT", str(bundle_root))

    response = await media_api.get_geojson(level="province")

    assert response.path == str(geo_file)


# ---------------- get_thumbnail format=file ----------------


@pytest.mark.asyncio
async def test_get_thumbnail_returns_file_response(tmp_path):
    photo_id = uuid4()
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"x")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(owner_id=uuid4())

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(thumb)):
        response = await media_api.get_thumbnail(photo_id, format="file", db=db)

    assert response is not None


@pytest.mark.asyncio
async def test_get_thumbnail_404_when_thumbnail_missing(tmp_path):
    photo_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(owner_id=uuid4())

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(tmp_path / "missing.jpg")):
        with patch.object(media_api.os.path, "exists", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await media_api.get_thumbnail(photo_id, db=db)

    assert exc_info.value.status_code == 404
    assert "Thumbnail not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_thumbnail_rejects_bad_format(tmp_path):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(owner_id=uuid4())
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"x")

    with patch.object(media_api, "_get_thumbnail_path", return_value=str(thumb)):
        with pytest.raises(HTTPException) as exc_info:
            await media_api.get_thumbnail(uuid4(), format="binary", db=db)

    assert exc_info.value.status_code == 400
    assert "Invalid format" in exc_info.value.detail
