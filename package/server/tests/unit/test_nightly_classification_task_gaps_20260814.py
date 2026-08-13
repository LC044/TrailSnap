"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/service/tasks/classification.py -- ClassifyImageStrategy.process (generator
  mode: empty batch, no-force shortcut, force=True, exception path), process_batch
  routing (generator vs photo tasks), _process_generator_tasks (happy + failure),
  handle_completion (counter increment), release_resources (cache clear),
  get_tag_id (cache hit/miss/create).
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _task(**kw):
    base = {"id": uuid4(), "type": None, "owner_id": uuid4(), "payload": {}}
    base.update(kw)
    return SimpleNamespace(**base)


def _photo(**kw):
    base = {"id": uuid4(), "owner_id": uuid4(), "file_type": 0,
            "file_path": "/tmp/p.jpg", "processed_tasks": {}}
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _chain_db_query(db, batches):
    chain = db.query.return_value
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    calls = {"i": 0}

    def _consume(_=None):
        idx = calls["i"]
        calls["i"] += 1
        if idx < len(batches):
            return batches[idx]
        return []

    chain.all.side_effect = _consume
    return chain


def test_classify_strategy_task_category_is_io():
    from app.service.tasks import classification as classify_tasks
    s = classify_tasks.ClassifyImageStrategy()
    assert s.task_category == "IO"


def test_classify_strategy_registered_in_factory():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.service.task_strategy import TaskStrategyFactory
    from app.db.models.task import TaskType
    s = TaskStrategyFactory.get_strategy(TaskType.CLASSIFY_IMAGE)
    assert isinstance(s, ClassifyImageStrategy)


def test_process_generator_empty_db_returns_zero():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    _chain_db_query(db, [[]])
    strategy = ClassifyImageStrategy()
    task = _task(payload={})
    res = _run(strategy.process(MagicMock(), task, db))
    assert res["processed"] == 0
    assert res["generated_tasks"] == 0
    assert "Generated 0" in res["message"]


def test_process_generator_no_force_skips_processed():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskType, DEFAULT_PRIORITIES
    db = MagicMock()
    processed_photo = _photo(id=uuid4(), processed_tasks={"classification": True})
    fresh_photo = _photo(id=uuid4(), processed_tasks={})
    _chain_db_query(db, [[processed_photo, fresh_photo], []])
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    task = _task(payload={"force": False})
    res = _run(strategy.process(worker, task, db))
    assert res["generated_tasks"] == 1
    args, _ = worker.add_tasks.call_args
    generated = args[1]
    assert generated[0]["payload"]["photo_id"] == str(fresh_photo.id)
    assert generated[0]["type"] == TaskType.CLASSIFY_IMAGE
    assert generated[0]["priority"] == DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE]


def test_process_generator_force_includes_all():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    processed_photo = _photo(id=uuid4(), processed_tasks={"classification": True})
    unprocessed_photo = _photo(id=uuid4(), processed_tasks={})
    _chain_db_query(db, [[processed_photo, unprocessed_photo], []])
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    task = _task(payload={"force": True})
    res = _run(strategy.process(worker, task, db))
    assert res["generated_tasks"] == 2


def test_process_generator_exception_propagates():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    strategy = ClassifyImageStrategy()
    task = _task(payload={})
    with pytest.raises(RuntimeError, match="db down"):
        _run(strategy.process(MagicMock(), task, db))


def test_process_batch_routes_to_owner_and_generator():
    from app.service.tasks.classification import ClassifyImageStrategy
    owner = uuid4()
    photo_id = str(uuid4())
    gen_task = _task(payload={})
    photo_task = _task(payload={"photo_id": photo_id}, owner_id=owner)
    db = MagicMock()
    strategy = ClassifyImageStrategy()

    owner_results = [{"task_id": photo_task.id, "task_type": None,
                      "status": "completed", "result": {"status": "success"}}]
    gen_results = [{"task_id": gen_task.id, "task_type": None,
                    "status": "completed", "result": {"status": "ok"}}]

    with patch.object(strategy, "_process_generator_tasks",
                      AsyncMock(return_value=gen_results)), \
         patch.object(strategy, "_process_owner_batch",
                      AsyncMock(return_value=owner_results)):
        results = _run(strategy.process_batch(MagicMock(), [gen_task, photo_task], db))
    assert len(results) == 2
    task_ids = {r["task_id"] for r in results}
    assert gen_task.id in task_ids
    assert photo_task.id in task_ids


