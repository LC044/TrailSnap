"""Unit tests for the rebuild / index-status router (app/api/index.py).

This router is the user-facing entry point to the photo search index.  Each
endpoint is small enough to test with a mocked DB session:

* ``POST /index/rebuild`` kicks off a background rebuild via ``indexer``.
* ``GET  /index/status`` reports the current ``TaskManager`` state.
* ``GET  /index/logs`` returns the most recent ``IndexLog`` rows.

These tests do not start the worker subprocess; they assert that the router
delegates to the right collaborators with the right arguments so a future
refactor cannot silently change the contract.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api import index as index_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_index]


def test_rebuild_delegates_to_indexer_with_user_id():
    """``rebuild`` must convert the user id to string before passing it down.

    The indexer expects a string for ``user_id``; the router is the boundary
    that performs the conversion so the ORM UUID never leaks into the
    service-layer call signature.
    """
    db = MagicMock()
    user = SimpleNamespace(id="user-uuid-123")

    with patch("app.api.index.indexer.rebuild_index") as rebuild:
        result = index_api.rebuild(db=db, current_user=user)

    rebuild.assert_called_once_with(db, user_id="user-uuid-123")
    assert result == {"started": True}


def test_status_reads_task_manager_snapshot():
    """``status`` must return whatever the singleton TaskManager reports.

    We patch ``TaskManager.get_instance`` to return a stub manager so the
    test does not depend on the real singleton state.
    """
    fake_manager = MagicMock()
    fake_manager.get_status.return_value = {"running": 2, "pending": 5}

    with patch(
        "app.api.index.TaskManager.get_instance", return_value=fake_manager
    ) as get_instance:
        result = index_api.status()

    get_instance.assert_called_once_with()
    fake_manager.get_status.assert_called_once_with()
    assert result == {"running": 2, "pending": 5}


def test_logs_returns_serialized_descending_rows_with_limit():
    """``logs`` must return IndexLog rows newest-first and within the limit.

    The router calls ``db.query(IndexLog).order_by(IndexLog.id.desc()).limit(...)``;
    we replace the chain with a MagicMock so we can assert the limit is
    forwarded while still returning a deterministic list of fake rows.
    """
    row_old = SimpleNamespace(
        id=10,
        action="rebuild",
        file_path="/a.jpg",
        photo_id=None,
        details={"k": "v"},
        created_at="2026-07-22T10:00:00Z",
    )
    row_new = SimpleNamespace(
        id=11,
        action="add",
        file_path="/b.jpg",
        photo_id="photo-uuid",
        details=None,
        created_at="2026-07-22T11:00:00Z",
    )

    db = MagicMock()
    query = db.query.return_value
    query.order_by.return_value.limit.return_value.all.return_value = [row_new, row_old]

    result = index_api.logs(limit=2, db=db)

    db.query.assert_called_once()
    query.order_by.assert_called_once()
    query.order_by.return_value.limit.assert_called_once_with(2)
    query.order_by.return_value.limit.return_value.all.assert_called_once_with()

    assert result[0]["id"] == 11
    assert result[0]["photo_id"] == "photo-uuid"
    assert result[1]["id"] == 10
    assert result[1]["photo_id"] is None
    # ``details`` flows through unchanged (None and dict both serialise fine).
    assert result[0]["details"] is None
    assert result[1]["details"] == {"k": "v"}


def test_logs_default_limit_is_100():
    """The ``limit`` query parameter must default to 100 to bound the response.

    This guards against an accidental removal of the default that would make
    ``GET /index/logs`` return the entire IndexLog table on a long-running
    deployment.
    """
    db = MagicMock()
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    index_api.logs(db=db)

    db.query.return_value.order_by.return_value.limit.assert_called_once_with(100)
