"""Nightly coverage for the photo-organisation file transfer and the image
search endpoint.

The 2026-10-27 backend coverage scan reported:

* ``service/tasks/organize.py`` at 86.0% -- the compensation logic of
  ``_commit_transfer`` was never executed: neither the "file already back at
  the source" guard nor the "recovery failed, keep the file" escalation.
* ``api/search.py`` at 85.8% -- the ``folder`` search type, the error handler
  of the text search and the whole ``/search/image`` endpoint (AI call,
  non-200 answer, missing embedding) were never executed.

Neither needs a running service: the transfer runs against a temporary
directory and a mocked session, the search endpoint against a fake aiohttp
session.
"""

from __future__ import annotations

import os
import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import search as search_api
from app.service.tasks import organize as organize_service


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# service/tasks/organize.py -- _commit_transfer
# ---------------------------------------------------------------------------


def _photo(path):
    return SimpleNamespace(file_path=str(path), filename=os.path.basename(str(path)))


def test_commit_transfer_move_relocates_the_file_and_updates_the_photo(tmp_path):
    old = tmp_path / "old.jpg"
    old.write_bytes(b"payload")
    new = tmp_path / "new.jpg"
    db = MagicMock()
    photo = _photo(old)

    organize_service._commit_transfer(db, photo, str(old), str(new), move=True)

    assert not old.exists()
    assert new.read_bytes() == b"payload"
    assert photo.file_path == str(new)
    assert photo.filename == "new.jpg"
    db.commit.assert_called_once()


def test_commit_transfer_copy_keeps_the_source_file(tmp_path):
    old = tmp_path / "old.jpg"
    old.write_bytes(b"payload")
    new = tmp_path / "new.jpg"
    db = MagicMock()
    photo = _photo(old)

    organize_service._commit_transfer(db, photo, str(old), str(new), move=False)

    assert old.read_bytes() == b"payload"
    assert new.read_bytes() == b"payload"
    db.commit.assert_called_once()


def test_commit_transfer_restores_the_file_when_the_commit_fails(tmp_path):
    """A failed commit must put the file back where the database still points."""
    old = tmp_path / "old.jpg"
    old.write_bytes(b"payload")
    new = tmp_path / "new.jpg"
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit rejected")
    photo = _photo(old)

    with pytest.raises(RuntimeError, match="commit rejected"):
        organize_service._commit_transfer(db, photo, str(old), str(new), move=True)

    db.rollback.assert_called_once()
    # The moved file was rolled back to its original location.
    assert old.read_bytes() == b"payload"
    assert not new.exists()


def test_commit_transfer_removes_the_copy_when_the_commit_fails(tmp_path):
    old = tmp_path / "old.jpg"
    old.write_bytes(b"payload")
    new = tmp_path / "new.jpg"
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit rejected")
    photo = _photo(old)

    with pytest.raises(RuntimeError, match="commit rejected"):
        organize_service._commit_transfer(db, photo, str(old), str(new), move=False)

    # A copy leaves the source in place but must not leave a stray duplicate.
    assert old.read_bytes() == b"payload"
    assert not new.exists()


def test_commit_transfer_keeps_the_file_when_the_recovery_fails(tmp_path):
    """If the file cannot be put back, the operator has to be told where it is."""
    old = tmp_path / "old.jpg"
    old.write_bytes(b"payload")
    new = tmp_path / "new.jpg"
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit rejected")
    photo = _photo(old)

    real_exists = os.path.exists

    def _exists(path):
        # During the recovery the source path looks occupied again, so the
        # restore refuses to overwrite it.
        if str(path) == str(old):
            return True
        return real_exists(path)

    with patch.object(organize_service.os.path, "exists", side_effect=_exists):
        with pytest.raises(RuntimeError) as excinfo:
            organize_service._commit_transfer(db, photo, str(old), str(new), move=True)

    assert "整理失败且文件恢复未完成" in str(excinfo.value)
    assert str(new) in str(excinfo.value)
    assert new.read_bytes() == b"payload"


# ---------------------------------------------------------------------------
# api/search.py -- image search
# ---------------------------------------------------------------------------


# Every ``session.post`` call is recorded here so a test can assert on the
# request the server actually sent to the AI service.
SESSION_CALLS = []


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload if payload is not None else {}

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response):
        self._response = response

    def post(self, *args, **kwargs):
        SESSION_CALLS.append((args, kwargs))
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _user():
    return SimpleNamespace(id=uuid4())


