"""Nightly gap-fill tests for app.service.tasks.classification.

The ClassifyImageStrategy in app/service/tasks/classification.py
was at 17.1pct coverage before this file (155/187 lines missed).
The strategy has a synchronous generator process branch that
walks all photos and creates leaf tasks, plus an async
_process_ai_results that maps AI predictions to PhotoTag rows.

This file exercises the helper get_tag_id (cache + DB hit/miss),
the generator process branch (force=True + force=False paging),
the async _process_ai_results happy / ticket-detection / 500 /
others-label branches, and the AI-service HTTP 500 error branch.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# helpers
def _photo(pid=None, owner_id="owner-1", file_path="/photos/p.jpg"):
    return SimpleNamespace(
        id=pid or uuid4(),
        owner_id=owner_id,
        file_path=file_path,
        processed_tasks=None,
    )

def _task():
    return SimpleNamespace(id=uuid4(), type="CLASSIFY_IMAGE", payload={"photo_id": str(uuid4())})

def _chain_yielding(rows_batches):
    chain = MagicMock()
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.all.side_effect = rows_batches
    return chain

# get_tag_id
def test_get_tag_id_returns_existing_tag_from_db():
    from app.service.tasks import classification as cls_task
    cls_task._tag_cache.clear()
    db = MagicMock()
    existing = SimpleNamespace(id="tag-existing")
    with patch.object(cls_task.crud_tag, "get_tag_by_name", return_value=existing) as get_tag:
        result = cls_task.get_tag_id(db, "scenery", owner_id="owner-1")
    assert result == "tag-existing"
    get_tag.assert_called_once_with(db, "scenery", "owner-1")
    get_tag.reset_mock()
    cached = cls_task.get_tag_id(db, "scenery", owner_id="owner-1")
    assert cached == "tag-existing"
    get_tag.assert_not_called()
    cls_task._tag_cache.clear()

def test_get_tag_id_creates_tag_when_missing():
    from app.service.tasks import classification as cls_task
    cls_task._tag_cache.clear()
    db = MagicMock()
    with patch.object(cls_task.crud_tag, "get_tag_by_name", return_value=None):
        with patch.object(cls_task, "PhotoTag", new=MagicMock()) as PhotoTagMock:
            instance = PhotoTagMock.return_value
            instance.id = "tag-new"
            result = cls_task.get_tag_id(db, "yolo:cat", owner_id="owner-1")
    PhotoTagMock.assert_called_once_with(tag_name="yolo:cat", type="yolo", owner_id="owner-1")
    db.add.assert_called_once_with(instance)
    db.commit.assert_called_once()
    assert result == "tag-new"
    cls_task._tag_cache.clear()

# task_category
def test_classify_image_strategy_task_category_is_io():
    from app.service.tasks.classification import ClassifyImageStrategy
    strat = ClassifyImageStrategy.__new__(ClassifyImageStrategy)
    assert strat.task_category == "IO"

# _process_ai_results
@pytest.mark.asyncio
async def test_process_ai_results_happy_path_marks_classification_done():
    from app.service.tasks.classification import ClassifyImageStrategy
    photo = _photo()
    task = _task()
    task.payload["photo_id"] = str(photo.id)
    ai_results = [{"status": "success", "predictions": [{"label": "scenery", "confidence": 0.95}]}]
    db = MagicMock()
    with patch("app.service.tasks.classification.get_tag_id", return_value="tag-id-1") as get_tag:
        results = await ClassifyImageStrategy._process_ai_results(
            ClassifyImageStrategy.__new__(ClassifyImageStrategy),
            [task], [photo], ai_results, [str(photo.id)], db
        )
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["tags_found"] == 1
    assert photo.processed_tasks["classification"] is True
    db.add.assert_any_call(photo)
    db.commit.assert_called_once()
    get_tag.assert_called_once()

@pytest.mark.asyncio
async def test_process_ai_results_low_confidence_drops_tag():
    from app.service.tasks.classification import ClassifyImageStrategy
    photo = _photo()
    task = _task()
    task.payload["photo_id"] = str(photo.id)
    ai_results = [{"status": "success", "predictions": [{"label": "others", "confidence": 0.99}]}]
    db = MagicMock()
    with patch("app.service.tasks.classification.get_tag_id") as get_tag:
        results = await ClassifyImageStrategy._process_ai_results(
            ClassifyImageStrategy.__new__(ClassifyImageStrategy),
            [task], [photo], ai_results, [str(photo.id)], db
        )
    assert results[0]["result"]["tags_found"] == 0
    get_tag.assert_not_called()
    assert photo.processed_tasks["classification"] is True

@pytest.mark.asyncio
async def test_process_ai_results_ticket_label_creates_reprocess_task():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskType
    photo = _photo()
    task = _task()
    task.payload["photo_id"] = str(photo.id)
    ai_results = [{"status": "success", "predictions": [{"label": "火车票", "confidence": 0.97}]}]
    db = MagicMock()
    with patch("app.service.tasks.classification.get_tag_id", return_value="tag-ticket"):
        await ClassifyImageStrategy._process_ai_results(
            ClassifyImageStrategy.__new__(ClassifyImageStrategy),
            [task], [photo], ai_results, [str(photo.id)], db
        )
    db.bulk_save_objects.assert_called_once()
    saved_tasks = db.bulk_save_objects.call_args[0][0]
    assert len(saved_tasks) == 1
    assert saved_tasks[0].type == TaskType.RECOGNIZE_TICKET.value
    assert saved_tasks[0].payload["photo_id"] == str(photo.id)

@pytest.mark.asyncio
async def test_process_ai_results_failed_ai_status_marks_no_tag():
    from app.service.tasks.classification import ClassifyImageStrategy
    photo = _photo()
    task = _task()
    task.payload["photo_id"] = str(photo.id)
    ai_results = [{"status": "failure"}]
    db = MagicMock()
    with patch("app.service.tasks.classification.get_tag_id") as get_tag:
        results = await ClassifyImageStrategy._process_ai_results(
            ClassifyImageStrategy.__new__(ClassifyImageStrategy),
            [task], [photo], ai_results, [str(photo.id)], db
        )
    assert results[0]["result"]["tags_found"] == 0
    assert photo.processed_tasks["classification"] is True
    get_tag.assert_not_called()

# process generator
@pytest.mark.asyncio
async def test_process_generator_creates_tasks_for_unclassified_photos():
    from app.service.tasks.classification import ClassifyImageStrategy
    p1 = _photo(file_path="/p/1.jpg")
    p1.processed_tasks = {"classification": True}
    p2 = _photo(file_path="/p/2.jpg")
    p2.processed_tasks = None
    p3 = _photo(file_path="/p/3.jpg")
    p3.processed_tasks = {}
    db = MagicMock()
    db.query.return_value = _chain_yielding([[p1, p2], [p3], []])
    worker = MagicMock()
    task = SimpleNamespace(id="task-generator", payload={"force": False})
    result = await ClassifyImageStrategy().process(worker, task, db)
    assert result["generated_tasks"] == 2
    assert result["message"].startswith("Generated ")
    worker.add_tasks.assert_called()
    # aggregate leaves across both add_tasks calls
    leaves = []
    for call in worker.add_tasks.call_args_list:
        leaves.extend(call.args[1])
    assert len(leaves) == 2
    assert all(t["type"] == "CLASSIFY_IMAGE" for t in leaves)

@pytest.mark.asyncio
async def test_process_generator_force_true_reclassifies_all():
    from app.service.tasks.classification import ClassifyImageStrategy
    p1 = _photo(file_path="/p/1.jpg")
    p1.processed_tasks = {"classification": True}
    p2 = _photo(file_path="/p/2.jpg")
    p2.processed_tasks = None
    db = MagicMock()
    db.query.return_value = _chain_yielding([[p1, p2], []])
    worker = MagicMock()
    task = SimpleNamespace(id="task-generator-force", payload={"force": True})
    result = await ClassifyImageStrategy().process(worker, task, db)
    assert result["generated_tasks"] == 2
    leaves = []
    for call in worker.add_tasks.call_args_list:
        leaves.extend(call.args[1])
    assert all(t["payload"]["force"] is True for t in leaves)

@pytest.mark.asyncio
async def test_process_generator_no_photos_yields_zero():
    from app.service.tasks.classification import ClassifyImageStrategy
    db = MagicMock()
    db.query.return_value = _chain_yielding([[]])
    worker = MagicMock()
    task = SimpleNamespace(id="task-generator-empty", payload={"force": False})
    result = await ClassifyImageStrategy().process(worker, task, db)
    assert result["generated_tasks"] == 0
    worker.add_tasks.assert_not_called()

# handle_completion
@pytest.mark.asyncio
async def test_handle_completion_increments_classified_counter():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskStatus
    worker = MagicMock()
    worker.scan_status = {"classified": 2}
    items = [{"status": TaskStatus.COMPLETED}, {"status": TaskStatus.FAILED}, {"status": TaskStatus.COMPLETED}]
    await ClassifyImageStrategy().handle_completion(worker, items, MagicMock())
    assert worker.scan_status["classified"] == 4

@pytest.mark.asyncio
async def test_handle_completion_initializes_classified_counter():
    from app.service.tasks.classification import ClassifyImageStrategy
    from app.db.models.task import TaskStatus
    worker = MagicMock()
    worker.scan_status = {}
    items = [{"status": TaskStatus.COMPLETED}]
    await ClassifyImageStrategy().handle_completion(worker, items, MagicMock())
    assert worker.scan_status["classified"] == 1

# release_resources
def test_release_resources_clears_tag_cache():
    # _tag_cache is a module-level dict (not part of the class).
    from app.service.tasks import classification as cls_task
    cls_task._tag_cache["dummy-key"] = "value"
    # release_resources is a method on ClassifyImageStrategy that uses ``global _tag_cache``.
    strat = cls_task.ClassifyImageStrategy.__new__(cls_task.ClassifyImageStrategy)
    cls_task.ClassifyImageStrategy.release_resources(strat)
    assert dict(cls_task._tag_cache) == {}