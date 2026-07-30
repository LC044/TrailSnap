"""Unit tests for ``app/service/tasks/duplicate.py``.

The duplicate finder is a small async strategy that:
1. Loads every photo for the user with an empty ``md5`` column.
2. Computes MD5s in concurrent batches of 20 via ``calculate_file_md5_async``.
3. Persists the new MD5s back to the ``photo.md5`` column and writes a
   ``Task.result`` summary.

We mock the SQLAlchemy session, the model, and the MD5 coroutine so the
strategy can be exercised without disk or DB.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.models.task import TaskStatus

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload=None, owner_id="user-1"):
    """Build a Task-like SimpleNamespace with the fields the strategy reads."""
    return SimpleNamespace(
        id="task-1",
        type="FIND_DUPLICATE_PHOTOS",
        owner_id=owner_id,
        payload=payload or {},
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_photo(file_path, md5=""):
    return SimpleNamespace(file_path=file_path, md5=md5, owner_id="user-1")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_process_returns_zero_count_when_no_photos_need_md5():
    """If every photo already has an MD5, the strategy should short-circuit."""
    from app.service.tasks import duplicate

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    task = _build_task()

    result = asyncio.run(
        duplicate.FindDuplicatePhotosStrategy().process(worker=None, task=task, db=db)
    )

    assert result == {"status": TaskStatus.COMPLETED, "count": 0}
    assert task.total_items == 0
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"message": "No photos need MD5 calculation"}


def test_process_updates_md5_for_existing_files(tmp_path):
    """Photos with real files on disk get their MD5 written back."""
    from app.service.tasks import duplicate

    file_a = tmp_path / "a.jpg"
    file_a.write_bytes(b"hello")
    file_b = tmp_path / "b.jpg"
    file_b.write_bytes(b"world")

    photos = [_make_photo(str(file_a)), _make_photo(str(file_b))]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = photos
    task = _build_task()

    async def fake_md5(path):
        # Deterministic per file so we can assert per-photo assignment.
        if path.endswith("a.jpg"):
            return "md5-aaa"
        if path.endswith("b.jpg"):
            return "md5-bbb"
        return ""

    with patch.object(duplicate, "calculate_file_md5_async", side_effect=fake_md5):
        result = asyncio.run(
            duplicate.FindDuplicatePhotosStrategy().process(worker=None, task=task, db=db)
        )

    assert result == {"status": TaskStatus.COMPLETED, "updated_count": 2}
    assert photos[0].md5 == "md5-aaa"
    assert photos[1].md5 == "md5-bbb"
    assert task.total_items == 2
    assert task.processed_items == 2
    assert task.status == TaskStatus.COMPLETED
    # task.result is the JSON envelope; updated_count is the headline.
    assert task.result == {"updated_count": 2}


def test_process_skips_missing_files_and_assigns_empty_md5(tmp_path):
    """Missing files should not crash the run; they count as not-updated."""
    from app.service.tasks import duplicate

    real = tmp_path / "exists.jpg"
    real.write_bytes(b"hi")
    missing = tmp_path / "ghost.jpg"
    # Note: missing is intentionally never created on disk.

    photos = [_make_photo(str(real)), _make_photo(str(missing))]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = photos
    task = _build_task()

    async def fake_md5(path):
        if path.endswith("exists.jpg"):
            return "md5-real"
        return ""

    with patch.object(duplicate, "calculate_file_md5_async", side_effect=fake_md5):
        result = asyncio.run(
            duplicate.FindDuplicatePhotosStrategy().process(worker=None, task=task, db=db)
        )

    assert result["updated_count"] == 1
    assert photos[0].md5 == "md5-real"
    # Missing file path gets a None md5 from the strategy (empty string from
    # the fake coroutine is falsy and skipped, so md5 stays at "").
    assert photos[1].md5 == ""

