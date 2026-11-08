"""Nightly watch 2026-11-08 (round 2): priority blind-spot coverage.

Targets the lowest-coverage backend modules reported by the 2026-11-08
coverage snapshot:

* ``app/service/app_update.py``      - APK cache / release lookup guards
* ``app/service/tasks/metadata.py``  - thumbnail colour extraction + cached metadata
* ``app/api/media.py``               - chunked upload finalisation + live-photo guards

Every test below exercises an already-implemented behaviour; no production
code is changed.
"""

from __future__ import annotations

import errno
import io
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api import media as media_api
from app.db.models.photo import FileType
from app.service import app_update
from app.service.tasks import metadata as metadata_tasks

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------- #
# app/service/app_update.py
# --------------------------------------------------------------------------- #


def test_cached_apk_path_rejects_invalid_version():
    """An unparsable version must not resolve to a cache path."""
    assert app_update.cached_apk_path("not-a-version") is None
    assert app_update.cached_apk_path("") is None


def test_prune_app_update_cache_keeps_file_that_cannot_be_removed(tmp_path):
    """A locked file is reported but must not abort the whole prune pass."""
    keep = tmp_path / "TrailSnap-1.2.3.apk"
    keep.write_bytes(b"keep")
    stale = tmp_path / "TrailSnap-1.0.0.apk"
    stale.write_bytes(b"stale")

    with patch.object(app_update, "APP_UPDATE_CACHE_DIR", str(tmp_path)), \
         patch.object(app_update.os, "remove", side_effect=OSError("file is locked")):
        removed = app_update.prune_app_update_cache("1.2.3")

    assert removed == []
    assert stale.exists()


def test_prune_app_update_cache_ignores_non_apk_files(tmp_path):
    """Only ``.apk`` / ``.part`` leftovers are eligible for pruning."""
    keep = tmp_path / "TrailSnap-1.2.3.apk"
    keep.write_bytes(b"keep")
    stale = tmp_path / "TrailSnap-1.0.0.apk"
    stale.write_bytes(b"stale")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_bytes(b"keep me")

    with patch.object(app_update, "APP_UPDATE_CACHE_DIR", str(tmp_path)):
        removed = app_update.prune_app_update_cache("1.2.3")

    assert removed == ["TrailSnap-1.0.0.apk"]
    assert unrelated.exists()
    assert keep.exists()
    assert not stale.exists()


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, payload, recorder):
        self._payload = payload
        self._recorder = recorder

    def get(self, url, headers=None, timeout=None):
        self._recorder.append((url, dict(headers or {})))
        return _FakeResponse(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _release_payload():
    return {
        "assets": [
            {
                "name": "TrailSnap-1.2.3-mobile-android-universal-debug.apk",
                "browser_download_url": "https://github.com/LC044/TrailSnap/releases/download/v1.2.3/app.apk",
                "size": 42,
            }
        ]
    }


@pytest.mark.asyncio
async def test_fetch_release_apk_forwards_token_to_github_origin(monkeypatch):
    """The GitHub credential may only travel to the GitHub origin itself."""
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    recorder = []
    origin = "https://api.github.com/repos/LC044/TrailSnap/releases/tags/v1.2.3"

    with patch.object(app_update, "github_url_candidates", return_value=[origin]), \
         patch.object(app_update.aiohttp, "ClientSession",
                      lambda *a, **k: _FakeSession(_release_payload(), recorder)):
        asset = await app_update.fetch_release_apk("1.2.3")

    assert asset is not None
    assert asset["size"] == 42
    assert recorder[0][1]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_fetch_release_apk_never_forwards_token_to_mirror(monkeypatch):
    """Mirrors are third parties and must never receive the GitHub token."""
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    recorder = []
    mirror = "https://gh-proxy.com/https://api.github.com/repos/LC044/TrailSnap/releases/tags/v1.2.3"

    with patch.object(app_update, "github_url_candidates", return_value=[mirror]), \
         patch.object(app_update.aiohttp, "ClientSession",
                      lambda *a, **k: _FakeSession(_release_payload(), recorder)):
        asset = await app_update.fetch_release_apk("1.2.3")

    assert asset is not None
    assert "Authorization" not in recorder[0][1]


@pytest.mark.asyncio
async def test_ensure_cached_apk_prunes_older_packages_after_cache():
    """A freshly cached APK must trigger pruning of the previous version."""
    cached = "/tmp/TrailSnap-1.2.3.apk"
    asset = {
        "download_url": "https://github.com/LC044/TrailSnap/releases/download/v1.2.3/app.apk",
        "size": 42,
        "file_name": "app.apk",
    }

    with patch.object(app_update, "cached_apk_path", return_value=None), \
         patch.object(app_update, "fetch_release_apk", return_value=asset), \
         patch.object(app_update, "cache_release_apk", return_value=cached), \
         patch.object(app_update, "prune_app_update_cache") as prune:
        result = await app_update.ensure_cached_apk("1.2.3")

    assert result == cached
    prune.assert_called_once_with("1.2.3")


# --------------------------------------------------------------------------- #
# app/service/tasks/metadata.py
# --------------------------------------------------------------------------- #


class _FakeImage:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _photo(file_type=FileType.image, *, with_owner=True):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4() if with_owner else None,
        file_type=file_type,
        file_path="photo.jpg",
    )


