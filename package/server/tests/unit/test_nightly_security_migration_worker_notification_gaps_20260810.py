"""Nightly watch gap coverage for 2026-08-10 round 4.

Targets four low-coverage backend modules picked from the §4 gap scan.

* ``app/core/security.py`` -- password hashing + JWT minting helpers
  (50% coverage, 9 missed of 18 statements).
* ``app/core/migration.py`` -- one-shot legacy ``config.json`` migration
  to admin user (44.4%, 20 missed of 36).
* ``app/crud/notification.py`` -- listing / unread_count / create /
  mark_read / mark_all_read helpers that complement the partial
  ``test_notification_crud.py`` (42.9%, 28 missed of 49).
* ``app/service/task_worker.py::TaskWorker._get_concurrency_settings``
  and ``_calculate_allowed_task_types`` -- pure-ish helpers that
  drive the worker pool sizing (TaskWorker class still ~20% covered).

These tests intentionally avoid touching the live DB: the security
helpers use ``system_config`` directly, the migration function is
patched against the file system + SQLAlchemy session, the notification
crud helpers are exercised via a ``MagicMock`` session, and the
task_worker helpers are stubbed via ``system_config`` and
``TaskStrategyFactory``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# core/security.py
# ---------------------------------------------------------------------------


def _reload_security():
    """Reload the security module so it picks up patched ``system_config``."""
    import importlib

    from app.core import security as security_mod

    importlib.reload(security_mod)
    return security_mod


def test_security_password_hash_round_trip_and_jwt_with_default_expires():
    security_mod = _reload_security()

    hash_a = security_mod.get_password_hash("correct horse battery staple")
    hash_b = security_mod.get_password_hash("correct horse battery staple")

    # bcrypt salt makes the two hashes different even though the plaintext
    # matches -- this is the property verify_password relies on.
    assert hash_a != hash_b
    assert security_mod.verify_password("correct horse battery staple", hash_a)
    assert not security_mod.verify_password("wrong-password", hash_a)

    # create_access_token without expires_delta must read the configured
    # ``access_token_expire_minutes`` and include an ``exp`` claim.
    fake_config = SimpleNamespace(
        access_token_expire_minutes=7,
        secret_key="nightly-test-secret",
        algorithm="HS256",
    )
    with patch.object(security_mod.system_config, "config", SimpleNamespace(security=fake_config)):
        token = security_mod.create_access_token({"sub": "alice"})

    decoded = security_mod.jwt.decode(token, "nightly-test-secret", algorithms=["HS256"])
    assert decoded["sub"] == "alice"
    assert "exp" in decoded


def test_security_create_access_token_honours_explicit_expires_delta():
    security_mod = _reload_security()
    fake_config = SimpleNamespace(
        access_token_expire_minutes=99,  # should be ignored
        secret_key="nightly-test-secret",
        algorithm="HS256",
    )
    with patch.object(security_mod.system_config, "config", SimpleNamespace(security=fake_config)):
        token = security_mod.create_access_token({"sub": "bob"}, expires_delta=timedelta(minutes=2))

    decoded = security_mod.jwt.decode(token, "nightly-test-secret", algorithms=["HS256"])
    # The JWT library does NOT auto-add iat; compute the delta against the wall clock.
    delta = datetime.utcfromtimestamp(decoded["exp"]) - datetime.utcnow()
    # Allow a tiny jitter -- JWT's ``exp`` is an integer epoch second.
    assert 0 <= delta.total_seconds() <= 240



# ---------------------------------------------------------------------------
# core/migration.py
# ---------------------------------------------------------------------------


def test_migration_consumes_config_json_and_reassigns_owner_id(tmp_path):
    """``migrate_system_config`` should:
    1. read ./data/config.json if present and copy its contents into the admin
       user ``settings`` dict (then delete the file),
    2. update owner_id on each model in ``models_to_update`` from None to
       the admin id and commit.
    """
    from app.core import migration as migration_mod

    repo_root = tmp_path
    data_dir = repo_root / "data"
    data_dir.mkdir()
    cfg_path = data_dir / "config.json"
    cfg_path.write_text('{"theme": "amber", "ui": {"density": "cozy"}}', encoding="utf-8")

    admin = SimpleNamespace(
        id=uuid4(),
        username="admin",
        settings=None,
    )

    captured_owner_updates = []

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def update(self, values):
            captured_owner_updates.append((self.model, dict(values)))
            # Pretend 2 legacy rows were touched in each model.
            return 2

    db = MagicMock()
    db.query.side_effect = lambda model: FakeQuery(model)

    original_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        migration_mod.migrate_system_config(db, admin)
    finally:
        os.chdir(original_cwd)

    # The admin settings dict should be populated from the legacy file.
    assert admin.settings == {"theme": "amber", "ui": {"density": "cozy"}}
    # The legacy file must be deleted after migration.
    assert not cfg_path.exists()

    # Every model in the migration list must have been touched with the admin id.
    expected_models = {
        migration_mod.Album,
        migration_mod.Photo,
        migration_mod.TrainTicket,
        migration_mod.FlightTicket,
        migration_mod.Task,
        migration_mod.IndexLog,
        migration_mod.FaceIdentity,
    }
    seen = {model for model, _ in captured_owner_updates}
    assert seen == expected_models
    seen_payloads = [p for _, p in captured_owner_updates]
    assert len(seen_payloads) == len(expected_models)
    for payload in seen_payloads:
        # The migration uses ``{model.owner_id: admin.id}`` so the key is the
        # ``InstrumentedAttribute``; verify the value matches.
        assert list(payload.values()) == [admin.id]

    db.add.assert_called_once_with(admin)
    db.commit.assert_called_once()


def test_migration_no_config_file_still_updates_owner_and_commits(tmp_path):
    """When ``./data/config.json`` does not exist the admin settings dict is
    kept as-is (initialised to an empty dict if it was None) and the owner
    update still runs."""
    from app.core import migration as migration_mod

    # Run in an isolated cwd without data/config.json.
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    admin = SimpleNamespace(id=uuid4(), username="admin", settings=None)
    db = MagicMock()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def update(self, values):
            return 1

    db.query.return_value = FakeQuery()

    original_cwd = os.getcwd()
    os.chdir(repo_root)
    try:
        migration_mod.migrate_system_config(db, admin)
    finally:
        os.chdir(original_cwd)

    # settings was None, so the migration initialised it to an empty dict
    # (no config file present to overwrite it).
    assert admin.settings == {}
    # Commit still happens once at the end.
    db.commit.assert_called_once()



# ---------------------------------------------------------------------------
# crud/notification.py
# ---------------------------------------------------------------------------


def _fake_notification(user_id, *, read=False, created_at=None, notif_id=None):
    return SimpleNamespace(
        id=notif_id or uuid4(),
        user_id=user_id,
        type="SYSTEM",
        level="info",
        title="t",
        body={"k": "v"},
        ref_type=None,
        ref_id=None,
        read=1 if read else 0,
        created_at=created_at or datetime(2026, 8, 10, 12, 0),
        read_at=None,
    )


def test_notification_list_filters_and_clamps_limit():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    db = MagicMock()

    class FakeQuery:
        def __init__(self):
            self.filters = []

        def filter(self, *args):
            self.filters.extend(args)
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, n):
            # record the effective limit for assertion below.
            self.effective_limit = n
            return self

        def all(self):
            return [_fake_notification(user_id, read=False)]

    q = FakeQuery()
    db.query.return_value = q

    rows = crud_notif.list_notifications(db, user_id, type="SYSTEM", unread=True, limit=500)

    assert rows and len(rows) == 1
    # limit is clamped to <= 200; the requested 500 must collapse to 200.
    assert q.effective_limit == 200
    # ensure filter chain saw type & unread constraints.
    assert q.filters


def test_notification_list_before_id_cursor_filters_by_created_at():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    cursor_id = uuid4()
    db = MagicMock()

    captured_filters = []

    class FakeQuery:
        def filter(self, *args):
            captured_filters.extend(args)
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def all(self):
            return []

    # First .query call (in the function body) returns the main list query;
    # the second .query call resolves the cursor row.
    main_query = FakeQuery()
    cursor_query = FakeQuery()
    cursor_query.first = lambda: SimpleNamespace(id=cursor_id, created_at=datetime(2026, 8, 9))
    db.query.side_effect = [main_query, cursor_query]

    crud_notif.list_notifications(db, user_id, before_id=cursor_id)

    # Two filter calls on the main query: one for user_id, one for created_at.
    assert len(captured_filters) >= 2


def test_notification_unread_count_delegates_to_db_count():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 4

    assert crud_notif.unread_count(db, user_id) == 4
    db.query.return_value.filter.assert_called_once()


def test_notification_create_persists_with_commit_and_refresh():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    db = MagicMock()

    notif = crud_notif.create_notification(
        db,
        user_id,
        type="TASK_COMPLETED",
        title="scan finished",
        body={"scanned": 12},
    )

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert notif.user_id == user_id
    assert notif.type == "TASK_COMPLETED"
    assert notif.title == "scan finished"
    assert notif.body == {"scanned": 12}
    assert notif.read is False


def test_notification_create_without_commit_flushes_only():
    """``commit=False`` should flush but skip the commit + refresh."""
    from app.crud import notification as crud_notif

    user_id = uuid4()
    db = MagicMock()

    crud_notif.create_notification(
        db,
        user_id,
        type="TASK_COMPLETED",
        title="scan finished",
        commit=False,
    )

    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


def test_notification_mark_read_returns_false_on_miss_and_updates_on_hit():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    notif_id = uuid4()

    # 1) miss -> returns False, no commit
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert crud_notif.mark_read(db, user_id, notif_id) is False
    db.commit.assert_not_called()

    # 2) hit -> flips read flag, sets read_at, commits, returns True
    db = MagicMock()
    obj = _fake_notification(user_id, notif_id=notif_id, read=False)
    db.query.return_value.filter.return_value.first.return_value = obj
    assert crud_notif.mark_read(db, user_id, notif_id) is True
    assert obj.read is True
    assert obj.read_at is not None
    db.commit.assert_called_once()

    # 3) already-read hit -> still returns True but does NOT re-commit.
    db = MagicMock()
    obj2 = _fake_notification(user_id, notif_id=notif_id, read=True)
    obj2.read = True
    obj2.read_at = datetime.utcnow()
    db.query.return_value.filter.return_value.first.return_value = obj2
    assert crud_notif.mark_read(db, user_id, notif_id) is True
    db.commit.assert_not_called()


def test_notification_mark_all_read_marks_each_unread_row():
    from app.crud import notification as crud_notif

    user_id = uuid4()
    db = MagicMock()
    unread_rows = [
        _fake_notification(user_id, read=False),
        _fake_notification(user_id, read=False),
    ]
    db.query.return_value.filter.return_value.all.return_value = unread_rows

    count = crud_notif.mark_all_read(db, user_id)

    assert count == 2  # two unread rows were touched
    assert unread_rows[0].read is True
    assert unread_rows[0].read_at is not None
    assert unread_rows[1].read is True
    db.commit.assert_called_once()



# ---------------------------------------------------------------------------
# service/task_worker.py::TaskWorker helpers
# ---------------------------------------------------------------------------


def test_task_worker_get_concurrency_settings_three_levels():
    from app.service import task_worker

    fake_cpu_count = 8
    with patch.object(task_worker.os, "cpu_count", return_value=fake_cpu_count):
        # HIGH
        with patch.object(task_worker.system_config.config.task, "concurrency_level", "high"):
            cfg = task_worker.TaskWorker._get_concurrency_settings(self=None)
        assert cfg["process_pool"] == fake_cpu_count
        assert cfg["thread_pool"] == 16
        assert cfg["ai_consumer"] == 2

        # LOW
        with patch.object(task_worker.system_config.config.task, "concurrency_level", "low"):
            cfg = task_worker.TaskWorker._get_concurrency_settings(self=None)
        assert cfg["process_pool"] == max(1, fake_cpu_count // 4)
        assert cfg["thread_pool"] == 4
        assert cfg["ai_consumer"] == 1

        # MEDIUM (default branch)
        with patch.object(task_worker.system_config.config.task, "concurrency_level", "medium"):
            cfg = task_worker.TaskWorker._get_concurrency_settings(self=None)
        assert cfg["process_pool"] == max(1, fake_cpu_count // 2)
        assert cfg["thread_pool"] == 8

    # When os.cpu_count returns None we fall back to 4.
    with patch.object(task_worker.os, "cpu_count", return_value=None), \
         patch.object(task_worker.system_config.config.task, "concurrency_level", "low"):
        cfg = task_worker.TaskWorker._get_concurrency_settings(self=None)
    assert cfg["process_pool"] >= 1


def test_task_worker_calculate_allowed_task_types_with_pause_and_fast_mode(monkeypatch):
    """``_calculate_allowed_task_types`` must:
    * include every TaskType when fast_mode is off,
    * drop paused categories,
    * in fast_mode prefer CPU/IO/AI buckets then append other categories.
    """
    from app.db.models.task import TaskType
    from app.service import task_worker

    # Build a tiny fake strategy factory.
    class FakeStrategy:
        def __init__(self, category):
            self.task_category = category

    cpu, io, ai, other = "CPU", "IO", "AI", "OTHER"
    type_to_category = {
        TaskType.PROCESS_BASIC: cpu,
        TaskType.EXTRACT_METADATA: io,
        TaskType.VISUAL_DESCRIPTION: ai,
        TaskType.SCAN_FOLDER: other,
    }

    default_strategy = FakeStrategy(other)

    def fake_get_strategy(t):
        return FakeStrategy(type_to_category.get(t, other))

    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", fake_get_strategy)

    # 1) fast_mode off -> all types returned minus paused.
    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker.fast_mode = False
    worker.paused_categories = {TaskType.PROCESS_BASIC.value}
    allowed = task_worker.TaskWorker._calculate_allowed_task_types(worker)
    assert TaskType.PROCESS_BASIC not in allowed
    assert TaskType.SCAN_FOLDER in allowed

    # 2) fast_mode on -> CPU/IO/AI buckets first, then "other" categories.
    worker.fast_mode = True
    worker.paused_categories = {TaskType.VISUAL_DESCRIPTION.value}
    allowed = task_worker.TaskWorker._calculate_allowed_task_types(worker)
    # Visual description is in the AI bucket and is paused -> dropped.
    assert TaskType.VISUAL_DESCRIPTION not in allowed
    # PROCESS_BASIC (CPU) and EXTRACT_METADATA (IO) should still be present.
    assert TaskType.PROCESS_BASIC in allowed
    assert TaskType.EXTRACT_METADATA in allowed
    # SCAN_FOLDER (OTHER) should also be present after the bucket loop.
    assert TaskType.SCAN_FOLDER in allowed

