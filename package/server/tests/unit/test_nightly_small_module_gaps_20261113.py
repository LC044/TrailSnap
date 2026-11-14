"""Nightly watch 2026-11-13 (round 3): small-module coverage gaps.

The 2026-11-13 backend coverage snapshot (taken before the round-2 tests)
still reported uncovered lines in a handful of small, self-contained modules.
Those modules are cheap to cover and they carry real behaviour, so this file
pins the branches down:

* ``app/core/migration.py`` - a failing owner back-fill is logged, and the
  legacy ``data/config.json`` is folded into the admin user settings.
* ``app/service/gallery_sync.py`` - ``contains`` refuses empty inputs and
  unrelated drives; ``remove_gallery`` rejects an invalid path.
* ``app/db/sql.py`` - ``as_date`` normalises every backend shape.
* ``app/utils/path_validation.py`` - the filesystem limit is read from the
  nearest existing parent directory.
* ``app/service/ai_model_state.py`` - the model snapshot is cached, and a
  non-dict payload is treated as "nothing known".
* ``app/service/tasks/ai_runtime.py`` - rollback/close release the SQLite
  writer lock.
* ``app/crud/task.py`` - the small query helpers used by the task API.

Every test exercises already-implemented behaviour; no production change.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.db.models.task import Task, TaskStatus, TaskType

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/core/migration.py
# ---------------------------------------------------------------------------


def test_migrate_system_config_survives_a_failing_owner_backfill(tmp_path, monkeypatch):
    """One broken table must not abort the whole ownership migration."""
    from app.core import migration

    monkeypatch.chdir(tmp_path)
    db = MagicMock()
    db.query.return_value.filter.return_value.update.side_effect = RuntimeError("boom")
    admin = SimpleNamespace(settings=None, username="admin", id="u-1")

    migration.migrate_system_config(db, admin)

    db.commit.assert_called_once()


def test_migrate_system_config_folds_the_legacy_config_into_the_admin(tmp_path, monkeypatch):
    """``data/config.json`` becomes the admin user's settings and is removed."""
    from app.core import migration

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.json").write_text(
        json.dumps({"theme": "dark"}), encoding="utf-8"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.update.return_value = 1
    admin = SimpleNamespace(settings=None, username="admin", id="u-1")

    migration.migrate_system_config(db, admin)

    assert admin.settings == {"theme": "dark"}
    assert not (tmp_path / "data" / "config.json").exists()
    db.add.assert_called_once_with(admin)


def test_migrate_system_config_keeps_existing_admin_settings(tmp_path, monkeypatch):
    """Without a legacy config file the admin settings stay untouched."""
    from app.core import migration

    monkeypatch.chdir(tmp_path)
    db = MagicMock()
    db.query.return_value.filter.return_value.update.return_value = 0
    admin = SimpleNamespace(settings={"theme": "light"}, username="admin", id="u-1")

    migration.migrate_system_config(db, admin)

    assert admin.settings == {"theme": "light"}


# ---------------------------------------------------------------------------
# app/service/gallery_sync.py
# ---------------------------------------------------------------------------


def test_contains_refuses_an_empty_root_or_path():
    """An unset root or path can never contain anything."""
    from app.service import gallery_sync

    assert gallery_sync.contains("", "/photos/a.jpg") is False
    assert gallery_sync.contains("/photos", "") is False


def test_contains_refuses_paths_from_unrelated_drives(monkeypatch):
    """A path on another drive has no common root with the gallery."""
    from app.service import gallery_sync

    def boom(*args, **kwargs):
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(gallery_sync.os.path, "commonpath", boom)

    assert gallery_sync.contains("C:" + chr(92) + "photos",
                                 "D:" + chr(92) + "photos" + chr(92) + "a.jpg") is False


def test_remove_gallery_rejects_an_invalid_path():
    """A blank, non-string or NUL path is refused before any DB work."""
    from app.service import gallery_sync

    db = MagicMock()
    for bad in ("", "   ", None, 42, "with\x00nul"):
        with pytest.raises(ValueError, match="请提供有效的文件夹绝对路径"):
            gallery_sync.remove_gallery(db, uuid4(), bad)


