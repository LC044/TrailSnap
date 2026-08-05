"""Unit tests for ``app/service/tasks/album.py``.

The ``ScanAlbumStrategy`` keeps smart/conditional albums in sync with the
underlying photo rows: every task scans the matching photos, computes the
diff against existing ``AlbumPhoto`` rows, and updates the cover + count.
We mock the SQLAlchemy session and the ``crud_album`` helpers so the
diff / cover logic can be exercised without a real database.

Coverage:

* Album not found -> short-circuit ``skipped``.
* Manual (user-created) album -> skipped; never touches ``AlbumPhoto``.
* Happy path (smart album) adds new rows and removes stale ones, commits
  twice (once for ``AlbumPhoto`` diff, once for the album row), and
  returns ``status=success``.
* Empty match -> existing rows are removed and ``album.cover_id`` is
  reset to ``None``.
* Missing cover -> strategy picks the earliest photo (by ``photo_time``
  with ``upload_time`` fallback) as the new cover.
* Existing cover photo still in match set -> kept as cover; only stale
  or missing covers get replaced.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _build_task(album_id=None):
    return SimpleNamespace(
        id="task-scan-album",
        type="SCAN_ALBUM",
        owner_id="user-1",
        payload={"album_id": album_id or uuid.uuid4().hex},
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_album(album_id=None, album_type="smart", cover_id=None):
    return SimpleNamespace(
        id=album_id or uuid.uuid4().hex,
        type=album_type,
        condition={},
        cover_id=cover_id,
        num_photos=0,
        owner_id="user-1",
    )


def _make_photo(pid, photo_time=None, upload_time=None):
    return SimpleNamespace(
        id=pid,
        photo_time=photo_time,
        upload_time=upload_time,
    )


def _existing_relations(pairs, album_id=None):
    """Build ``AlbumPhoto``-like objects: ``album_id`` + ``photo_id``."""
    aid = album_id or uuid.uuid4().hex
    return [SimpleNamespace(album_id=aid, photo_id=pid) for pid in pairs]


def _chain_existing_relations(relations):
    """Build a chainable mock so ``db.query(AlbumPhoto).filter(...).all()``
    returns ``relations`` regardless of the chain depth."""
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = relations
    query.delete.return_value = len(relations)
    return query


def test_album_not_found_is_skipped():
    """When the album row vanished (deleted before the scan ran) we must
    not raise; we report ``album not found`` instead."""
    from app.service.tasks import album as album_mod

    task = _build_task()

    with patch.object(album_mod.crud_album, "get_album", return_value=None) as get_album:
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=MagicMock())
        )

    assert result == {"status": "skipped", "reason": "album not found"}
    get_album.assert_called_once()


def test_manual_album_is_skipped():
    """User-curated albums (``type=user``) are managed by hand; the scan
    must skip them entirely without touching ``AlbumPhoto``."""
    from app.service.tasks import album as album_mod

    task = _build_task()
    manual = _make_album(album_type="user")

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch.object(album_mod.crud_album, "get_album", return_value=manual):
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=db)
        )

    assert result == {"status": "skipped", "reason": "manual album"}
    # We must never add/delete AlbumPhoto rows for a manual album.
    db.add_all.assert_not_called()
    db.commit.assert_not_called()


def test_happy_path_adds_new_rows_and_removes_stale():
    """A smart album whose match set gained one and lost one row must
    add the new ``AlbumPhoto`` row, drop the stale one, and pick a cover
    from the earliest matching photo."""
    from app.service.tasks import album as album_mod

    album = _make_album(album_type="smart", cover_id=None)
    task = _build_task(album_id=album.id)
    db = MagicMock()
    db.query.return_value = _chain_existing_relations(
        _existing_relations(["p-stale", "p-keep-1"], album_id=album.id)
    )

    new_p = _make_photo("p-new-1", photo_time="2025-08-05T10:00:00")
    keep_p = _make_photo("p-keep-1", photo_time="2025-08-04T10:00:00")

    matching_query = MagicMock()
    matching_query.all.return_value = [new_p, keep_p]

    with patch.object(album_mod.crud_album, "get_album", return_value=album), \
         patch.object(album_mod.crud_album, "_build_album_query", return_value=matching_query):
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=db)
        )

    assert result["status"] == "success"
    assert result["added"] == 1
    assert result["removed"] == 1
    # Cover falls back to the earliest match; keep_p has the earliest photo_time.
    assert album.cover_id == keep_p.id
    assert album.num_photos == 2
    add_args = db.add_all.call_args[0][0]
    added_ids = {a.photo_id for a in add_args}
    assert added_ids == {"p-new-1"}
    db.commit.assert_called()


def test_empty_match_clears_cover_and_removes_existing():
    """When no photo matches anymore we drop the cover and all existing
    rows; ``album.cover_id`` must be ``None`` so the UI doesn't render a
    dangling thumbnail."""
    from app.service.tasks import album as album_mod

    album = _make_album(album_type="smart", cover_id="old-cover")
    task = _build_task(album_id=album.id)
    db = MagicMock()
    db.query.return_value = _chain_existing_relations(
        _existing_relations(["p1", "p2"], album_id=album.id)
    )

    matching_query = MagicMock()
    matching_query.all.return_value = []

    with patch.object(album_mod.crud_album, "get_album", return_value=album), \
         patch.object(album_mod.crud_album, "_build_album_query", return_value=matching_query):
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=db)
        )

    assert result["status"] == "success"
    assert result["added"] == 0
    assert result["removed"] == 2
    assert album.cover_id is None
    assert album.num_photos == 0
    db.refresh.assert_called_once_with(album)


def test_existing_cover_among_matches_is_preserved():
    """If ``album.cover_id`` still references a matching photo we leave
    it alone; only stale or missing covers get replaced."""
    from app.service.tasks import album as album_mod

    keep = _make_photo("p-keep", photo_time="2025-08-04T10:00:00")
    new = _make_photo("p-new", photo_time="2025-08-05T10:00:00")
    album = _make_album(album_type="smart", cover_id="p-keep")
    task = _build_task(album_id=album.id)
    db = MagicMock()
    db.query.return_value = _chain_existing_relations(
        _existing_relations(["p-keep"], album_id=album.id)
    )

    matching_query = MagicMock()
    matching_query.all.return_value = [new, keep]

    with patch.object(album_mod.crud_album, "get_album", return_value=album), \
         patch.object(album_mod.crud_album, "_build_album_query", return_value=matching_query):
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=db)
        )

    assert result["added"] == 1
    assert result["removed"] == 0
    # Cover stays at p-keep (it is still in the match set).
    assert album.cover_id == "p-keep"


def test_cover_falls_back_to_upload_time_when_photo_time_missing():
    """Earliest selection uses ``photo_time`` first, falling back to
    ``upload_time`` for photos whose ``photo_time`` is ``None``."""
    from app.service.tasks import album as album_mod

    no_time = _make_photo("p-no-time", photo_time=None, upload_time="2025-01-01T00:00:00")
    later = _make_photo("p-later", photo_time="2025-08-05T10:00:00")
    album = _make_album(album_type="smart", cover_id=None)
    task = _build_task(album_id=album.id)
    db = MagicMock()
    db.query.return_value = _chain_existing_relations(
        _existing_relations([], album_id=album.id)
    )

    matching_query = MagicMock()
    matching_query.all.return_value = [later, no_time]

    with patch.object(album_mod.crud_album, "get_album", return_value=album), \
         patch.object(album_mod.crud_album, "_build_album_query", return_value=matching_query):
        result = asyncio.run(
            album_mod.ScanAlbumStrategy().process(worker=MagicMock(), task=task, db=db)
        )

    assert result["added"] == 2
    # The ``min`` key prefers photo_time; ``no_time`` falls back to
    # upload_time which is earlier than ``later``'s photo_time.
    assert album.cover_id == "p-no-time"