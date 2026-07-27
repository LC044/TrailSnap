"""Focused unit coverage for media thumbnail helpers and responses."""

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api


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