# ---------------------------------------------------------------------------
# app/db/sql.py
# ---------------------------------------------------------------------------


def test_as_date_normalises_every_backend_shape():
    """SQLite returns text, PostgreSQL returns dates; both become a date."""
    from app.db.sql import as_date, as_date_string

    assert as_date(datetime(2024, 5, 6, 7, 8, 9)) == date(2024, 5, 6)
    assert as_date(date(2024, 5, 6)) == date(2024, 5, 6)
    assert as_date("2024-05-06") == date(2024, 5, 6)
    assert as_date_string(datetime(2024, 5, 6, 7, 8, 9)) == "2024-05-06"


# ---------------------------------------------------------------------------
# app/utils/path_validation.py
# ---------------------------------------------------------------------------


def test_pathconf_limit_reads_the_nearest_existing_parent(tmp_path):
    """A not-yet-created directory falls back to its closest existing parent."""
    from app.utils.path_validation import _pathconf_limit

    missing = tmp_path / "not" / "created" / "yet"
    assert _pathconf_limit(str(missing), "PC_NAME_MAX", 255) > 0
    assert _pathconf_limit(str(missing), "PC_PATH_MAX", 4096) > 0


# ---------------------------------------------------------------------------
# app/service/ai_model_state.py
# ---------------------------------------------------------------------------


def test_get_model_wait_reason_ignores_unrelated_task_types():
    """A task without a model dependency never waits."""
    from app.service import ai_model_state

    assert ai_model_state.get_model_wait_reason("http://ai", TaskType.PROCESS_BASIC) is None


def test_get_model_wait_reason_tolerates_a_non_dict_snapshot(monkeypatch):
    """A malformed catalogue is treated as "no models known"."""
    from app.service import ai_model_state

    response = MagicMock()
    response.json.return_value = ["not", "a", "dict"]
    monkeypatch.setattr(ai_model_state, "_cache", {})
    monkeypatch.setattr(ai_model_state.requests, "get", lambda *a, **k: response)

    assert ai_model_state.get_model_wait_reason("http://ai", TaskType.OCR) is None


def test_model_wait_reason_reports_a_downloading_model():
    """A model that is still downloading is reported as a wait reason."""
    from app.service import ai_model_state

    snapshot = {
        "models": [{"id": "ocr", "name": "文字识别", "status": "downloading",
                    "downloadState": "queued"}],
        "tasks": {"ocr": {"selected": "ocr"}},
    }

    reason = ai_model_state.model_wait_reason(snapshot, TaskType.OCR)

    assert reason is not None and "排队等待下载" in reason


def test_model_wait_reason_reports_a_failed_model():
    """A failed download asks the user to retry in the model manager."""
    from app.service import ai_model_state

    snapshot = {
        "models": [{"id": "ocr", "name": "文字识别", "status": "failed"}],
        "tasks": {"ocr": {"selected": "ocr"}},
    }

    reason = ai_model_state.model_wait_reason(snapshot, TaskType.OCR)

    assert reason is not None and "下载失败" in reason


def test_model_wait_reason_reports_a_running_download():
    """A model that is actively downloading is reported as running."""
    from app.service import ai_model_state

    snapshot = {
        "models": [{"id": "ocr", "name": "文字识别", "status": "downloading"}],
        "tasks": {"ocr": {"selected": "ocr"}},
    }

    reason = ai_model_state.model_wait_reason(snapshot, TaskType.OCR)

    assert reason is not None and "正在下载" in reason


def test_model_wait_reason_reports_a_model_that_is_not_installed():
    """A model that was never downloaded asks the user to install it."""
    from app.service import ai_model_state

    snapshot = {
        "models": [{"id": "ocr", "name": "文字识别", "status": "missing"}],
        "tasks": {"ocr": {"selected": "ocr"}},
    }

    reason = ai_model_state.model_wait_reason(snapshot, TaskType.OCR)

    assert reason is not None and "尚未下载" in reason


