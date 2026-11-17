"""Nightly gap coverage (2026-11-16) - app/service/tasks/clip_classification.py.

The 2026-11-16 backend coverage scan reported
``service/tasks/clip_classification.py`` at 82% with 29 uncovered lines - the
second lowest coverage of any backend module.  The strategy is new (CLIP
classification jobs that must never hold a worker slot while waiting for the
image embedding) and had never been exercised by a unit test.

The gaps sit in the batch orchestration:

* ``26-36`` - a bulk task (no ``photo_id``) is processed on its own.
* ``37-46`` - a failing bulk task is reported as ``failed`` and the session is
  rolled back.
* ``23-24``/``50`` - per photo tasks are grouped per owner and processed in
  one go.
* ``51-54`` - a failing owner group marks every task of that group failed.
* ``102``/``108-119`` - a photo without an embedding (or with a stale one) is
  deferred instead of being scored.

The database is a ``MagicMock`` and the CLIP service layer is patched, so the
file stays a pure strategy test.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.service.tasks import clip_classification as clip_tasks
from app.service.tasks.clip_classification import ClipClassificationStrategy


pytestmark = pytest.mark.smoke


def _task(payload=None, owner_id=None, task_id=None, task_type="CLIP"):
    return SimpleNamespace(
        id=task_id or uuid4(),
        type=task_type,
        owner_id=owner_id,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_a_bulk_task_is_processed_on_its_own():
    """A task without a photo_id is handled by the regular single path."""
    strategy = ClipClassificationStrategy()
    task = _task(payload={"revisions": {}}, owner_id=None)

    with patch.object(
        strategy, "process", new=AsyncMock(return_value={"status": "success"})
    ) as process:
        results = await strategy.process_batch(MagicMock(), [task], MagicMock())

    process.assert_awaited_once()
    assert results == [
        {
            "task_id": task.id,
            "task_type": task.type,
            "status": "completed",
            "result": {"status": "success"},
        }
    ]


@pytest.mark.asyncio
async def test_a_failing_bulk_task_is_reported_as_failed():
    """A crashing task must not abort the whole batch."""
    strategy = ClipClassificationStrategy()
    task = _task(payload={"revisions": {}}, owner_id=None)
    db = MagicMock()

    with patch.object(strategy, "process", new=AsyncMock(side_effect=RuntimeError("boom"))):
        results = await strategy.process_batch(MagicMock(), [task], db)

    db.rollback.assert_called_once()
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"


@pytest.mark.asyncio
async def test_photo_tasks_are_grouped_per_owner():
    """Per photo tasks of one owner are processed together."""
    strategy = ClipClassificationStrategy()
    owner_id = uuid4()
    first = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_id)
    second = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_id)

    with patch.object(
        strategy,
        "process_photos",
        return_value=[{"task_id": first.id, "status": "completed"}],
    ) as process_photos:
        results = await strategy.process_batch(MagicMock(), [first, second], MagicMock())

    process_photos.assert_called_once()
    assert process_photos.call_args.args[1] == owner_id
    assert len(process_photos.call_args.args[2]) == 2
    assert results == [{"task_id": first.id, "status": "completed"}]


@pytest.mark.asyncio
async def test_a_failing_owner_group_marks_every_task_failed():
    """When the group fails, each task of that group is reported as failed."""
    strategy = ClipClassificationStrategy()
    owner_id = uuid4()
    first = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_id, task_type="CLIP")
    second = _task(payload={"photo_id": str(uuid4())}, owner_id=owner_id, task_type="CLIP")
    db = MagicMock()

    with patch.object(
        strategy, "process_photos", side_effect=RuntimeError("db down")
    ):
        results = await strategy.process_batch(MagicMock(), [first, second], db)

    db.rollback.assert_called_once()
    assert len(results) == 2
    assert all(r["status"] == "failed" for r in results)
    assert all(r["error"] == "db down" for r in results)


# --------------------------------------------------------------------------- #
# process_photos
# --------------------------------------------------------------------------- #

def _process_photos_db(photos, embeddings, cats, rules, pending_tasks=()):
    """A database stub whose five queries return the given rows."""
    db = MagicMock()
    photo_query = MagicMock()
    photo_query.filter.return_value = list(photos)
    vector_query = MagicMock()
    vector_query.filter.return_value = list(embeddings)
    category_query = MagicMock()
    category_query.filter_by.return_value.all.return_value = list(cats)
    rule_query = MagicMock()
    rule_query.filter.return_value = list(rules)
    task_query = MagicMock()
    task_query.filter.return_value = list(pending_tasks)
    db.query.side_effect = [
        photo_query,
        vector_query,
        category_query,
        rule_query,
        task_query,
    ]
    return db


def test_a_photo_without_a_matching_rule_is_skipped():
    """A photo whose rules were disabled in the meantime is skipped."""
    strategy = ClipClassificationStrategy()
    owner_id = uuid4()
    photo_id = uuid4()
    task = _task(payload={"photo_id": str(photo_id)}, owner_id=owner_id)

    db = _process_photos_db(photos=[], embeddings=[], cats=[], rules=[])

    with patch.object(clip_tasks.svc, "ai_url", return_value="http://ai.test"):
        results = strategy.process_photos(db, owner_id, [task])

    assert results[0]["result"] == {"status": "skipped"}


def test_a_photo_without_an_embedding_is_deferred():
    """Without a vector the photo waits for the embedding task."""
    strategy = ClipClassificationStrategy()
    owner_id = uuid4()
    photo_id = uuid4()
    category = SimpleNamespace(id=uuid4(), revision=1, tag_id=uuid4())
    task = _task(
        payload={"photo_id": str(photo_id), "revisions": {str(category.id): 1}},
        owner_id=owner_id,
    )
    photo = SimpleNamespace(id=photo_id)

    db = _process_photos_db(
        photos=[photo], embeddings=[], cats=[category], rules=[]
    )

    with patch.object(clip_tasks.svc, "ai_url", return_value="http://ai.test"), patch.object(
        clip_tasks.svc, "apply_batch_results", return_value={}
    ):
        results = strategy.process_photos(db, owner_id, [task])

    assert results[0]["result"]["status"] == "deferred"
    assert results[0]["result"]["reason"] == "waiting for image embedding"
    # An embedding task is scheduled for the deferred photo.
    assert db.add.called


def test_a_photo_with_an_outdated_embedding_is_deferred():
    """An embedding of a different model cannot be scored."""
    strategy = ClipClassificationStrategy()
    owner_id = uuid4()
    photo_id = uuid4()
    category = SimpleNamespace(id=uuid4(), revision=1, tag_id=uuid4())
    task = _task(
        payload={
            "photo_id": str(photo_id),
            "revisions": {str(category.id): 1},
            "model": "clip-vit-b32",
        },
        owner_id=owner_id,
    )
    photo = SimpleNamespace(id=photo_id)
    embedding = SimpleNamespace(photo_id=photo_id, model_name="clip-vit-l14", embedding=[0.1, 0.2])

    db = _process_photos_db(
        photos=[photo], embeddings=[embedding], cats=[category], rules=[]
    )

    with patch.object(clip_tasks.svc, "ai_url", return_value="http://ai.test"), patch.object(
        clip_tasks.svc, "apply_batch_results", return_value={}
    ):
        results = strategy.process_photos(db, owner_id, [task])

    assert results[0]["result"]["status"] == "deferred"