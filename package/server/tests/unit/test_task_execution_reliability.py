"""Real SQLite and executor regressions for task admission and acknowledgement."""
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.user import User
from app.service import task_worker
from app.service.disk_budget import DiskBudget
from app.service.task_runtime import run_in_executor_owned

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def seed(db, types):
    owner = uuid4()
    db.add(User(id=owner, username=str(owner), settings={}))
    tasks = [Task(id=uuid4(), type=kind, status=TaskStatus.PENDING,
                  priority=100-i, owner_id=owner, payload={}) for i, kind in enumerate(types)]
    db.add_all(tasks)
    db.commit()
    return owner, [t.id for t in tasks]


@pytest.mark.asyncio
async def test_completion_commit_failure_retries_without_events_counters_or_duplicate_followups(face_sqlite_session, monkeypatch):
    from app.schemas.photo import PhotoCreate
    from app.schemas.metadata import PhotoMetadataCreate
    db = face_sqlite_session
    owner, ids = seed(db, [TaskType.PROCESS_BASIC, TaskType.CLASSIFY_IMAGE])
    photo_id = uuid4()
    db.add(Photo(id=photo_id, owner_id=owner, filename='x.jpg', file_path='/x.jpg',
                 file_type=FileType.image, processed_tasks={}))
    db.commit()
    fail = True
    threads = []
    class FlushSession(Session):
        def commit(self):
            nonlocal fail
            threads.append(threading.get_ident())
            if fail:
                fail = False
                raise OSError('temporary write failure')
            super().commit()
    monkeypatch.setattr(task_worker, 'SessionLocal', sessionmaker(bind=db.get_bind(), class_=FlushSession))
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    items = [
        {'task_id': ids[0], 'task_type': TaskType.PROCESS_BASIC, 'status': 'completed',
         'result': {'photo_create_data': {
             'photo_id': photo_id, 'file_path': '/x.jpg', 'user_id': str(owner),
             'photo': PhotoCreate(filename='x.jpg', file_type=FileType.image, size=123),
             'metadata': PhotoMetadataCreate(exif_info='{}'), 'is_pre_created': True,
         }}},
        {'task_id': ids[1], 'task_type': TaskType.CLASSIFY_IMAGE, 'status': 'completed', 'result': {}},
    ]
    with pytest.raises(OSError, match='temporary write'):
        await worker._flush_results(items)
    db.expire_all()
    assert db.query(Task).count() == 2
    assert worker.scan_status['classified'] == 0
    worker._publish.assert_not_called()
    await worker._flush_results(items)
    db.expire_all()
    assert db.query(Task).count() == 6
    assert all(db.get(Task, tid) is None for tid in ids)
    assert worker.scan_status['classified'] == 1
    assert worker._publish.call_count == 2
    assert all(t != threading.get_ident() for t in threads)
    await worker._flush_results(items)  # Replayed delivery after successful commit.
    db.expire_all()
    assert db.query(Task).count() == 6
    assert worker.scan_status['classified'] == 1
    assert worker._publish.call_count == 2


@pytest.mark.asyncio
async def test_result_loop_retains_failed_batch_and_stops_consuming(monkeypatch):
    worker = task_worker.TaskWorker()
    worker.running = True
    worker.result_queue = asyncio.Queue(maxsize=64)
    for i in range(51):
        worker.result_queue.put_nowait({'task_id': i})
    attempts = []
    async def flush(items):
        attempts.append([i['task_id'] for i in items])
        assert not worker.is_drained()
        if len(attempts) == 1:
            raise OSError('busy')
        assert worker.result_queue.qsize() == 1
        worker.running = False
    monkeypatch.setattr(worker, '_flush_results', flush)
    monkeypatch.setattr(worker, '_save_system_state', lambda *a: None)
    await asyncio.wait_for(worker.result_loop(), 2)
    assert attempts == [list(range(50)), list(range(50))]
    assert worker._pending_results == []
    assert worker.result_queue._unfinished_tasks == 1


@pytest.mark.asyncio
async def test_timeout_keeps_resource_slot_and_processing_until_explicit_pool_job_finishes(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    _, ids = seed(db, [TaskType.PROCESS_BASIC, TaskType.PROCESS_BASIC])
    monkeypatch.setattr(task_worker, 'SessionLocal', sessionmaker(bind=db.get_bind()))
    started, release = threading.Event(), threading.Event()
    worker = task_worker.TaskWorker()
    worker.batch_pool = ThreadPoolExecutor(max_workers=2)
    worker.thread_pool = ThreadPoolExecutor(max_workers=2)
    def job():
        started.set()
        release.wait(2)
    class Strategy:
        resource_key = 'one'
        timeout = .025
        max_attempts = 3
        async def process_batch(self, worker, tasks, session):
            await run_in_executor_owned(worker.thread_pool, job)
            return [{'task_id': t.id, 'task_type': t.type, 'status': 'completed'} for t in tasks]
    monkeypatch.setattr(task_worker.TaskStrategyFactory, 'get_strategy', lambda _: Strategy())
    def info(tid):
        return [{'id': tid, 'type': TaskType.PROCESS_BASIC, 'resource_key': 'one'}]
    first = asyncio.create_task(worker.execute_batch_task_wrapper(info(ids[0]), 'CPU'))
    second = None
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(.005)
        assert started.is_set()
        second = asyncio.create_task(worker.execute_batch_task_wrapper(info(ids[1]), 'CPU'))
        await asyncio.sleep(.075)
        db.expire_all()
        assert worker._resource_limiter('one').in_use == 1
        assert db.get(Task, ids[0]).status == 'processing'
        assert db.get(Task, ids[1]).status == 'pending'
        assert not first.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 2)
        db.expire_all()
        assert db.get(Task, ids[0]).status == 'pending'
        assert db.get(Task, ids[0]).attempt_count == 1
        assert worker._resource_limiter('one').in_use == 0
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
        worker.thread_pool.shutdown()
        worker.batch_pool.shutdown()


