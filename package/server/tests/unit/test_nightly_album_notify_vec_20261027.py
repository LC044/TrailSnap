"""Nightly coverage for the album router's write paths, the notification
pub/sub singletons and the face-vector embedding cache.

The 2026-10-27 backend coverage scan reported:

* ``api/album.py`` at 86.2% -- ``create_album`` never built a query embedding
  nor enqueued the async album scan, the cover auto-assignment never ran, and
  the ownership guards of ``delete_album`` / ``upload_photo`` /
  ``delete_photo`` were never executed.
* ``service/notification_manager.py`` at 87.5% -- the closed-loop guard, the
  "queue is full" drop path and the subscriber-gone error path were never
  executed.
* ``service/face_vector_cache.py`` at 80.8% -- the environment parser's
  fallback branches, the vector packer's dimension guard, the shard growth
  path and the per-owner invalidation were never executed.

None of the branches need external services: the album router is driven
through patched CRUD helpers, the notification manager is exercised with
plain ``asyncio`` queues and the vector cache is a pure in-memory object.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from app.api import album as album_api
from app.service import face_vector_cache as fvc
from app.service.notification_manager import NotificationManager


pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _album(owner_id=None, **kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", uuid4()),
        owner_id=owner_id or uuid4(),
        name=kwargs.get("name", "Vacation"),
        type=kwargs.get("type", "normal"),
        cover_id=kwargs.get("cover_id"),
        cover=kwargs.get("cover"),
        description=kwargs.get("description"),
    )


# ---------------------------------------------------------------------------
# api/album.py -- create_album
# ---------------------------------------------------------------------------


def test_create_smart_album_builds_embedding_and_enqueues_scan():
    """A smart album with a description becomes a vector query."""
    user = _user()
    db = MagicMock()
    created = _album(owner_id=user.id, type="smart")
    payload = album_api.schemas.AlbumCreate(name="Beach", type="smart", description="sunset")

    with (
        patch.object(album_api, "async_get_embedding", new=AsyncMock(return_value=[0.1, 0.2])) as embedding,
        patch.object(album_api.crud, "create_album", return_value=created) as create,
        patch.object(album_api.TaskManager, "get_instance") as get_instance,
    ):
        manager = get_instance.return_value
        response = asyncio.run(album_api.create_album(payload, MagicMock(), db, user))

    embedding.assert_awaited_once_with("sunset", user.id, db)
    assert create.call_args.kwargs["query_embedding"] == [0.1, 0.2]
    manager.add_task.assert_called_once()
    assert manager.add_task.call_args.args[1] == album_api.TaskType.SCAN_ALBUM
    assert manager.add_task.call_args.kwargs["payload"] == {"album_id": str(created.id)}
    assert response.data is created


def test_create_normal_album_skips_embedding_and_scan():
    """A normal album must not spend an embedding call nor queue a scan."""
    user = _user()
    db = MagicMock()
    created = _album(owner_id=user.id, type="normal")
    payload = album_api.schemas.AlbumCreate(name="Trip", type="normal")

    with (
        patch.object(album_api, "async_get_embedding", new=AsyncMock()) as embedding,
        patch.object(album_api.crud, "create_album", return_value=created),
        patch.object(album_api.TaskManager, "get_instance") as get_instance,
    ):
        response = asyncio.run(album_api.create_album(payload, MagicMock(), db, user))

    embedding.assert_not_awaited()
    get_instance.return_value.add_task.assert_not_called()
    assert response.data is created


# ---------------------------------------------------------------------------
# api/album.py -- cover auto-assignment
# ---------------------------------------------------------------------------


def test_read_album_assigns_earliest_photo_as_cover():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)
    early = SimpleNamespace(id=uuid4(), photo_time=None, upload_time=1)
    late = SimpleNamespace(id=uuid4(), photo_time=None, upload_time=99)

    with (
        patch.object(album_api.crud, "get_album", return_value=album),
        patch.object(album_api.app.crud.photo, "get_photos", return_value=[late, early]),
    ):
        response = album_api.read_album(album.id, db, user)

    assert album.cover_id == early.id
    assert album.cover is early
    db.commit.assert_called_once()
    assert response.data is album


def test_read_album_keeps_working_when_cover_assignment_fails():
    """A failing cover assignment must not break the album read."""
    user = _user()
    db = MagicMock()
    db.commit.side_effect = RuntimeError("db down")
    album = _album(owner_id=user.id)
    photo = SimpleNamespace(id=uuid4(), photo_time=None, upload_time=1)

    with (
        patch.object(album_api.crud, "get_album", return_value=album),
        patch.object(album_api.app.crud.photo, "get_photos", return_value=[photo]),
    ):
        response = album_api.read_album(album.id, db, user)

    assert response.data is album


# ---------------------------------------------------------------------------
# api/album.py -- ownership guards
# ---------------------------------------------------------------------------


def test_delete_album_rejects_a_different_owner():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=uuid4())

    with patch.object(album_api.crud, "get_album", return_value=album):
        response = album_api.delete_album(album.id, db, user)

    assert response.code == 403
    assert response.data is None


def test_upload_photo_rejects_missing_album_and_foreign_owner():
    user = _user()
    db = MagicMock()
    upload = MagicMock()
    album_id = uuid4()

    with patch.object(album_api.crud, "get_album", return_value=None):
        missing = asyncio.run(album_api.upload_photo(album_id, upload, db, user))
    assert missing.code == 404

    foreign = _album(owner_id=uuid4())
    with patch.object(album_api.crud, "get_album", return_value=foreign):
        denied = asyncio.run(album_api.upload_photo(album_id, upload, db, user))
    assert denied.code == 403


def test_upload_photo_forwards_to_the_generic_handler():
    user = _user()
    db = MagicMock()
    upload = MagicMock()
    album = _album(owner_id=user.id)
    sentinel = SimpleNamespace(code=0, data="uploaded")

    with (
        patch.object(album_api.crud, "get_album", return_value=album),
        patch.object(album_api, "upload_photo_generic", new=AsyncMock(return_value=sentinel)) as generic,
    ):
        response = asyncio.run(album_api.upload_photo(album.id, upload, db, user))

    generic.assert_awaited_once_with(album_id=album.id, file=upload, db=db, current_user=user)
    assert response is sentinel


def test_delete_photo_reports_404_when_photo_is_not_in_album():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)
    photo_id = uuid4()

    with (
        patch.object(album_api.crud, "get_album", return_value=album),
        patch.object(album_api.crud, "batch_update_album_association", return_value=0),
    ):
        response = album_api.delete_photo(album.id, photo_id, db, user)

    assert response.code == 404
    assert response.data is None


# ---------------------------------------------------------------------------
# service/notification_manager.py
# ---------------------------------------------------------------------------


def _manager():
    manager = NotificationManager()
    manager._subscribers = []
    manager._loop = None
    return manager


def test_publish_to_user_only_reaches_the_matching_subscriber():
    manager = _manager()
    mine = manager.subscribe("u1")
    theirs = manager.subscribe("u2")

    manager.publish_to_user("u1", "task.done", {"n": 1})

    assert mine.get_nowait() == {"event": "task.done", "data": {"n": 1}}
    assert theirs.empty()


def test_publish_with_no_target_broadcasts_to_every_subscriber():
    manager = _manager()
    first = manager.subscribe("u1")
    second = manager.subscribe(None)

    manager.publish_to_user(None, "system.notice", {"k": "v"})

    assert first.get_nowait()["event"] == "system.notice"
    assert second.get_nowait()["event"] == "system.notice"


def test_publish_to_a_closed_loop_is_dropped_instead_of_raising():
    """A loop that shut down between publish and dispatch must not raise."""
    manager = _manager()
    queue = manager.subscribe("u1")

    class _ClosedLoop:
        def call_soon_threadsafe(self, *args, **kwargs):
            raise RuntimeError("event loop is closed")

    manager.attach_loop(_ClosedLoop())
    manager.publish_to_user("u1", "task.done", {"n": 1})

    assert queue.empty()


def test_publish_drops_the_oldest_message_when_the_queue_is_full():
    manager = _manager()
    queue = manager.subscribe("u1")
    for index in range(256):
        queue.put_nowait({"event": "old", "data": index})

    manager.publish_to_user("u1", "task.done", {"n": 1})

    # The queue keeps its newest 256 entries: the oldest one was evicted.
    assert queue.qsize() == 256
    assert queue.get_nowait()["data"] == 1


def test_unsubscribe_only_removes_the_target_queue():
    manager = _manager()
    kept = manager.subscribe("u1")
    dropped = manager.subscribe("u2")

    manager.unsubscribe(dropped)
    manager.publish_to_user("u1", "task.done", {"n": 1})

    assert kept.get_nowait()["event"] == "task.done"
    assert dropped.empty()


def test_publish_to_a_broken_queue_is_swallowed():
    """A subscriber that disappears mid-flight must not break the publisher."""
    manager = _manager()
    broken = manager.subscribe("u1")
    healthy = manager.subscribe("u1")

    def _boom():
        raise RuntimeError("subscriber went away")

    broken.put_nowait = _boom  # type: ignore[method-assign]
    manager.publish_to_user("u1", "task.done", {"n": 1})

    assert healthy.get_nowait()["event"] == "task.done"


# ---------------------------------------------------------------------------
# service/face_vector_cache.py
# ---------------------------------------------------------------------------


def test_env_int_falls_back_to_the_default_for_bad_values(monkeypatch):
    monkeypatch.setenv("TS_FACE_CACHE_MAX_ROWS", "not-a-number")
    assert fvc._env_int("TS_FACE_CACHE_MAX_ROWS", 150_000) == 150_000

    monkeypatch.setenv("TS_FACE_CACHE_MAX_ROWS", "0")
    assert fvc._env_int("TS_FACE_CACHE_MAX_ROWS", 150_000) == 150_000

    monkeypatch.setenv("TS_FACE_CACHE_MAX_ROWS", "-5")
    assert fvc._env_int("TS_FACE_CACHE_MAX_ROWS", 150_000) == 150_000

    monkeypatch.setenv("TS_FACE_CACHE_MAX_ROWS", "42")
    assert fvc._env_int("TS_FACE_CACHE_MAX_ROWS", 150_000) == 42

    monkeypatch.delenv("TS_FACE_CACHE_MAX_ROWS", raising=False)
    assert fvc._env_int("TS_FACE_CACHE_MAX_ROWS", 150_000) == 150_000


def test_pack_leaves_none_and_mismatched_vectors_zeroed():
    packed = fvc._pack([[3.0, 4.0], None, [1.0, 2.0, 3.0]], 2)

    assert packed.shape == (3, 2)
    # The valid row is L2-normalised.
    assert np.allclose(packed[0], [0.6, 0.8], atol=1e-6)
    # A missing vector and a vector of the wrong dimension stay zeroed, so they
    # can never win a nearest-neighbour comparison.
    assert np.allclose(packed[1], [0.0, 0.0])
    assert np.allclose(packed[2], [0.0, 0.0])


def test_shard_append_grows_its_buffer_and_tracks_the_watermark():
    shard = fvc._Shard()

    shard.append([], [])
    assert shard.size == 0

    # The first append establishes the dimension.
    shard.append([1], [[1.0, 0.0]])
    assert shard._dim == 2
    assert shard.max_face_id == 1

    # Growing past the reserved capacity must keep the earlier rows intact.
    for offset in range(2, 400):
        shard.append([offset], [[1.0, 0.0]])
    assert shard.size == 399
    assert shard.max_face_id == 399
    assert list(shard.ids[:399]) == list(range(1, 400))
    assert np.allclose(shard.matrix[0], [1.0, 0.0])


def test_shard_append_ignores_vectors_without_a_dimension():
    shard = fvc._Shard()
    shard.append([7], [None])
    assert shard.size == 0
    assert shard.max_face_id == 0


def test_cache_invalidate_drops_one_owner_or_everything():
    cache = fvc.FaceVectorCache(max_rows=1000)
    cache._shards["u1"] = fvc._Shard()
    cache._shards["u2"] = fvc._Shard()
    cache._oversized.add("u2")

    cache.invalidate("u1")
    assert "u1" not in cache._shards
    assert "u2" in cache._shards
    assert cache.stats()["oversized"] == ["u2"]

    cache.invalidate()
    assert cache.stats()["shards"] == 0
    assert cache.stats()["oversized"] == []


def test_cache_evicts_the_oldest_shard_to_stay_under_the_budget():
    cache = fvc.FaceVectorCache(max_rows=fvc._MIN_SHARD_CAPACITY)
    first = fvc._Shard()
    first.append([1], [[1.0, 0.0]])
    second = fvc._Shard()
    second.append([2], [[0.0, 1.0]])
    cache._shards["old"] = first
    cache._shards["new"] = second

    # A third owner does not fit: the oldest shard is dropped.
    cache._evict_until_fits(fvc._MIN_SHARD_CAPACITY, "new")

    assert "old" not in cache._shards
    assert "new" in cache._shards


def test_cache_stats_report_rows_and_allocated_rows():
    cache = fvc.FaceVectorCache(max_rows=1000)
    shard = fvc._Shard()
    shard.append([1, 2], [[1.0, 0.0], [0.0, 1.0]])
    cache._shards["u1"] = shard

    stats = cache.stats()
    assert stats["shards"] == 1
    assert stats["rows"] == 2
    assert stats["allocated_rows"] >= stats["rows"]
    assert stats["max_rows"] == 1000
    assert stats["oversized"] == []




