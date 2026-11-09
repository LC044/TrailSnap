"""Nightly watch 2026-11-09: media API guard gaps.

Targets uncovered branches reported by the 2026-11-09 coverage snapshot for
``app/api/media.py``:

* ``get_static_thumbnail`` - thumbnail path escaping the user root, and the
  ``os.path.commonpath`` ValueError fallback (different drives on Windows).
* ``get_live_photo_video`` - malformed ``Range`` header falls back to the
  full-file response instead of raising.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.api import media
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.user import User

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _run(coro):
    return asyncio.run(coro)


def test_get_static_thumbnail_rejects_path_outside_user_root(tmp_path):
    owner_id = uuid4()
    user_root = tmp_path / "user"
    user_root.mkdir()
    outside = tmp_path / "elsewhere" / "thumb.webp"

    with patch.object(media.user_storage, "get_cached_storage_base", return_value={"location": str(user_root)}), \
         patch.object(media.user_storage, "get_user_root", return_value=str(user_root)), \
         patch.object(media, "_get_thumbnail_path", return_value=str(outside)):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.get_static_thumbnail(owner_id, uuid4(), size="small"))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Thumbnail not found"


def test_get_static_thumbnail_handles_commonpath_value_error(tmp_path):
    owner_id = uuid4()
    user_root = tmp_path / "user"
    user_root.mkdir()

    with patch.object(media.user_storage, "get_cached_storage_base", return_value={"location": str(user_root)}), \
         patch.object(media.user_storage, "get_user_root", return_value=str(user_root)), \
         patch.object(media, "_get_thumbnail_path", return_value=str(user_root / "thumb.webp")), \
         patch.object(media.os.path, "commonpath", side_effect=ValueError("different drives")):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.get_static_thumbnail(owner_id, uuid4(), size="small"))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Thumbnail not found"


def test_get_live_photo_video_falls_back_when_range_header_is_invalid(db, tmp_path):
    owner_id = uuid4()
    db.add(User(id=owner_id, username="nightly-media-owner", hashed_password="x"))
    source = tmp_path / "clip.jpg"
    source.write_bytes(b"jpeg")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video-bytes")

    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename="clip.jpg",
        file_path=str(source),
        file_type=FileType.live_photo,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()

    with patch.object(media, "_get_thumbnail_path", return_value=str(tmp_path / "thumb.webp")):
        response = _run(
            media.get_live_photo_video(photo.id, request=None, range="bytes=abc", db=db)
        )

    assert isinstance(response, FileResponse)
    assert response.headers.get("Accept-Ranges") == "bytes"

