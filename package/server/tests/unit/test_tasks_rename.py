"""Unit tests for ``app/service/tasks/rename.py``.

The batch rename strategy is the in-task companion of the toolbox page. It
walks every photo under a target root, builds a new name from a template,
and resolves collisions in memory so siblings can be renamed in the same
batch. We focus on the bits the toolbox UI relies on:

* Missing ``target_root_path`` -- 400-equivalent ValueError.
* Collision avoidance -- two photos that would clash get sequential
  ``(1)``, ``(2)`` suffixes.
* Already-correct names -- the photo is left alone (no-op entry).
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _build_task(payload, owner_id="user-1"):
    return SimpleNamespace(
        id="task-rename",
        type="BATCH_RENAME",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
    )


def _make_photo(file_id, file_path, photo_time=None, filename=None):
    return SimpleNamespace(
        id=file_id,
        file_path=file_path,
        filename=filename or os.path.basename(file_path),
        owner_id="user-1",
        is_deleted=False,
        photo_time=photo_time, upload_time=None,
    )


def _mock_db(photos, metadata_rows=None):
    """Build a MagicMock session whose ``query(...).filter(...).all()``
    pattern returns ``photos`` for the first call and ``metadata_rows`` for
    the second. The strategy makes two such queries: Photo then PhotoMetadata.
    """
    db = MagicMock()
    calls = [photos, metadata_rows or []]

    def _all(_self=None):
        # Pop the next planned return. Once exhausted, fall back to empty.
        return calls.pop(0) if calls else []

    chain = MagicMock()
    chain.all.side_effect = _all
    db.query.return_value.filter.return_value = chain
    return db


def _run(coro):
    return asyncio.run(coro)


def test_process_raises_value_error_when_target_root_missing(tmp_path):
    """The strategy should refuse to run without a target root."""
    from app.service.tasks import rename as rename_mod

    db = _mock_db([])
    task = _build_task(payload={"template": "IMG_{date}"})

    with pytest.raises(ValueError, match="target_root_path"):
        _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))


def test_process_leaves_already_correctly_named_photo_untouched(tmp_path):
    """If the new name equals the current name, no rename should happen."""
    from app.service.tasks import rename as rename_mod

    from datetime import datetime

    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = target_dir / "2026-07-31_120000.jpg"
    file_path.write_bytes(b"img")
    photo = _make_photo("p1", str(file_path), photo_time=datetime(2026, 7, 31, 12, 0, 0))
    db = _mock_db([photo])

    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "{date}_{time}"}
    )

    result = _run(
        rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db)
    )

    assert result["success_count"] == 0
    assert result["total_processed"] == 1
    # File on disk should be untouched.
    assert os.path.exists(file_path)


def test_process_renames_photo_to_template(tmp_path):
    """Plain rename when the target name is free."""
    from app.service.tasks import rename as rename_mod

    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    src = target_dir / "IMG_old.jpg"
    src.write_bytes(b"img")
    photo = _make_photo("p1", str(src))
    db = _mock_db([photo])

    task = _build_task(
        payload={
            "target_root_path": str(target_dir),
            "template": "renamed_{sequence3}",
        }
    )

    result = _run(
        rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db)
    )

    assert result["success_count"] == 1
    assert os.path.exists(target_dir / "renamed_001.jpg")
    assert not os.path.exists(src)
    assert photo.file_path == str(target_dir / "renamed_001.jpg")


def test_process_avoids_collisions_with_counter_suffix(tmp_path):
    """Two photos that would clash get sequential ``(N)`` suffixes."""
    from app.service.tasks import rename as rename_mod

    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    a = target_dir / "a.jpg"
    b = target_dir / "b.jpg"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    p1 = _make_photo("p1", str(a))
    p2 = _make_photo("p2", str(b))
    db = _mock_db([p1, p2])

    task = _build_task(
        payload={
            "target_root_path": str(target_dir),
            "template": "collide",
        }
    )

    result = _run(
        rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db)
    )

    # Both files should land in the target dir, with ``(1)`` on the second.
    assert result["success_count"] == 2
    assert os.path.exists(target_dir / "collide.jpg")
    assert os.path.exists(target_dir / "collide(1).jpg")