def test_get_model_wait_reason_survives_an_unreachable_ai_service(monkeypatch):
    """A failing AI service is treated as "no models known"."""
    from app.service import ai_model_state

    def boom(*args, **kwargs):
        raise ai_model_state.requests.RequestException("connection refused")

    monkeypatch.setattr(ai_model_state, "_cache", {})
    monkeypatch.setattr(ai_model_state.requests, "get", boom)

    assert ai_model_state.get_model_wait_reason("http://ai", TaskType.OCR) is None


def test_get_model_wait_reason_reuses_a_cached_snapshot(monkeypatch):
    """The second call inside the cache window does not hit the network."""
    from app.service import ai_model_state

    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        response = MagicMock()
        response.json.return_value = {"models": [], "tasks": {}}
        return response

    monkeypatch.setattr(ai_model_state, "_cache", {})
    monkeypatch.setattr(ai_model_state.requests, "get", fake_get)

    ai_model_state.get_model_wait_reason("http://ai", TaskType.OCR)
    ai_model_state.get_model_wait_reason("http://ai", TaskType.OCR)

    assert calls["n"] == 1


def test_get_model_wait_reason_drops_a_full_cache(monkeypatch):
    """A bounded cache is cleared instead of growing without limit."""
    from app.service import ai_model_state

    response = MagicMock()
    response.json.return_value = {"models": [], "tasks": {}}
    monkeypatch.setattr(ai_model_state, "_cache", {f"u{i}": (0.0, {}) for i in range(128)})
    monkeypatch.setattr(ai_model_state.requests, "get", lambda *a, **k: response)

    ai_model_state.get_model_wait_reason("http://ai", TaskType.OCR)

    assert len(ai_model_state._cache) == 1


# ---------------------------------------------------------------------------
# app/service/tasks/ai_runtime.py
# ---------------------------------------------------------------------------


def test_ai_batch_session_rollback_releases_the_sqlite_writer(face_sqlite_session):
    """A rollback must hand the writer lock back, even without a commit."""
    from app.service.tasks import ai_runtime

    db = ai_runtime.AIBatchSession(
        bind=face_sqlite_session.get_bind(), expire_on_commit=False, autoflush=False
    )
    ai_runtime._sqlite_writer.acquire()
    db._writer_owned = True
    try:
        db.rollback()
        assert db._writer_owned is False
    finally:
        db.close()


def test_ai_batch_session_close_releases_the_sqlite_writer(face_sqlite_session):
    """Closing a session must not leave the writer lock held."""
    from app.service.tasks import ai_runtime

    db = ai_runtime.AIBatchSession(
        bind=face_sqlite_session.get_bind(), expire_on_commit=False, autoflush=False
    )
    ai_runtime._sqlite_writer.acquire()
    db._writer_owned = True
    db.close()

    assert db._writer_owned is False


# ---------------------------------------------------------------------------
# app/crud/task.py
# ---------------------------------------------------------------------------


def _make_task(db, owner_id, status=TaskStatus.PENDING):
    task = Task(
        id=uuid4(),
        type=TaskType.PROCESS_BASIC.value,
        status=status.value,
        priority=1,
        owner_id=owner_id,
        payload={"file_path": "/photos/a.jpg"},
    )
    db.add(task)
    db.commit()
    return task


def test_task_queries_filter_by_status_and_owner(face_sqlite_session):
    """The task API helpers only return the rows they were asked for."""
    from app.crud import task as crud_task

    db = face_sqlite_session
    owner = uuid4()
    other = uuid4()
    pending = _make_task(db, owner)
    _make_task(db, owner, status=TaskStatus.COMPLETED)
    _make_task(db, other)

    assert crud_task.count_tasks_by_status(db, TaskStatus.PENDING.value) == 2
    assert len(crud_task.get_tasks_by_status(db, TaskStatus.PENDING.value)) == 2
    assert crud_task.get_task_by_id_and_owner(db, pending.id, owner).id == pending.id
    assert crud_task.get_task_by_id_and_owner(db, pending.id, other) is None


def test_delete_task_removes_the_row(face_sqlite_session):
    """Deleting a task commits the removal."""
    from app.crud import task as crud_task

    db = face_sqlite_session
    task = _make_task(db, uuid4())

    crud_task.delete_task(db, task)

    assert db.query(Task).filter(Task.id == task.id).first() is None