def test_update_photo_color_from_thumbnail_skips_video_photos():
    """Videos carry no still thumbnail, so colour analysis must be skipped."""
    photo = _photo(file_type=FileType.video)

    with patch.object(metadata_tasks.storage, "get_available_photo_path") as available:
        metadata_tasks.update_photo_color_from_thumbnail(MagicMock(), photo)

    available.assert_not_called()


def test_update_photo_color_from_thumbnail_skips_photos_without_owner():
    """Photos without an owner have no storage root to read a preview from."""
    photo = _photo(with_owner=False)

    with patch.object(metadata_tasks.storage, "get_available_photo_path") as available:
        metadata_tasks.update_photo_color_from_thumbnail(MagicMock(), photo)

    available.assert_not_called()


def test_update_photo_color_from_thumbnail_returns_when_preview_is_missing():
    """A missing preview means there is nothing to analyse."""
    photo = _photo()

    with patch.object(metadata_tasks.storage, "get_available_photo_path", return_value=None):
        metadata_tasks.update_photo_color_from_thumbnail(MagicMock(), photo)


def test_update_photo_color_from_thumbnail_creates_record_in_supplied_cache(tmp_path):
    """When a colour cache is passed in, the new record must be registered in it."""
    photo = _photo()
    preview = tmp_path / "photo.jpg"
    preview.write_bytes(b"image")
    thumbnail = tmp_path / "photo-thumb.jpg"
    thumbnail.write_bytes(b"thumb")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    colors = {}

    with patch.object(metadata_tasks.storage, "get_available_photo_path", return_value=str(preview)), \
         patch.object(metadata_tasks, "budgeted_open", lambda path: open(path, "rb")), \
         patch.object(metadata_tasks.Image, "open", lambda source: _FakeImage()), \
         patch.object(metadata_tasks, "extract_color_info",
                      return_value={"dominant_colors": ["#112233"], "brightness": 0.5,
                                    "saturation": 0.25, "emotion_hint": "calm"}):
        metadata_tasks.update_photo_color_from_thumbnail(db, photo, colors=colors)

    assert photo.id in colors
    record = colors[photo.id]
    assert record.dominant_colors == ["#112233"]
    assert record.brightness == 0.5
    assert record.analysis_version == metadata_tasks.CURRENT_COLOR_ANALYSIS_VERSION
    db.add.assert_called_once_with(record)


def test_update_photo_color_from_thumbnail_skips_images_without_dominant_colors(tmp_path):
    """An analysis result without dominant colours must not be persisted."""
    photo = _photo()
    preview = tmp_path / "photo.jpg"
    preview.write_bytes(b"image")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(metadata_tasks.storage, "get_available_photo_path", return_value=str(preview)), \
         patch.object(metadata_tasks, "budgeted_open", lambda path: open(path, "rb")), \
         patch.object(metadata_tasks.Image, "open", lambda source: _FakeImage()), \
         patch.object(metadata_tasks, "extract_color_info", return_value={"dominant_colors": []}):
        metadata_tasks.update_photo_color_from_thumbnail(db, photo)

    db.add.assert_not_called()


