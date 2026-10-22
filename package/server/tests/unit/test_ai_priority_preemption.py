"""Priority changes must yield an AI phase without cancelling owned work."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.task import INTERACTIVE_TASK_PRIORITY, Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service import task_worker


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def scheduler(face_sqlite_session, monkeypatch):
    from app.core.config_manager import config_manager

    db = face_sqlite_session
    owner = uuid4()
    db.add(User(id=owner, username=str(owner), settings={}))
    db.commit()
    monkeypatch.setattr(task_worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(db, 'close', lambda: None)
    monkeypatch.setattr(config_manager, 'get_user_config', lambda *_: SimpleNamespace(
        ai=SimpleNamespace(analysis_connection_id='builtin')))
    worker = task_worker.TaskWorker()

    def add(kind, priority, **kwargs):
        row = Task(type=kind, priority=priority, owner_id=owner, payload={},
                   created_at=datetime.now(), **kwargs)
        db.add(row)
        db.commit()
        return row

    def fetch():
        return worker._fetch_tasks_to_queues_sync(
            worker._calculate_allowed_task_types(),
            {'AI': worker.queue_manager.item_count('AI')},
            reserved_task_ids=set(worker.reserved_task_ids),
        )

    return db, worker, add, fetch


def test_new_classification_withdraws_prefetch_waits_for_results_then_resumes(scheduler):
    db, worker, add, fetch = scheduler
    active = add(TaskType.VISUAL_DESCRIPTION, 1)
    queued = add(TaskType.VISUAL_DESCRIPTION, 1)
    remaining = add(TaskType.VISUAL_DESCRIPTION, 1)

    async def run():
        initial = fetch()
        assert initial
        for category, batch in initial:
            await worker.queue_manager.put_batch(category, batch, 1)
            worker.reserved_task_ids.update(t['id'] for t in batch)
        running_batch = await worker.queue_manager.get_batch('AI')
        assert running_batch[0]['id'] == active.id
        active.status = TaskStatus.PROCESSING
        db.commit()
        urgent = add(TaskType.CLASSIFY_IMAGE, 10)
        # Even a full prefetch queue must allow the producer to notice urgency.
        monkey_limit = worker._prefetch_limit
        worker._prefetch_limit = lambda *_: 1
        assert fetch() == []
        worker._prefetch_limit = monkey_limit
        assert worker.ai_phase_yield_requested
        worker._withdraw_ai_prefetch()
        assert worker.queue_manager.item_count('AI') == 0
        assert worker.reserved_task_ids == {active.id}
        assert db.get(Task, queued.id).status == TaskStatus.PENDING
        assert db.get(Task, remaining.id).status == TaskStatus.PENDING
        assert fetch() == []
        # Executor completion releases its reservation before result persistence.
        worker.reserved_task_ids.remove(active.id)
        worker.queue_manager.task_done('AI')
        assert fetch() == []
        db.delete(active)
        db.commit()
        batches = fetch()
        assert [t['id'] for _, batch in batches for t in batch] == [urgent.id]
        assert worker.ai_phase_type == TaskType.CLASSIFY_IMAGE
        assert not worker.ai_phase_yield_requested
        db.delete(urgent)
        db.commit()
        batches = fetch()
        assert {t['id'] for _, batch in batches for t in batch} == {queued.id, remaining.id}
        assert worker.ai_phase_type == TaskType.VISUAL_DESCRIPTION
        await asyncio.wait_for(worker.queue_manager.queues['AI'].join(), .1)

    asyncio.run(run())


@pytest.mark.parametrize('blocked', ['equal', 'lower', 'paused', 'backoff'])
def test_ineligible_or_nonurgent_work_does_not_preempt(scheduler, blocked):
    db, worker, add, fetch = scheduler
    current = add(TaskType.VISUAL_DESCRIPTION, 10)
    assert fetch()
    current.status = TaskStatus.PROCESSING
    db.commit()
    urgent = add(TaskType.CLASSIFY_IMAGE, {'equal': 10, 'lower': 9}.get(blocked, 11))
    if blocked == 'paused':
        worker.paused_categories = {TaskType.CLASSIFY_IMAGE.value}
    elif blocked == 'backoff':
        urgent.next_retry_at = datetime.now() + timedelta(minutes=1)
        db.commit()
    assert fetch() == []
    assert worker.ai_phase_type == TaskType.VISUAL_DESCRIPTION
    assert not worker.ai_phase_yield_requested


def test_dequeued_unclaimed_batch_must_drain_before_switch(scheduler):
    db, worker, add, fetch = scheduler
    current = add(TaskType.VISUAL_DESCRIPTION, 1)
    assert fetch()
    worker.reserved_task_ids.add(current.id)
    add(TaskType.CLASSIFY_IMAGE, 10)
    assert fetch() == []
    assert worker.ai_phase_yield_requested
    worker.reserved_task_ids.clear()
    assert fetch()[0][1][0]['type'] == TaskType.CLASSIFY_IMAGE


def test_retry_backoff_yields_to_higher_priority_and_cancelled_urgency_resumes(scheduler):
    db, worker, add, fetch = scheduler
    current = add(TaskType.VISUAL_DESCRIPTION, 1)
    assert fetch()
    current.next_retry_at = datetime.now() + timedelta(minutes=1)
    db.commit()
    urgent = add(TaskType.CLASSIFY_IMAGE, 10)
    assert fetch()[0][1][0]['id'] == urgent.id
    db.delete(urgent)
    current.next_retry_at = None
    db.commit()
    assert fetch()[0][1][0]['id'] == current.id


def test_interactive_task_can_preempt_a_paused_type(scheduler):
    db, worker, add, fetch = scheduler
    current = add(TaskType.VISUAL_DESCRIPTION, 1)
    assert fetch()
    worker.paused_categories = {TaskType.CLASSIFY_IMAGE.value}
    urgent = add(TaskType.CLASSIFY_IMAGE, INTERACTIVE_TASK_PRIORITY)
    assert fetch()[0][1][0]['id'] == urgent.id


def test_withdrawn_urgent_candidate_unblocks_current_phase(scheduler):
    db, worker, add, fetch = scheduler
    current = add(TaskType.VISUAL_DESCRIPTION, 1)
    assert fetch()
    current.status = TaskStatus.PROCESSING
    db.commit()
    urgent = add(TaskType.CLASSIFY_IMAGE, 10)
    assert fetch() == []
    assert worker.ai_phase_yield_requested
    urgent.status = TaskStatus.CANCELLED
    db.commit()
    assert fetch() == []
    assert not worker.ai_phase_yield_requested
    current.status = TaskStatus.COMPLETED
    db.commit()
    assert fetch() == []
    assert worker.ai_phase_type is None


def test_consumer_stops_admitting_old_batches_during_yield(monkeypatch):
    async def run():
        worker = task_worker.TaskWorker()
        worker.running = True
        worker.ai_phase_yield_requested = True
        low = {'id': uuid4(), 'type': TaskType.VISUAL_DESCRIPTION,
               'resource_key': 'local_llm'}
        high = {'id': uuid4(), 'type': TaskType.CLASSIFY_IMAGE,
                'resource_key': 'classification'}
        worker.reserved_task_ids.add(low['id'])
        await worker.queue_manager.put_batch('AI', [low], 1)
        executed = []
        finished = asyncio.Event()

        async def execute(batch, category):
            executed.extend(t['id'] for t in batch)
            worker.reserved_task_ids.difference_update(t['id'] for t in batch)
            finished.set()

        monkeypatch.setattr(worker, 'execute_batch_task_wrapper', execute)
        consumer = asyncio.create_task(worker.consumer_loop('AI'))
        try:
            await asyncio.sleep(.1)
            assert executed == []
            assert worker.queue_manager.item_count('AI') == 1
            worker._withdraw_ai_prefetch()
            assert not worker.reserved_task_ids
            worker.ai_phase_yield_requested = False
            await worker.queue_manager.put_batch('AI', [high], 10)
            await asyncio.wait_for(finished.wait(), 1)
            assert executed == [high['id']]
            await asyncio.wait_for(worker.queue_manager.queues['AI'].join(), 1)
        finally:
            worker.running = False
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)

    asyncio.run(run())


def test_model_wait_yields_to_ready_lower_priority_type(scheduler):
    db, worker, add, fetch = scheduler
    waiting = add(TaskType.CLASSIFY_IMAGE, 10,
                  error="等待 AI 模型：分类模型正在下载，完成后自动继续",
                  next_retry_at=datetime.now() + timedelta(minutes=1))
    ready = add(TaskType.RECOGNIZE_FACE, 9)
    worker.ai_phase_type = TaskType.CLASSIFY_IMAGE
    batches = fetch()
    assert [t['id'] for _, batch in batches for t in batch] == [ready.id]
    assert worker.ai_phase_type == TaskType.RECOGNIZE_FACE
    # After the wait expires, the higher priority type becomes eligible again.
    db.delete(ready)
    waiting.next_retry_at = datetime.now() - timedelta(seconds=1)
    db.commit()
    assert [t['id'] for _, batch in fetch() for t in batch] == [waiting.id]
