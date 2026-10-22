"""Unit tests for ``app/service/tasks/image_embedding.py`` error paths.

The 2026-10-22 coverage scan showed the module at 70.7% (51 missed of
174). The misses concentrated on two places:

* the *owner-level* ``except`` inside ``process_batch`` -- when anything
  blows up while embedding one owner's photos, the batch must roll the
  transaction back, drop the partial results for that owner and report a
  failed entry for every task of that owner;
* ``process_single_photo`` -- the per-photo path that talks to the AI
  service, persists the vector and flips the ``image_embedding`` marker.

Both paths decide whether a photo is considered embedded, so a silent
regression there would re-embed every photo on the next sweep.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload, *, owner_id="user-1", task_id=None):
    return SimpleNamespace(
        id=task_id or f"task-{payload.get('photo_id', 'gen')}",
        type="IMAGE_EMBEDDING",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_photo(pid, *, owner_id="user-1", file_path="/fake/photo.jpg"):
    return SimpleNamespace(
        id=pid,
        file_type="image",
        processed_tasks={},
        owner_id=owner_id,
        file_path=file_path,
    )


def _ai_response(status=200, *, embeddings=None, body_text="error"):
    resp = MagicMock()
    resp.status = status
    if status == 200:
        resp.json = AsyncMock(return_value=embeddings or [])
    else:
        resp.text = AsyncMock(return_value=body_text)
        resp.json = AsyncMock(return_value={})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_with(response):
    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _patch_ai_config(monkeypatch, *, url="http://fake-ai"):
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url=url))
    monkeypatch.setattr(
        "app.service.tasks.image_embedding.config_manager.get_user_config",
        lambda owner_id, db: cfg,
    )


def _patch_storage(monkeypatch, *, target="/fake/photo.jpg"):
    monkeypatch.setattr(
        "app.service.tasks.image_embedding.storage.get_available_photo_path",
        lambda owner_id, photo_id, file_path: target,
    )


# ---------------------------------------------------------------------------
# process_batch: owner-level failure
# ---------------------------------------------------------------------------


def test_process_batch_rolls_back_and_fails_every_task_of_the_owner(monkeypatch):
    """A mid-batch failure must not leave partial results behind."""
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    task = _build_task({"photo_id": "p-1"}, task_id="t-1")

    # The photo lookup itself explodes -> the whole owner batch fails.
    db.query.side_effect = RuntimeError("db gone")

    results = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_batch(worker=None, tasks=[task], db=db)
    )

    db.rollback.assert_called_once()
    assert len(results) == 1
    assert results[0]["task_id"] == "t-1"
    assert results[0]["status"] == "failed"
    assert "db gone" in results[0]["error"]


def test_process_batch_keeps_results_of_other_owners_when_one_fails(monkeypatch):
    """One owner's failure must not discard another owner's success."""
    from app.service.tasks import image_embedding as ie_mod

    good_photo = _make_photo("p-ok", owner_id="user-good")
    db = MagicMock()

    from app.db.models.image_vector import ImageVector
    from app.db.models.photo import Photo

    photo_lookups = {"count": 0}

    def _query(model, *args, **kwargs):
        query = MagicMock()
        query.filter.return_value = query
        if model is Photo:
            photo_lookups["count"] += 1
            if photo_lookups["count"] == 1:
                query.all.return_value = [good_photo]
            else:
                query.all.side_effect = RuntimeError("owner-bad exploded")
        else:
            query.all.return_value = []
        return query

    db.query.side_effect = _query

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    good_task = _build_task({"photo_id": "p-ok"}, owner_id="user-good", task_id="t-good")
    bad_task = _build_task({"photo_id": "p-bad"}, owner_id="user-bad", task_id="t-bad")

    resp = _ai_response(200, embeddings=[[0.1, 0.2]])
    session = _session_with(resp)

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n\x1a\n")):
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[good_task, bad_task], db=db,
            )
        )

    by_id = {item["task_id"]: item for item in results}
    assert by_id["t-good"]["status"] == "completed"
    assert by_id["t-bad"]["status"] == "failed"
    assert "owner-bad exploded" in by_id["t-bad"]["error"]


# ---------------------------------------------------------------------------
# process_single_photo
# ---------------------------------------------------------------------------


def test_process_single_photo_persists_vector_and_marks_photo(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(200, embeddings=[[0.1, 0.2, 0.3]])
    session = _session_with(resp)

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n\x1a\n")):
        result = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_single_photo(
                worker=None, photo=photo, db=db,
            )
        )

    assert result == {"status": "success", "embedding_size": 3}
    assert photo.processed_tasks["image_embedding"] is True
    db.commit.assert_called()


def test_process_single_photo_reports_missing_file(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()

    monkeypatch.setattr(
        "app.service.tasks.image_embedding.storage.get_available_photo_path",
        lambda owner_id, photo_id, file_path: None,
    )

    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_single_photo(
            worker=None, photo=photo, db=db,
        )
    )

    assert result == {"status": "failed", "error": "file not found"}


def test_process_single_photo_reports_empty_embedding(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(200, embeddings=[])
    session = _session_with(resp)

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n\x1a\n")):
        result = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_single_photo(
                worker=None, photo=photo, db=db,
            )
        )

    assert result == {"status": "failed", "error": "No embedding returned"}


def test_process_single_photo_surfaces_ai_service_error(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(500, body_text="boom")
    session = _session_with(resp)

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n\x1a\n")):
        result = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_single_photo(
                worker=None, photo=photo, db=db,
            )
        )

    assert result["status"] == "failed"
    assert "500" in result["error"]


def test_process_single_photo_clears_marker_and_reraises_on_failure(monkeypatch):
    """A crash must clear the marker so the photo is retried next sweep."""
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(200, embeddings=[[0.1]])
    session = _session_with(resp)

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", side_effect=OSError("disk gone")):
        with pytest.raises(OSError, match="disk gone"):
            asyncio.run(
                ie_mod.ImageEmbeddingStrategy().process_single_photo(
                    worker=None, photo=photo, db=db,
                )
            )

    assert photo.processed_tasks["image_embedding"] is False
    db.commit.assert_called()