def _patch_image_search(response, results=("r1",)):
    """Patch every collaborator of ``search_by_image``."""
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local"))
    return (
        patch.object(search_api.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(response)),
        patch.object(search_api.config_manager, "get_user_config", return_value=config),
        patch.object(search_api.crud_vector, "search_similar_vectors", return_value=list(results)),
        patch.object(search_api, "_build_vector_search_response", return_value=["built"]),
    )


def _upload():
    """A fake ``UploadFile`` that passes the image content-type check."""
    upload = MagicMock()
    upload.read = AsyncMock(return_value=b"bytes")
    upload.filename = "query.jpg"
    upload.content_type = "image/jpeg"
    return upload


def test_search_by_image_returns_vector_results():
    """``/search/image`` asks the AI service for one embedding per query image.

    Since the Chinese-CLIP rollout (REQ-205) the server posts the base64
    encoded image to ``/embedding/image`` and expects a *list* of embeddings
    back -- not the old ``{"embedding": [...]}`` envelope.
    """
    user = _user()
    db = MagicMock()
    upload = _upload()
    response = _FakeResponse(200, [[0.1, 0.2]])
    SESSION_CALLS.clear()

    client, config, vectors, builder = _patch_image_search(response)
    with client, config, vectors as search, builder:
        result = asyncio.run(
            search_api.search_by_image(upload, limit=5, threshold=0.1, db=db, user=user)
        )

    assert result.code == 200
    assert result.data == ["built"]
    assert search.call_args.kwargs["user_id"] == user.id

    # The query image is posted base64 encoded to the CLIP embedding endpoint.
    args, kwargs = SESSION_CALLS[0]
    assert args[0].endswith("/embedding/image")
    assert kwargs["json"] == {"images": [base64.b64encode(b"bytes").decode("ascii")]}


def test_search_by_image_surfaces_an_ai_service_error():
    user = _user()
    db = MagicMock()
    upload = _upload()
    response = _FakeResponse(500, {})

    client, config, vectors, builder = _patch_image_search(response)
    with client, config, vectors, builder:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                search_api.search_by_image(upload, limit=5, threshold=0.0, db=db, user=user)
            )

    # A non-200 answer from the AI service is an upstream failure (502),
    # not a server error of this endpoint.
    assert excinfo.value.status_code == 502
    assert "图片特征提取失败" in str(excinfo.value.detail)


def test_search_by_image_rejects_an_answer_without_an_embedding():
    user = _user()
    db = MagicMock()
    upload = _upload()
    response = _FakeResponse(200, [])

    client, config, vectors, builder = _patch_image_search(response)
    with client, config, vectors, builder:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                search_api.search_by_image(upload, limit=5, threshold=0.0, db=db, user=user)
            )

    assert excinfo.value.status_code == 502
    assert "图片特征" in str(excinfo.value.detail)


def test_search_by_image_rejects_a_non_image_upload():
    """A non-image upload is rejected before the AI service is contacted."""
    user = _user()
    db = MagicMock()
    upload = _upload()
    upload.content_type = "text/plain"
    SESSION_CALLS.clear()

    client, config, vectors, builder = _patch_image_search(_FakeResponse(200, [[0.1]]))
    with client, config, vectors, builder:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                search_api.search_by_image(upload, limit=5, threshold=0.0, db=db, user=user)
            )

    assert excinfo.value.status_code == 400
    assert SESSION_CALLS == []


def test_search_by_image_rejects_an_empty_upload():
    user = _user()
    db = MagicMock()
    upload = _upload()
    upload.read = AsyncMock(return_value=b"")
    SESSION_CALLS.clear()

    client, config, vectors, builder = _patch_image_search(_FakeResponse(200, [[0.1]]))
    with client, config, vectors, builder:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                search_api.search_by_image(upload, limit=5, threshold=0.0, db=db, user=user)
            )

    assert excinfo.value.status_code == 400
    assert SESSION_CALLS == []


def test_search_by_text_reports_a_500_when_the_query_fails():
    """A failing query must surface as a 500 instead of leaking the exception."""
    user = _user()
    db = MagicMock()
    db.query.side_effect = RuntimeError("query exploded")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            search_api.search_by_text(
                search_api.TextSearchRequest(text="trip", type="folder"),
                db=db,
                user=user,
            )
        )

    assert excinfo.value.status_code == 500
    assert "query exploded" in str(excinfo.value.detail)

