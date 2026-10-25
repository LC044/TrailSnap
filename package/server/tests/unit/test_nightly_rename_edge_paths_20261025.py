"""Nightly coverage for ``app.service.tasks.rename`` error branches.

The 2026-10-24 backend coverage report ranked ``service/tasks/rename.py``
at 81.6% with 18 statements never executed.  All of them sit on the
*defensive* paths of the batch planner:

* a target name that fails ``validate_target_path`` (Windows reserved
  names, over-long names, ...),
* a rename that fails on disk (file locked by another process),
* a path that cannot be resolved at all,
* the periodic commit that keeps long batches from losing all progress.

A batch rename touches the user's whole library, so the contract under
test is "a photo that cannot be renamed is skipped, never fatal, and never
silently reported as renamed".
"""

import asyncio
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.tasks import rename as rename_mod


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


def _make_photo(photo_id, file_path, photo_time=None, filename=None):
    return SimpleNamespace(
        id=photo_id,
        file_path=file_path,
        filename=filename or os.path.basename(file_path),
        owner_id="user-1",
        is_deleted=False,
        photo_time=photo_time or datetime(2026, 7, 31, 12, 0, 0),
        upload_time=None,
    )


def _mock_db(photos, metadata_rows=None):
    """Session mock matching the strategy's two ``query().filter().all()`` calls."""
    db = MagicMock()
    calls = [photos, metadata_rows or []]

    def _all(_self=None):
        return calls.pop(0) if calls else []

    chain = MagicMock()
    chain.all.side_effect = _all
    db.query.return_value.filter.return_value = chain
    return db


def _run(coro):
    return asyncio.run(coro)


def _write_photo(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"img")
    return str(path)


def test_metadata_template_uses_metadata_columns(tmp_path):
    """A template with a metadata variable pulls the value from PhotoMetadata."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)

    metadata = SimpleNamespace(
        photo_id="p1",
        city="上海",
        address="外滩",
        make="Canon",
        model="EOS",
        exif_info=None,
    )
    db = _mock_db([photo], [metadata])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{city}"}
    )

    result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result["success_count"] == 1
    assert photo.filename == "IMG_上海.jpg"
    assert os.path.exists(os.path.join(str(target_dir), "IMG_上海.jpg"))


def test_invalid_target_path_skips_the_photo(tmp_path):
    """A name rejected by ``validate_target_path`` is skipped, not renamed."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)
    db = _mock_db([photo])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{date}"}
    )

    with patch.object(rename_mod, "validate_target_path", side_effect=ValueError("bad name")):
        result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result == {"success_count": 0, "total_processed": 1}
    assert photo.file_path == file_path
    assert os.path.exists(file_path)


def test_validation_failure_after_collision_resolution_skips_the_photo(tmp_path):
    """The second validation pass (after collision suffixes) is honoured too."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)
    db = _mock_db([photo])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{date}"}
    )

    with patch.object(rename_mod, "validate_target_path", side_effect=[None, ValueError("bad name")]):
        result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result == {"success_count": 0, "total_processed": 1}
    assert photo.file_path == file_path


def test_failed_rename_is_not_counted_as_success(tmp_path):
    """A rename that fails on disk is reported as processed but not renamed."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)
    db = _mock_db([photo])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{date}"}
    )

    with patch.object(rename_mod.os, "rename", side_effect=OSError("file is locked")):
        result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result == {"success_count": 0, "total_processed": 1}
    assert photo.file_path == file_path
    assert os.path.exists(file_path)


def test_unresolvable_photo_path_excludes_the_photo(tmp_path):
    """A path that cannot be resolved excludes the photo from the batch."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)
    db = _mock_db([photo])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{date}"}
    )

    real_abspath = os.path.abspath

    def _fake_abspath(path):
        if path == file_path:
            raise OSError("cwd was removed")
        return real_abspath(path)

    with patch.object(rename_mod.os.path, "abspath", side_effect=_fake_abspath):
        result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result == {"success_count": 0, "total_processed": 0}
    assert photo.file_path == file_path


def test_unresolvable_source_path_does_not_abort_the_batch(tmp_path):
    """A failure while collecting sibling source paths is tolerated."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()
    file_path = _write_photo(target_dir, "raw.jpg")
    photo = _make_photo("p1", file_path)
    db = _mock_db([photo])
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{date}"}
    )

    real_abspath = os.path.abspath
    seen = {"count": 0}

    def _fake_abspath(path):
        if path == file_path:
            seen["count"] += 1
            # 1st call: the "is it under the target root?" check.
            # 2nd call: collecting the sibling source paths.
            if seen["count"] == 2:
                raise OSError("cwd was removed")
        return real_abspath(path)

    with patch.object(rename_mod.os.path, "abspath", side_effect=_fake_abspath):
        result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result["total_processed"] == 1
    assert result["success_count"] == 1
    assert photo.filename == "IMG_2026-07-31.jpg"


def test_long_batch_commits_progress_periodically(tmp_path):
    """Batches larger than 50 photos commit their progress while running."""
    target_dir = tmp_path / "photos"
    target_dir.mkdir()

    photos = []
    base = datetime(2026, 7, 31, 12, 0, 0)
    for index in range(50):
        file_path = _write_photo(target_dir, f"raw-{index}.jpg")
        photos.append(_make_photo(f"p{index}", file_path, photo_time=base + timedelta(seconds=index)))

    db = _mock_db(photos)
    task = _build_task(
        payload={"target_root_path": str(target_dir), "template": "IMG_{sequence4}"}
    )

    result = _run(rename_mod.BatchRenameStrategy().process(worker=None, task=task, db=db))

    assert result == {"success_count": 50, "total_processed": 50}
    # One commit for the item counter, one for the 50th item, one at the end.
    assert db.commit.call_count >= 2
