"""Nightly coverage for ``app/service/tasks/duplicate.py`` (2026-10-26).

The 2026-10-26 backend coverage scan listed ``service/tasks/duplicate.py`` at
84.7% with 11 missed lines.  The missed lines sat in the arguments of the
duplicate photo task:

* the one hour ``timeout`` of the strategy
* the parsing of the optional ``photo_ids`` payload: unparsable ids are
  skipped and a payload without a single valid id must not scan anything
* the re-raise of a failed scan

The strategy is driven with a stub session, so no database is needed.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke]


def _strategy():
    from app.service.tasks.duplicate import FindDuplicatePhotosStrategy

    return FindDuplicatePhotosStrategy()


def _task(payload=None):
    return SimpleNamespace(
        owner_id=uuid.uuid4(),
        payload=payload or {},
        total_items=0,
        processed_items=0,
        status=None,
        result=None,
    )


def _session(photos=()):
    """A stub session whose ``query(Photo).filter(...)`` returns ``photos``."""
    db = MagicMock()
    query = db.query.return_value.filter.return_value
    query.all.return_value = list(photos)
    query.filter.return_value = query
    return db, query


def _photo(file_path=""):
    return SimpleNamespace(file_path=file_path, md5=None)


# ---------------------------------------------------------------------------
# timeout
# ---------------------------------------------------------------------------


def test_the_duplicate_scan_uses_a_one_hour_timeout():
    assert _strategy().timeout == 60 * 60


# ---------------------------------------------------------------------------
# photo_ids payload
# ---------------------------------------------------------------------------


def test_unparsable_photo_ids_are_skipped():
    db, query = _session()
    valid = uuid.uuid4()
    task = _task({"photo_ids": ["not-a-uuid", str(valid), 42]})

    asyncio.run(_strategy().process(worker=None, task=task, db=db))

    # The strategy filtered on a real id list instead of the empty filter.
    assert query.filter.call_args[0][0] is not False


def test_a_payload_without_a_single_valid_id_scans_nothing():
    db, query = _session()
    task = _task({"photo_ids": ["not-a-uuid", "also-not-a-uuid"]})

    result = asyncio.run(_strategy().process(worker=None, task=task, db=db))

    assert query.filter.call_args[0][0] is False
    assert result == {"status": "completed", "count": 0}
    assert task.status.name == "COMPLETED"


def test_a_scan_without_photos_completes_immediately():
    db, _query = _session()
    task = _task()

    result = asyncio.run(_strategy().process(worker=None, task=task, db=db))

    assert result == {"status": "completed", "count": 0}
    assert task.result == {"message": "No photos need MD5 calculation"}


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------


def test_a_scan_stores_the_computed_hashes(monkeypatch, tmp_path):
    from app.service.tasks import duplicate as duplicate_module

    image = tmp_path / "photo.jpg"
    image.write_bytes(b"content")

    async def fake_md5(path):
        return "d41d8cd98f00b204e9800998ecf8427e" if path == str(image) else ""

    monkeypatch.setattr(duplicate_module, "calculate_file_md5_async", fake_md5)

    db, _query = _session(photos=[_photo(str(image)), _photo("")])
    task = _task()

    result = asyncio.run(_strategy().process(worker=None, task=task, db=db))

    assert result == {"status": "completed", "updated_count": 1}
    assert task.processed_items == 2


# ---------------------------------------------------------------------------
# failures
# ---------------------------------------------------------------------------


def test_a_failed_scan_is_reraised():
    db = MagicMock()
    db.query.side_effect = RuntimeError("database is gone")
    task = _task()

    with pytest.raises(RuntimeError, match="database is gone"):
        asyncio.run(_strategy().process(worker=None, task=task, db=db))