def test_extract_task_metadata_rebuilds_when_cached_payload_is_corrupt():
    """A cached payload that cannot be decoded must fall back to a rebuild."""
    photo = _photo()
    data = {
        "file_path": "photo.jpg",
        "raw_metadata_version": 1,
        "raw_metadata": {"exif_info": "{not-json"},
    }

    with patch.object(metadata_tasks, "rebuild_metadata_cpu_job",
                      return_value={"success": True, "meta": {"rebuilt": True}}) as rebuild:
        result = metadata_tasks.extract_task_metadata(data, photo)

    assert result == {"success": True, "meta": {"rebuilt": True}}
    rebuild.assert_called_once()


# --------------------------------------------------------------------------- #
# app/api/media.py
# --------------------------------------------------------------------------- #


def test_finalize_chunk_upload_falls_back_to_copy_across_devices(tmp_path):
    """``os.replace`` cannot cross devices, so a copy must be used instead."""
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"payload")
    final_path = tmp_path / "final.jpg"

    real_replace = os.replace
    calls = {"count": 0}

    def flaky_replace(source, destination):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(source, destination)

    with patch.object(media_api.storage, "prepare_upload_path", return_value=str(final_path)), \
         patch.object(media_api.storage, "validate_target_path"), \
         patch.object(media_api.os, "replace", side_effect=flaky_replace):
        result = media_api._finalize_chunk_upload(
            str(chunk_dir), [0], "final.jpg", uuid4(), None, MagicMock()
        )

    assert result == str(final_path)
    assert final_path.read_bytes() == b"payload"


def test_finalize_chunk_upload_rejects_mismatched_chunk_count(tmp_path):
    """The chunk count must match the value announced by the client."""
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"payload")

    with patch.object(media_api.storage, "prepare_upload_path",
                      return_value=str(tmp_path / "final.jpg")), \
         patch.object(media_api.storage, "validate_target_path"):
        with pytest.raises(ValueError, match="chunk count"):
            media_api._finalize_chunk_upload(
                str(chunk_dir), [0], "final.jpg", uuid4(), None, MagicMock(), expected_chunks=3
            )


@pytest.mark.asyncio
async def test_upload_photo_generic_rejects_overlong_backup_key():
    """An oversized backup key is refused before any file is touched."""
    upload = StarletteUploadFile(filename="IMG_0001.jpg", file=io.BytesIO(b"image"))

    with pytest.raises(HTTPException) as excinfo:
        await media_api.upload_photo_generic(
            backup_key="k" * 256,
            file=upload,
            db=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert excinfo.value.status_code == 400
    assert "backup_key" in excinfo.value.detail


@pytest.mark.asyncio
async def test_upload_photo_generic_rejects_mismatched_live_photo_pair():
    """The companion clip must share the stem of the image and use a video extension."""
    upload = StarletteUploadFile(filename="IMG_0001.jpg", file=io.BytesIO(b"image"))
    companion = StarletteUploadFile(filename="IMG_0001.avi", file=io.BytesIO(b"clip"))

    with pytest.raises(HTTPException) as excinfo:
        await media_api.upload_photo_generic(
            file=upload,
            live_photo_video=companion,
            db=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert excinfo.value.status_code == 400
    assert "live photo pair" in excinfo.value.detail


@pytest.mark.asyncio
async def test_upload_photo_generic_rejects_live_photo_with_non_image_stem():
    """A clip whose stem differs from the image stem is not a live photo pair."""
    upload = StarletteUploadFile(filename="IMG_0001.jpg", file=io.BytesIO(b"image"))
    companion = StarletteUploadFile(filename="IMG_0002.mp4", file=io.BytesIO(b"clip"))

    with pytest.raises(HTTPException) as excinfo:
        await media_api.upload_photo_generic(
            file=upload,
            live_photo_video=companion,
            db=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert excinfo.value.status_code == 400
    assert "live photo pair" in excinfo.value.detail
