"""Unit tests for ``app/service/tasks/image_embedding.py``.

The ImageEmbeddingStrategy has two entry points:

1. ``process`` with ``photo_id`` in the payload -- a per-photo job that
   short-circuits when the ``image_embedding`` marker is already set on the
   photo row.
2. ``process`` without ``photo_id`` -- a generator over all photos that
   queues one IMAGE_EMBEDDING child task per photo that still needs an
   embedding.

Coverage:

* Single-photo mode: photo with the marker set is skipped.
* Single-photo mode: photo without the marker falls through to
  ``process_single_photo``.
* Generator mode queues a task only for photos whose marker is absent;
  videos and already-processed photos are skipped.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload):
    return SimpleNamespace(
        id="task-emb",
        type="IMAGE_EMBEDDING",
        owner_id="user-1",
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_photo(pid, file_type="image", marker=False, owner_id="user-1"):
    return SimpleNamespace(
        id=pid,
        file_type=file_type,
        processed_tasks={"image_embedding": True} if marker else {},
        owner_id=owner_id,
    )


def test_single_photo_skips_when_marker_already_set():
    """A photo that already has an embedding is reported as ``skipped``."""
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1", marker=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    task = _build_task({"photo_id": "p-1"})

    import asyncio
    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process(worker=None, task=task, db=db)
    )

    assert result == {"status": "skipped", "reason": "already processed"}


def test_single_photo_skips_when_photo_not_found():
    """An unknown ``photo_id`` is short-circuited."""
    from app.service.tasks import image_embedding as ie_mod

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    task = _build_task({"photo_id": "p-missing"})

    import asyncio
    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process(worker=None, task=task, db=db)
    )

    assert result == {"status": "skipped", "reason": "photo not found"}


def test_single_photo_falls_through_to_process_single_photo():
    """A photo without the marker delegates to ``process_single_photo``."""
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-2", marker=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    task = _build_task({"photo_id": "p-2"})

    strategy = ie_mod.ImageEmbeddingStrategy()
    sentinel = {"status": "ok", "photo_id": "p-2"}
    with patch.object(
        strategy, "process_single_photo", new=AsyncMock(return_value=sentinel)
    ) as single:
        import asyncio
        result = asyncio.run(
            strategy.process(worker=None, task=task, db=db)
        )

    assert result == sentinel
    single.assert_awaited_once()


def test_generator_mode_skips_videos_and_processed_photos():
    """Generator mode only queues tasks for photos that still need embedding."""
    from app.service.tasks import image_embedding as ie_mod

    class _ImageType:
        pass

    class _FileType:
        video = "video"
        image = "image"

    # Patch the FileType the strategy module imported so we can label videos.
    ie_mod.FileType = _FileType()

    pending = _make_photo("p-a", file_type="image", marker=False)
    already = _make_photo("p-b", file_type="image", marker=True)
    video = _make_photo("p-c", file_type="video", marker=False)

    db = MagicMock()
    # Generator loops ``while True`` with offset / limit pagination, so we
    # simulate two pages: page 1 has the three candidates; page 2 is empty.
    query = MagicMock()
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.side_effect = [[pending, already, video], []]
    db.query.return_value = query

    task = _build_task({})

    worker = MagicMock()
    worker.add_tasks = MagicMock()

    import asyncio
    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process(worker=worker, task=task, db=db)
    )

    # Only the unmarked, non-video photo should be queued.
    worker.add_tasks.assert_called_once()
    queued = worker.add_tasks.call_args[0][1]
    assert len(queued) == 1
    assert queued[0]["payload"]["photo_id"] == "p-a"
    # Public envelope reports the number of generated tasks.
    assert result["generated_tasks"] == 1
    assert "Generated 1 image embedding tasks" in result["message"]