def test_process_batch_only_photo_tasks():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    photo_id = str(uuid4())
    photo_task = _task(payload={"photo_id": photo_id}, owner_id=uuid4())
    expected = [{"task_id": photo_task.id, "task_type": None,
                 "status": "completed", "result": {"ok": 1}}]
    with patch.object(strategy, "_process_generator_tasks",
                      AsyncMock(return_value=[])), \
         patch.object(strategy, "_process_owner_batch",
                      AsyncMock(return_value=expected)):
        results = _run(strategy.process_batch(MagicMock(), [photo_task], db))
    assert results == expected


def test_process_batch_only_generator_tasks():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    gen_task = _task(payload={})
    expected = [{"task_id": gen_task.id, "task_type": None,
                 "status": "completed", "result": {"generated": 5}}]
    with patch.object(strategy, "_process_generator_tasks",
                      AsyncMock(return_value=expected)), \
         patch.object(strategy, "_process_owner_batch",
                      AsyncMock(return_value=[])):
        results = _run(strategy.process_batch(MagicMock(), [gen_task], db))
    assert results == expected


def test_process_generator_tasks_happy_path():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    tasks = [_task(payload={}), _task(payload={})]
    process_res = {"processed": 0, "generated_tasks": 3,
                   "message": "Generated 3 classification tasks"}
    with patch.object(strategy, "process", AsyncMock(return_value=process_res)):
        results = _run(strategy._process_generator_tasks(worker, tasks, db))
    assert len(results) == 2
    for r in results:
        assert r["status"] == "completed"
        assert r["result"] == process_res
        assert r["error"] is None


def test_process_generator_tasks_failed_status_payload():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    task = _task(payload={})
    failed = {"status": "failed", "error": "boom"}
    with patch.object(strategy, "process", AsyncMock(return_value=failed)):
        results = _run(strategy._process_generator_tasks(worker, [task], db))
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"


def test_process_generator_tasks_exception_captures():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    task = _task(payload={})
    with patch.object(strategy, "process",
                      AsyncMock(side_effect=RuntimeError("broken"))):
        results = _run(strategy._process_generator_tasks(worker, [task], db))
    assert results[0]["status"] == "failed"
    assert "broken" in results[0]["error"]


def test_handle_completion_initializes_counter():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskStatus
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    worker.scan_status = {}
    items = [{"status": TaskStatus.COMPLETED, "task_id": 1}]
    _run(strategy.handle_completion(worker, items, db))
    assert worker.scan_status["classified"] == 1


def test_handle_completion_accumulates():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskStatus
    db = MagicMock()
    strategy = ClassifyImageStrategy()
    worker = MagicMock()
    worker.scan_status = {"classified": 5}
    items = [
        {"status": TaskStatus.COMPLETED, "task_id": 1},
        {"status": TaskStatus.COMPLETED, "task_id": 2},
        {"status": TaskStatus.FAILED, "task_id": 3},
    ]
    _run(strategy.handle_completion(worker, items, db))
    assert worker.scan_status["classified"] == 7


def test_release_resources_clears_tag_cache():
    from app.service.tasks import classification as classify_tasks
    classify_tasks._tag_cache["cached-tag-name"] = "tag-id-1"
    strategy = classify_tasks.ClassifyImageStrategy()
    strategy.release_resources()
    assert classify_tasks._tag_cache == {}


def test_get_tag_id_cache_hit():
    from app.service.tasks import classification as classify_tasks
    classify_tasks._tag_cache["cache-only"] = "cached-id"
    db = MagicMock()
    res = classify_tasks.get_tag_id(db, "cache-only", owner_id=uuid4())
    assert res == "cached-id"
    db.query.assert_not_called()
    classify_tasks._tag_cache.clear()


def test_get_tag_id_fetches_existing_tag():
    from app.service.tasks import classification as classify_tasks
    existing_id = uuid4()
    existing = MagicMock()
    existing.id = existing_id
    db = MagicMock()
    with patch("app.service.tasks.classification.crud_tag.get_tag_by_name",
               return_value=existing) as m_get:
        res = classify_tasks.get_tag_id(db, "fetch-me", owner_id=uuid4())
    assert res == str(existing_id)
    m_get.assert_called_once()
    db.add.assert_not_called()
    db.commit.assert_not_called()
    classify_tasks._tag_cache.clear()


def test_get_tag_id_creates_and_caches_new_tag():
    from app.service.tasks import classification as classify_tasks
    db = MagicMock()
    new_id = uuid4()

    class _StubTag:
        id = new_id

    with patch("app.service.tasks.classification.crud_tag.get_tag_by_name",
               return_value=None):
        def _refresh(_tag):
            _tag.id = new_id
        db.refresh.side_effect = _refresh
        res = classify_tasks.get_tag_id(db, "new-tag", owner_id=uuid4())
    assert res == str(new_id)
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert classify_tasks._tag_cache["new-tag"] == str(new_id)
    classify_tasks._tag_cache.clear()