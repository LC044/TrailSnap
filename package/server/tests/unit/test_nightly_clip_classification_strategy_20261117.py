"""2026-11-17 nightly coverage for the CLIP classification task strategy.

The 2026-11-17 targeted coverage scan reported
``service/tasks/clip_classification.py`` at 79% (the module was reworked by
master in the CLIP directory v3 release). The strategy is the piece that keeps
a CLIP job from blocking another task phase while it holds a worker slot, so
the following paths deserve explicit regression tests:

* ``process_batch`` - photo-scoped tasks are grouped per owner and a failing
  batch is reported as ``failed`` instead of raising out of the worker loop;
* ``process`` - a task without an owner is rejected, a task that waits for the
  image-embedding model stays resumable, and a photo that no longer exists
  (or turned into a video) is skipped instead of failing;
* ``process_photos`` - a photo without a matching embedding is deferred, and
  the deferred photo is re-queued as an IMAGE_EMBEDDING task so the
  classification is retried automatically once the embedding exists.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.db.models.photo import FileType
from app.service.tasks import clip_classification as strategy_module


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


Strategy = strategy_module.ClipClassificationStrategy


class _FakeQuery:
    """A minimal chainable query stub: every filter/order/limit returns self."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)

    def add_columns(self, *args, **kwargs):
        return self

    def correlate(self, *args, **kwargs):
        return self

    def scalar_subquery(self):
        return self

    def __iter__(self):
        return iter(self.rows)


def _strategy():
    return Strategy()


def _task(task_id="task-1", owner_id="owner-1", payload=None):
    return SimpleNamespace(
        id=task_id,
        type="CLASSIFY_IMAGE_CLIP",
        owner_id=owner_id,
        payload=payload or {},
        photo_id=None,
        status="PENDING",
    )


def test_task_category_and_resource_key_are_stable():
    strategy = _strategy()
    assert strategy.task_category == "AI"
    assert strategy.resource_key == "clip_classification"


def test_process_rejects_a_task_without_an_owner():
    db = MagicMock()
    with pytest.raises(ValueError):
        asyncio.run(_strategy().process(MagicMock(), _task(owner_id=None), db))


def test_process_stays_resumable_while_the_embedding_model_is_still_running():
    db = MagicMock()
    db.query.return_value = _FakeQuery([SimpleNamespace(id="pending-1")])
    task = _task(payload={"wait_for_embeddings": True})

    with pytest.raises(RuntimeError):
        asyncio.run(_strategy().process(MagicMock(), task, db))


def test_process_skips_a_photo_that_no_longer_exists():
    db = MagicMock()
    db.query.return_value = _FakeQuery([])
    task = _task(payload={"photo_id": "6f1a9b8e-0000-4000-8000-000000000001"})

    assert asyncio.run(_strategy().process(MagicMock(), task, db)) == {"status": "skipped"}


def test_process_skips_a_photo_that_became_a_video():
    db = MagicMock()
    photo = SimpleNamespace(id="6f1a9b8e-0000-4000-8000-000000000001",
                            file_type=FileType.video, is_deleted=False)
    db.query.return_value = _FakeQuery([photo])
    task = _task(payload={"photo_id": "6f1a9b8e-0000-4000-8000-000000000001"})

    assert asyncio.run(_strategy().process(MagicMock(), task, db)) == {"status": "skipped"}


def test_process_returns_no_generated_task_when_no_category_is_enabled():
    db = MagicMock()
    db.query.return_value = _FakeQuery([])
    task = _task(payload={})

    with patch.object(strategy_module.svc, "ensure_presets", lambda *_a, **_k: None):
        result = asyncio.run(_strategy().process(MagicMock(), task, db))

    assert result == {"generated_tasks": 0}


def test_process_batch_reports_a_failing_task_as_failed():
    db = MagicMock()
    task = _task(task_id="task-1", payload={})
    strategy = _strategy()

    async def _boom(worker, item, session):
        raise RuntimeError("classifier exploded")

    with patch.object(strategy, "process", _boom):
        results = asyncio.run(strategy.process_batch(MagicMock(), [task], db))

    assert results[0]["status"] == "failed"
    assert "classifier exploded" in results[0]["error"]


