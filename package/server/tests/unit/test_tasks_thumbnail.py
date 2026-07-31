"""Unit tests for ``app/service/tasks/thumbnail.py``.

The thumbnail rebuild path is the CPU side of the GENERATE_THUMBNAIL task.
We focus on the two outcomes that matter for an operator:

1. Happy path -- a real image file produces a thumbnail and color info.
2. Missing / unreadable file -- the job returns a failure envelope without
   raising (the worker logs and moves on).
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _make_png(path, size=(8, 8), color=(255, 0, 0)):
    """Write a tiny solid-color PNG to ``path``."""
    from PIL import Image

    img = Image.new("RGB", size, color)
    img.save(path, format="PNG")


def test_rebuild_thumbnail_cpu_job_returns_success_for_real_image(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    file_path = str(tmp_path / "a.png")
    _make_png(file_path)
    file_id = uuid4()

    with patch.object(thumb_mod.storage, "update_storage_root_cache"), \
         patch.object(thumb_mod.storage, "generate_thumbnail", return_value=str(tmp_path / "thumb.jpg")):
        result = thumb_mod.rebuild_thumbnail_cpu_job(
            user_id="user-1",
            file_path=file_path,
            file_id=file_id,
            storage_root=str(tmp_path),
        )

    assert result["success"] is True
    assert result["thumb_path"] == str(tmp_path / "thumb.jpg")
    # A valid PNG should yield a non-empty color_info dict.
    assert isinstance(result["color_info"], dict)
    assert result["color_info"]



def test_rebuild_thumbnail_cpu_job_returns_null_thumb_for_missing_file(tmp_path):
    """Missing files do not raise; ``generate_thumbnail`` returns None internally.

    The strategy still reports ``success=True`` because the failure is
    absorbed by the storage helper. Downstream code reads ``thumb_path``
    to decide whether the rebuild produced anything useful.
    """
    from app.service.tasks import thumbnail as thumb_mod

    missing = tmp_path / "does-not-exist.png"

    with patch.object(thumb_mod.storage, "update_storage_root_cache"), \
         patch.object(thumb_mod.storage, "generate_thumbnail", return_value=None):
        result = thumb_mod.rebuild_thumbnail_cpu_job(
            user_id="user-1",
            file_path=str(missing),
            file_id=uuid4(),
            storage_root=str(tmp_path),
        )

    assert result["success"] is True
    assert result["thumb_path"] is None
    # No color info either -- PIL couldn't open the file.
    assert result["color_info"] is None


def test_rebuild_thumbnail_cpu_job_propagates_storage_exception(tmp_path):
    """If the storage helper itself raises, the strategy surfaces a failure."""
    from app.service.tasks import thumbnail as thumb_mod

    file_path = str(tmp_path / "ok.png")
    _make_png(file_path)

    with patch.object(thumb_mod.storage, "update_storage_root_cache"), \
         patch.object(thumb_mod.storage, "generate_thumbnail", side_effect=RuntimeError("disk full")):
        result = thumb_mod.rebuild_thumbnail_cpu_job(
            user_id="user-1",
            file_path=file_path,
            file_id=uuid4(),
            storage_root=str(tmp_path),
        )

    assert result["success"] is False
    assert "disk full" in result["error"]


def test_rebuild_thumbnail_cpu_batch_job_threads_task_id_through(tmp_path):
    """The batch wrapper must echo the input task_id back to the caller."""
    from app.service.tasks import thumbnail as thumb_mod

    file_path = str(tmp_path / "b.png")
    _make_png(file_path)
    file_id = uuid4()

    tasks_data = [
        {
            "task_id": "task-A",
            "user_id": "user-1",
            "file_path": file_path,
            "file_id": file_id,
            "storage_root": str(tmp_path),
        }
    ]

    with patch.object(thumb_mod.storage, "update_storage_root_cache"), \
         patch.object(thumb_mod.storage, "generate_thumbnail", return_value=str(tmp_path / "t.jpg")):
        results = thumb_mod.rebuild_thumbnail_cpu_batch_job(tasks_data)

    assert len(results) == 1
    assert results[0]["task_id"] == "task-A"
    assert results[0]["success"] is True