@pytest.mark.asyncio
async def test_synchronous_strategy_and_claim_leave_scheduler_responsive(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    _, ids = seed(db, [TaskType.SIMILAR_PHOTO_CLUSTERING])
    threads = []
    class SlowSession(Session):
        def commit(self):
            threads.append(threading.get_ident())
            time.sleep(.04)
            super().commit()
    monkeypatch.setattr(task_worker, 'SessionLocal', sessionmaker(bind=db.get_bind(), class_=SlowSession))
    class Strategy:
        resource_key = 'one'
        timeout = 1
        max_attempts = 3
        async def process_batch(self, worker, tasks, session):
            threads.append(threading.get_ident())
            time.sleep(.06)
            return [{'task_id': t.id, 'task_type': t.type, 'status': 'completed'} for t in tasks]
    monkeypatch.setattr(task_worker.TaskStrategyFactory, 'get_strategy', lambda _: Strategy())
    worker = task_worker.TaskWorker()
    future = asyncio.create_task(worker.execute_batch_task_wrapper(
        [{'id': ids[0], 'type': TaskType.SIMILAR_PHOTO_CLUSTERING, 'resource_key': 'one'}], 'CPU'))
    ticks = 0
    while not future.done():
        ticks += 1
        await asyncio.sleep(.005)
    await future
    assert ticks >= 8
    assert all(t != threading.get_ident() for t in threads)
    assert worker.result_queue.qsize() == 1


@pytest.mark.parametrize('kind,size', [(TaskType.CLASSIFY_IMAGE, 8), (TaskType.EXTRACT_METADATA, 16), (TaskType.PROCESS_BASIC, 4)])
def test_low_profile_prefetch_fills_complete_batches(face_sqlite_session, monkeypatch, kind, size):
    db = face_sqlite_session
    seed(db, [kind] * 80)
    monkeypatch.setattr(task_worker, 'SessionLocal', sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(task_worker, 'resolve_concurrency_level', lambda _: 'low')
    monkeypatch.setattr(task_worker, '_available_cpu_cores', lambda: 4)
    worker = task_worker.TaskWorker()
    batches = worker._fetch_tasks_to_queues_sync([kind], {})
    assert len(batches) >= 2
    assert all(len(batch) == size for _, batch in batches)
    assert sum(len(batch) for _, batch in batches) <= 128


def test_reserved_high_priority_type_does_not_hide_other_cpu_work(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    _, ids = seed(db, [TaskType.PROCESS_BASIC, TaskType.GENERATE_THUMBNAIL])
    monkeypatch.setattr(task_worker, 'SessionLocal', sessionmaker(bind=db.get_bind()))
    batches = task_worker.TaskWorker()._fetch_tasks_to_queues_sync(
        [TaskType.PROCESS_BASIC, TaskType.GENERATE_THUMBNAIL], {}, reserved_task_ids={ids[0]})
    assert batches[0][1][0]['id'] == ids[1]


@pytest.mark.asyncio
async def test_producer_wakes_before_poll_deadline(monkeypatch):
    worker = task_worker.TaskWorker()
    worker.running = True
    worker._loop = asyncio.get_running_loop()
    fetched = asyncio.Queue()
    calls = 0
    def fetch(*args):
        nonlocal calls
        calls += 1
        worker._loop.call_soon_threadsafe(fetched.put_nowait, calls)
        if calls == 2:
            worker.running = False
            worker.wake()
        return []
    monkeypatch.setattr(worker, '_fetch_tasks_to_queues_sync', fetch)
    monkeypatch.setattr(worker, '_sync_system_state_if_needed', lambda: None)
    monkeypatch.setattr(worker, '_save_system_state', lambda *a: None)
    monkeypatch.setattr(worker, '_manage_pool_lifecycle', lambda: None)
    future = asyncio.create_task(worker.worker_loop())
    try:
        assert await asyncio.wait_for(fetched.get(), 1) == 1
        worker.wake()
        assert await asyncio.wait_for(fetched.get(), .4) == 2
        await asyncio.wait_for(future, .4)
    finally:
        future.cancel()
        await asyncio.gather(future, return_exceptions=True)


def test_media_budget_limits_shared_volume_and_releases_nested_failed_jobs(tmp_path):
    budget = DiskBudget(2)
    active = peak = 0
    lock = threading.Lock()
    def job(i):
        nonlocal active, peak
        with budget.slot(tmp_path / str(i)), budget.slot(tmp_path):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.01)
            with lock:
                active -= 1
            if i == 0:
                raise OSError('bad image')
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(job, i) for i in range(12)]
        for future in futures:
            try:
                future.result(timeout=2)
            except OSError:
                pass
    assert peak == 2
    assert active == 0
    assert all(value == 0 for value in budget._active.values())
