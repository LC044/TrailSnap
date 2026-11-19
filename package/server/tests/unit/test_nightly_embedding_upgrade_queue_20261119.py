"""2026-11-19 nightly coverage for ``app/db/embedding_upgrade.py``.

No test file referenced ``app/db/embedding_upgrade.py``.  The module holds the
frozen queue payload shared by the two Chinese-CLIP embedding migrations, so
its guard rails matter: the rebuild task must never be queued for an empty
library, must never be queued twice, and the downgrade step must only remove a
task that is still pending.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db import embedding_upgrade


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


class _Result:
    """Stand-in for the result of ``connection.execute(...)``."""

    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row


class _FakeConnection:
    """Minimal DBAPI-ish connection that records every executed statement."""

    def __init__(self, dialect="sqlite", vector_rows=(), task_rows=()):
        self.dialect = SimpleNamespace(name=dialect)
        self.executed = []
        self._vector_rows = list(vector_rows)
        self._task_rows = list(task_rows)

    def execute(self, statement, *args, **kwargs):
        self.executed.append(statement)
        text = str(statement).lower()
        if "image_vectors" in text and "select" in text:
            return _Result(self._vector_rows[0] if self._vector_rows else None)
        if "tasks" in text and "select" in text:
            return _Result(self._task_rows[0] if self._task_rows else None)
        return _Result()


def _insert_statements(connection):
    return [s for s in connection.executed if str(s).lower().startswith("insert")]


def _delete_statements(connection):
    return [s for s in connection.executed if str(s).lower().startswith("delete")]


def test_no_rebuild_task_is_queued_for_an_empty_library():
    connection = _FakeConnection(vector_rows=())

    embedding_upgrade.queue_chinese_clip_rebuild(connection)

    assert _insert_statements(connection) == []


def test_a_rebuild_task_is_queued_once_with_the_frozen_payload():
    connection = _FakeConnection(vector_rows=[("photo-1",)])

    embedding_upgrade.queue_chinese_clip_rebuild(connection)

    inserts = _insert_statements(connection)
    assert len(inserts) == 1

    values = inserts[0].compile().params
    assert values["id"] == embedding_upgrade.TASK_ID
    assert values["type"] == "IMAGE_EMBEDDING"
    assert values["status"] == "pending"
    assert values["priority"] == 8
    assert values["payload"] == {
        "force": True,
        "model": "chinese-clip-ViT-B-16",
        "source": "chinese_clip_upgrade_v1",
    }
    assert values["attempt_count"] == 0
    assert values["total_items"] == 0
    assert values["processed_items"] == 0


def test_the_rebuild_task_is_not_queued_twice():
    connection = _FakeConnection(vector_rows=[("photo-1",)], task_rows=[(embedding_upgrade.TASK_ID,)])

    embedding_upgrade.queue_chinese_clip_rebuild(connection)

    assert _insert_statements(connection) == []


def test_the_task_id_is_a_frozen_uuid():
    assert embedding_upgrade.TASK_ID == "205c1a0b-0001-4000-8000-000000000001"


def test_downgrade_only_removes_a_pending_task():
    connection = _FakeConnection()

    embedding_upgrade.remove_chinese_clip_rebuild(connection)

    deletes = _delete_statements(connection)
    assert len(deletes) == 1

    params = deletes[0].compile().params
    assert params["id_1"] == embedding_upgrade.TASK_ID
    assert params["status_1"] == "pending"


def test_the_postgres_dialect_uses_a_uuid_id_column():
    postgres = _FakeConnection(dialect="postgresql", vector_rows=[("photo-1",)])
    sqlite = _FakeConnection(dialect="sqlite", vector_rows=[("photo-1",)])

    embedding_upgrade.queue_chinese_clip_rebuild(postgres)
    embedding_upgrade.queue_chinese_clip_rebuild(sqlite)

    postgres_insert = _insert_statements(postgres)[0]
    sqlite_insert = _insert_statements(sqlite)[0]

    assert type(postgres_insert.table.c.id.type).__name__ == "UUID"
    assert type(sqlite_insert.table.c.id.type).__name__ == "String"
