"""Unit tests for ``app/service/tasks/organize.py``.

The OrganizePhotosStrategy splits the user``s photos into per-strategy
subfolders (time / category / person / location) and either moves or copies
them. We mock the SQLAlchemy session + relationships so the strategy can
be exercised without disk, DB, or worker process.

Coverage:

* Missing payload keys -> ``ValueError`` from ``process``.
* ``strategy=time`` with ``ymd/nested`` builds ``YYYY/MM/DD`` subfolders.
* ``strategy=person`` (move action) picks the highest-confidence named
  identity and asks ``shutil.move`` to relocate the file.
* Missing files do not crash the run; the strategy advances
  ``processed_items`` but does not move or copy anything.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload):
    return SimpleNamespace(
        id="task-org",
        type="ORGANIZE_PHOTOS",
        owner_id="user-1",
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _chain(photos):
    """Build a chainable Mock so ``query.filter(...).options(...).filter(...).all()``
    returns ``photos``."""
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.all.return_value = photos
    return query


def test_process_raises_when_target_root_missing():
    """The strategy refuses to run with empty target_root_path."""
    from app.service.tasks import organize

    db = MagicMock()
    db.query.return_value = _chain([])
    task = _build_task({"strategy": "time", "action": "move"})

    with pytest.raises(ValueError, match="Missing required parameters"):
        import asyncio
        asyncio.run(organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db))


def test_process_raises_when_strategy_missing(tmp_path):
    from app.service.tasks import organize

    db = MagicMock()
    db.query.return_value = _chain([])
    task = _build_task({"target_root_path": str(tmp_path), "action": "move"})

    with pytest.raises(ValueError, match="Missing required parameters"):
        import asyncio
        asyncio.run(organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db))


def test_time_strategy_nested_builds_year_month_day(tmp_path):
    from app.service.tasks import organize

    photo = SimpleNamespace(
        file_path=str(tmp_path / "img.jpg"),
        filename="img.jpg",
        photo_time=SimpleNamespace(strftime=lambda fmt: {"%Y": "2024", "%m": "05", "%d": "07"}.get(fmt, "")),
        upload_time=None,
        is_deleted=False,
    )

    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "time",
        "action": "move",
        "time_granularity": "ymd",
        "time_format": "nested",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db))

    move.assert_called_once()
    called_src, called_dst = move.call_args[0]
    assert "2024" in called_dst and "05" in called_dst and "07" in called_dst
    # processed_items advanced to one; move succeeded so success_count == 1.
    assert task.processed_items == 1
    assert result["success_count"] == 1
    # The strategy updates the photo row in-place after a successful move.
    assert photo.file_path == called_dst


def test_person_strategy_picks_highest_confidence_identity(tmp_path):
    """Highest-confidence named face wins; ``action=move`` updates file_path."""
    from app.service.tasks import organize

    weak = MagicMock()
    weak.identity = None
    weak.confidence = 0.99

    alice = MagicMock()
    alice.identity.identity_name = "Alice"
    alice.confidence = 0.7

    bob = MagicMock()
    bob.identity.identity_name = "Bob"
    bob.confidence = 0.3

    photo = SimpleNamespace(
        file_path=str(tmp_path / "p.jpg"),
        filename="p.jpg",
        photo_time=None,
        upload_time=None,
        is_deleted=False,
        faces=[weak, alice, bob],
    )

    db = MagicMock()
    db.query.return_value = _chain([photo])

    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "person",
        "action": "move",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(organize.OrganizePhotosStrategy().process(worker=MagicMock(), task=task, db=db))

    # weak has no identity; alice (0.7) > bob (0.3) so Alice wins.
    move.assert_called_once()
    called_dst = move.call_args[0][1]
    assert "Alice" in called_dst
    assert photo.file_path == called_dst
    assert task.processed_items == 1
    assert result["success_count"] == 1


def test_process_skips_missing_files_advances_progress(tmp_path):
    """Missing file_path entries get counted but not created on disk."""
    from app.service.tasks import organize

    photo = SimpleNamespace(
        file_path=None,
        filename="missing.jpg",
        photo_time=None,
        upload_time=None,
        is_deleted=False,
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "time",
        "action": "move",
        "time_granularity": "ym",
        "time_format": "flat",
    })

    with patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(organize.OrganizePhotosStrategy().process(worker=MagicMock(), task=task, db=db))

    move.assert_not_called()
    assert task.processed_items == 1
    assert result["success_count"] == 0
    assert result["total_processed"] == 1