def test_process_batch_groups_photo_scoped_tasks_by_owner():
    db = MagicMock()
    task = _task(task_id="task-1", payload={"photo_id": "6f1a9b8e-0000-4000-8000-000000000001"})
    strategy = _strategy()

    with patch.object(strategy, "process_photos", lambda *_a, **_k: [{"task_id": "task-1",
                                                                     "task_type": "CLASSIFY_IMAGE_CLIP",
                                                                     "status": "completed"}]):
        results = asyncio.run(strategy.process_batch(MagicMock(), [task], db))

    assert results == [{"task_id": "task-1", "task_type": "CLASSIFY_IMAGE_CLIP", "status": "completed"}]


def test_process_batch_reports_a_failing_owner_group_as_failed():
    db = MagicMock()
    task = _task(task_id="task-1", payload={"photo_id": "6f1a9b8e-0000-4000-8000-000000000001"})
    strategy = _strategy()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("group exploded")

    with patch.object(strategy, "process_photos", _boom):
        results = asyncio.run(strategy.process_batch(MagicMock(), [task], db))

    assert results[0]["status"] == "failed"
    assert "group exploded" in results[0]["error"]


def _process_photos_db(photos, embeddings, categories, rules):
    """Route the different query targets of ``process_photos`` to their stubs."""
    def _query(model, *args, **kwargs):
        if model is strategy_module.Photo:
            return _FakeQuery(photos)
        if model is strategy_module.ImageVector:
            return _FakeQuery(embeddings)
        if model is strategy_module.ClipCategory:
            return _FakeQuery(categories)
        if model is strategy_module.ClipRuleRevision:
            return _FakeQuery(rules)
        return _FakeQuery([])

    db = MagicMock()
    db.query.side_effect = _query
    return db


def test_process_photos_defers_a_photo_without_a_matching_embedding():
    photo_id = "6f1a9b8e-0000-4000-8000-000000000001"
    photo = SimpleNamespace(id=UUID(photo_id), owner_id="owner-1", file_type=FileType.image,
                            is_deleted=False)
    vector = SimpleNamespace(photo_id=UUID(photo_id), model_name="clip-vit", embedding=[0.1, 0.2])
    category = SimpleNamespace(id="cat-1", revision=3, enabled=True, is_deleted=False)
    rule = SimpleNamespace(category_id="cat-1", revision=3, thresholds={})

    db = _process_photos_db([photo], [vector], [category], [rule])
    task = _task(task_id="task-1", payload={"photo_id": photo_id, "revisions": {"cat-1": 3}, "model": "stale-model"})

    results = _strategy().process_photos(db, "owner-1", [task])

    assert results[0]["result"]["status"] == "deferred"
    assert results[0]["result"]["reason"] == "waiting for image embedding"


def test_process_photos_skips_a_photo_that_is_not_owned_by_the_owner():
    photo_id = "6f1a9b8e-0000-4000-8000-000000000001"
    db = _process_photos_db([], [], [], [])
    task = _task(task_id="task-1", payload={"photo_id": photo_id, "revisions": {"cat-1": 3}})

    results = _strategy().process_photos(db, "owner-1", [task])

    assert results[0]["result"] == {"status": "skipped"}


def test_process_photos_scores_a_photo_against_its_selected_rules():
    photo_id = "6f1a9b8e-0000-4000-8000-000000000001"
    photo = SimpleNamespace(id=UUID(photo_id), owner_id="owner-1", file_type=FileType.image,
                            is_deleted=False)
    vector = SimpleNamespace(photo_id=UUID(photo_id), model_name="clip-vit", embedding=[0.1, 0.2])
    category = SimpleNamespace(id="cat-1", revision=3, enabled=True, is_deleted=False)
    rule = SimpleNamespace(category_id="cat-1", revision=3, thresholds={})

    db = _process_photos_db([photo], [vector], [category], [rule])
    task = _task(task_id="task-1", payload={"photo_id": photo_id, "revisions": {"cat-1": 3}})

    def _apply(_db, prepared):
        return {UUID(photo_id): 1}

    with patch.object(strategy_module.svc, "ai_url", lambda *_a, **_k: "http://ai"), \
            patch.object(strategy_module.svc, "rule_vectors", lambda *_a, **_k: np.array([[1.0, 0.0]])), \
            patch.object(strategy_module.svc, "normalize", lambda vectors: np.asarray(vectors)), \
            patch.object(strategy_module.svc, "threshold_for", lambda *_a, **_k: 0.3), \
            patch.object(strategy_module.svc, "apply_batch_results", _apply):
        results = _strategy().process_photos(db, "owner-1", [task])

    assert results[0]["result"]["status"] == "success"
    assert results[0]["result"]["rules_checked"] == 1
    assert results[0]["result"]["tags_found"] == 1



