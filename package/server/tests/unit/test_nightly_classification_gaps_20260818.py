"""Unit tests for 2026-08-18 nightly coverage gap scan.

Module exercised: ``app/service/tasks/classification.py``.

Coverage before this file: 53.8% (85 missed lines out of 184).
The missed lines cluster around the generator-mode pagination loop, the
process_batch dispatcher, the AI result post-processor, and the
``get_tag_id`` cache helper.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _strategy():
    from app.service.tasks.classification import ClassifyImageStrategy
    return ClassifyImageStrategy()


def _task(payload=None, owner_id=None, task_id=None, task_type="CLASSIFY_IMAGE"):
    return SimpleNamespace(
        id=task_id or uuid4(),
        type=task_type,
        owner_id=owner_id or uuid4(),
        payload=payload or {},
    )


# === get_tag_id ===

def test_get_tag_id_uses_cached_value_without_db(monkeypatch):
    from app.service.tasks import classification as cls_mod

    cls_mod._tag_cache.clear()
    # Seed the cache so we never even ask crud_tag.
    cls_mod._tag_cache["cached"] = "cached-id"

    db = MagicMock()
    assert cls_mod.get_tag_id(db, "cached", uuid4()) == "cached-id"
    db.assert_not_called()


def test_get_tag_id_fetches_existing_tag_then_caches(monkeypatch):
    from app.service.tasks import classification as cls_mod
    from app.db.models.tag import PhotoTag

    cls_mod._tag_cache.clear()

    existing = SimpleNamespace(id=uuid4())
    with patch.object(cls_mod.crud_tag, "get_tag_by_name", return_value=existing) as get_by_name:
        db = MagicMock()
        first = cls_mod.get_tag_id(db, "sky", uuid4())
        # Second call should hit the cache, never invoke crud_tag again.
        second = cls_mod.get_tag_id(db, "sky", uuid4())

    assert first == str(existing.id)
    assert second == first
    assert get_by_name.call_count == 1
    assert cls_mod._tag_cache["sky"] == first
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_get_tag_id_creates_tag_when_missing(monkeypatch):
    from app.service.tasks import classification as cls_mod
    from app.db.models.tag import PhotoTag

    cls_mod._tag_cache.clear()
    owner_id = uuid4()
    new_id = uuid4()

    def fake_get_tag_by_name(db, name, owner):
        return None

    def fake_refresh(tag):
        tag.id = new_id

    with patch.object(cls_mod.crud_tag, "get_tag_by_name", side_effect=fake_get_tag_by_name):
        with patch.object(cls_mod, "PhotoTag", PhotoTag):
            db = MagicMock()
            db.refresh.side_effect = fake_refresh
            tag_id = cls_mod.get_tag_id(db, "beach", owner_id)

    assert tag_id == str(new_id)
    assert cls_mod._tag_cache["beach"] == str(new_id)
    db.add.assert_called_once()
    db.commit.assert_called_once()


# === ClassifyImageStrategy.process (generator mode) ===

def test_process_generator_mode_generates_one_task_per_photo():
    strategy = _strategy()
    photos = [
        SimpleNamespace(
            id=uuid4(),
            owner_id=uuid4(),
            file_path=f"/p/{i}.jpg",
            processed_tasks={"classification": False} if i % 2 == 0 else {"classification": True},
        )
        for i in range(3)
    ]
    db = MagicMock()
    db.query.return_value.offset.return_value.limit.return_value.all.side_effect = [
        photos,
        [],
    ]

    worker = MagicMock()
    task = _task(payload={"force": False})

    out = _run(strategy.process(worker, task, db))

    assert out["processed"] == 0
    # Only the two photos without the classification flag should be scheduled.
    assert out["generated_tasks"] == 2
    worker.add_tasks.assert_called_once()
    scheduled = worker.add_tasks.call_args[0][1]
    assert len(scheduled) == 2
    for entry in scheduled:
        assert entry["type"] == "CLASSIFY_IMAGE"
        assert entry["payload"]["force"] is False
        assert entry["priority"] >= 0


def test_process_generator_mode_force_reschedules_all_photos():
    strategy = _strategy()
    photos = [
        SimpleNamespace(
            id=uuid4(),
            owner_id=uuid4(),
            file_path=f"/p/{i}.jpg",
            processed_tasks={"classification": True},
        )
        for i in range(2)
    ]
    db = MagicMock()
    db.query.return_value.offset.return_value.limit.return_value.all.side_effect = [photos, []]
    worker = MagicMock()
    task = _task(payload={"force": True})

    out = _run(strategy.process(worker, task, db))

    assert out["generated_tasks"] == 2


def test_process_generator_mode_handles_missing_processed_tasks_dict():
    strategy = _strategy()
    photo = SimpleNamespace(
        id=uuid4(), owner_id=uuid4(), file_path="/p/x.jpg", processed_tasks=None,
    )
    db = MagicMock()
    db.query.return_value.offset.return_value.limit.return_value.all.side_effect = [[photo], []]
    worker = MagicMock()
    task = _task(payload={"force": False})

    out = _run(strategy.process(worker, task, db))

    assert out["generated_tasks"] == 1


def test_process_generator_mode_propagates_exceptions():
    strategy = _strategy()
    db = MagicMock()
    db.query.side_effect = RuntimeError("db unavailable")
    worker = MagicMock()
    task = _task(payload={"force": False})

    with pytest.raises(RuntimeError, match="db unavailable"):
        _run(strategy.process(worker, task, db))


# === ClassifyImageStrategy.process_batch ===

def test_process_batch_routes_generator_and_photo_tasks_separately():
    strategy = _strategy()
    owner_id = uuid4()
    generator_task = _task(payload={}, owner_id=owner_id)
    photo_task = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_id)

    async def fake_process(worker, t, db):
        return {"status": "noop"}

    async def fake_process_generator(worker, tasks, db):
        return [{"task_id": t.id, "task_type": t.type, "status": "completed", "result": {"status": "noop"}} for t in tasks]

    async def fake_process_owner(owner, tasks, db):
        return [{"task_id": t.id, "task_type": t.type, "status": "completed", "result": {"status": "skipped"}} for t in tasks]

    with patch.object(strategy, "process", side_effect=fake_process), \
         patch.object(strategy, "_process_generator_tasks", side_effect=fake_process_generator), \
         patch.object(strategy, "_process_owner_batch", side_effect=fake_process_owner):
        results = _run(strategy.process_batch(MagicMock(), [generator_task, photo_task], MagicMock()))

    assert len(results) == 2


def test_process_batch_only_generator_tasks_returns_only_generator_results():
    strategy = _strategy()
    generator_task = _task(payload={})
    generator_results = [{"task_id": generator_task.id, "task_type": generator_task.type, "status": "completed", "result": {"status": "noop"}}]

    async def fake_process_generator(worker, tasks, db):
        return generator_results

    with patch.object(strategy, "_process_generator_tasks", side_effect=fake_process_generator):
        results = _run(strategy.process_batch(MagicMock(), [generator_task], MagicMock()))

    assert results == generator_results


def test_process_batch_only_photo_tasks_returns_only_photo_results():
    strategy = _strategy()
    photo_task = _task(payload={"photo_id": str(uuid4())})
    photo_results = [{"task_id": photo_task.id, "task_type": photo_task.type, "status": "completed", "result": {"status": "skipped"}}]

    async def fake_process_owner(owner, tasks, db):
        return photo_results

    with patch.object(strategy, "_process_owner_batch", side_effect=fake_process_owner):
        results = _run(strategy.process_batch(MagicMock(), [photo_task], MagicMock()))

    assert results == photo_results


def test_process_batch_groups_photo_tasks_by_owner():
    strategy = _strategy()
    owner_a = uuid4()
    owner_b = uuid4()
    task_a = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_a)
    task_b = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_b)
    task_a2 = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_a)

    seen = []

    async def fake_process_owner(owner, tasks, db):
        seen.append((owner, [t.id for t in tasks]))
        return []

    with patch.object(strategy, "_process_owner_batch", side_effect=fake_process_owner):
        _run(strategy.process_batch(MagicMock(), [task_a, task_b, task_a2], MagicMock()))

    assert sorted([call[0] for call in seen]) == sorted([owner_a, owner_b])
    for owner, ids in seen:
        if owner == owner_a:
            assert sorted(ids) == sorted([task_a.id, task_a2.id])
        else:
            assert ids == [task_b.id]


# === ClassifyImageStrategy._process_generator_tasks ===

def test_process_generator_tasks_marks_failures_for_exception():
    strategy = _strategy()
    bad_task = _task(task_id=uuid4(), task_type="CLASSIFY_IMAGE")

    async def fake_process(worker, t, db):
        raise RuntimeError("boom")

    strategy.process = fake_process
    results = _run(strategy._process_generator_tasks(MagicMock(), [bad_task], MagicMock()))

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "boom" in results[0]["error"]


def test_process_generator_tasks_marks_failed_status_when_result_says_so():
    strategy = _strategy()
    generator_task = _task(task_id=uuid4(), task_type="CLASSIFY_IMAGE")

    async def fake_process(worker, t, db):
        return {"status": "failed", "error": "downstream"}

    strategy.process = fake_process
    results = _run(strategy._process_generator_tasks(MagicMock(), [generator_task], MagicMock()))

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "downstream"


def test_process_generator_tasks_marks_completed_for_success_result():
    strategy = _strategy()
    generator_task = _task(task_id=uuid4(), task_type="CLASSIFY_IMAGE")

    async def fake_process(worker, t, db):
        return {"status": "ok"}

    strategy.process = fake_process
    results = _run(strategy._process_generator_tasks(MagicMock(), [generator_task], MagicMock()))

    assert results[0]["status"] == "completed"
    assert results[0]["result"] == {"status": "ok"}


# === ClassifyImageStrategy._process_ai_results ===

def test_process_ai_results_picks_first_label_above_threshold_and_records_tag(monkeypatch):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=uuid4(),
        file_path="/p/x.jpg",
        processed_tasks=None,
    )
    task = _task(payload={"photo_id": str(photo_id)})

    ai_results = [{
        "status": "success",
        "predictions": [{"label": "beach", "confidence": 0.9}, {"label": "sky", "confidence": 0.6}],
    }]

    monkeypatch.setattr(cls_mod, "get_tag_id", lambda db, name, owner: "tag-id")

    db = MagicMock()
    results = _run(strategy._process_ai_results([task], [photo], ai_results, [str(photo_id)], db))

    assert results[0]["result"]["tags_found"] == 1
    assert results[0]["status"] == "completed"
    assert photo.processed_tasks == {"classification": True}
    db.bulk_save_objects.assert_not_called()
    db.commit.assert_called_once()


def test_process_ai_results_skips_low_confidence_label(monkeypatch):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=uuid4(),
        file_path="/p/x.jpg",
        processed_tasks={},
    )
    task = _task(payload={"photo_id": str(photo_id)})
    ai_results = [{
        "status": "success",
        "predictions": [{"label": "beach", "confidence": 0.5}],
    }]

    monkeypatch.setattr(cls_mod, "get_tag_id", lambda db, name, owner: "tag-id")

    db = MagicMock()
    results = _run(strategy._process_ai_results([task], [photo], ai_results, [str(photo_id)], db))

    assert results[0]["result"]["tags_found"] == 0
    assert photo.processed_tasks == {"classification": True}


def test_process_ai_results_skips_others_label(monkeypatch):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=uuid4(),
        file_path="/p/x.jpg",
        processed_tasks={},
    )
    task = _task(payload={"photo_id": str(photo_id)})
    ai_results = [{
        "status": "success",
        "predictions": [{"label": "others", "confidence": 0.95}],
    }]

    monkeypatch.setattr(cls_mod, "get_tag_id", lambda db, name, owner: "tag-id")

    db = MagicMock()
    results = _run(strategy._process_ai_results([task], [photo], ai_results, [str(photo_id)], db))

    assert results[0]["result"]["tags_found"] == 0


def test_process_ai_results_enqueues_ticket_task_for_ticket_label(monkeypatch):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=uuid4(),
        file_path="/p/x.jpg",
        processed_tasks={},
    )
    task = _task(payload={"photo_id": str(photo_id)})
    ai_results = [{
        "status": "success",
        "predictions": [{"label": "\u706b\u8f66\u7968", "confidence": 0.93}],
    }]

    monkeypatch.setattr(cls_mod, "get_tag_id", lambda db, name, owner: "tag-id")

    db = MagicMock()
    _run(strategy._process_ai_results([task], [photo], ai_results, [str(photo_id)], db))

    db.bulk_save_objects.assert_called_once()
    saved = db.bulk_save_objects.call_args[0][0]
    assert len(saved) == 1
    assert saved[0].type == "RECOGNIZE_TICKET"
    assert saved[0].payload["photo_id"] == str(photo_id)
    assert saved[0].payload["file_path"] == "/p/x.jpg"


def test_process_ai_results_handles_missing_ai_result_entry():
    strategy = _strategy()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=uuid4(),
        file_path="/p/x.jpg",
        processed_tasks={},
    )
    task = _task(payload={"photo_id": str(photo_id)})

    # AI returned fewer entries than tasks; the missing slot is treated as empty.
    db = MagicMock()
    results = _run(strategy._process_ai_results([task], [photo], [], [str(photo_id)], db))

    assert results[0]["result"]["tags_found"] == 0
    assert results[0]["status"] == "completed"
    db.commit.assert_called_once()
