"""SQLite transaction and scheduling contracts for AI batches."""
import asyncio
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.crud import ocr as crud_ocr
from app.db.models.ocr import OCR
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.schemas.ocr import OCRCreate
from app.service.task_worker import TaskQueueManager
from app.service.tasks.ai_runtime import AIBatchSession
from app.service.tasks.ai_runtime import run_ai_batch
from app.db.models.task import Task, TaskType
from app.service.tasks.classification import ClassifyImageStrategy
from test_basic_pipeline_performance import seed

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_ocr_hundred_regions_one_commit(face_sqlite_session):
    bind = face_sqlite_session.get_bind()
    _, photos = seed(face_sqlite_session, 1)
    pid = photos[0].id
    commits = []
    event.listen(bind, 'commit', lambda _: commits.append(True))
    with AIBatchSession(bind=bind, autoflush=False, expire_on_commit=False) as db:
        crud_ocr.delete_ocr_by_photo_id(db, pid, commit=False)
        for i in range(100):
            crud_ocr.create_ocr(db, OCRCreate(photo_id=pid, text=str(i), text_score=.9, polygon=[]), commit=False)
        db.commit()
        assert db.query(OCR).filter(OCR.photo_id == pid).count() == 100
    assert len(commits) == 1


def test_classification_preserves_manual_tags(face_sqlite_session):
    db = face_sqlite_session
    uid, photos = seed(db, 1)
    manual = PhotoTag(owner_id=uid, tag_name='manual', type='manual')
    old = PhotoTag(owner_id=uid, tag_name='old', type='yolo')
    db.add_all([manual, old]); db.flush()
    db.add_all([PhotoTagRelation(photo_id=photos[0].id, tag_id=t.id) for t in (manual, old)])
    db.commit()
    task = SimpleNamespace(id=uuid4(), type='classify_image')
    result = asyncio.run(ClassifyImageStrategy()._process_ai_results(
        [task], photos, [{'status': 'success', 'predictions': [{'label': 'landscape', 'confidence': .99}]}], [photos[0].id], db))
    assert result[0]['status'] == 'completed'
    tags = db.query(PhotoTag).join(PhotoTagRelation).filter(PhotoTagRelation.photo_id == photos[0].id).all()
    assert {t.tag_name for t in tags} == {'manual', 'landscape'}


def test_saturated_model_keeps_lower_priority_model_waiting():
    async def run():
        queue = TaskQueueManager()
        await queue.put_batch('AI', [{'resource_key': 'ocr'}], 10)
        await queue.put_batch('AI', [{'resource_key': 'face'}], 9)
        ready = False
        pending = asyncio.create_task(queue.get_available_ai_batch(lambda b: ready))
        await asyncio.sleep(.06)
        assert not pending.done()
        assert queue.item_count('AI') == 2
        ready = True
        batch = await asyncio.wait_for(pending, .2)
        assert batch[0]['resource_key'] == 'ocr'
        queue.task_done('AI')
        assert queue.item_count('AI') == 1
        assert (await queue.get_batch('AI'))[0]['resource_key'] == 'face'
        queue.task_done('AI')
        await asyncio.wait_for(queue.queues['AI'].join(), .1)
    asyncio.run(run())


def test_ai_producer_drains_phase_including_retry_and_completion(face_sqlite_session, monkeypatch):
    from datetime import datetime, timedelta
    from app.service import task_worker
    from app.db.models.task import TaskStatus
    db = face_sqlite_session
    owner, _ = seed(db, 1)
    scene = Task(type=TaskType.CLASSIFY_IMAGE, priority=10, owner_id=owner, payload={})
    face = Task(type=TaskType.RECOGNIZE_FACE, priority=9, owner_id=owner, payload={})
    db.add_all([scene, face]); db.commit()
    monkeypatch.setattr(task_worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(db, 'close', lambda: None)
    worker = task_worker.TaskWorker()
    kinds = [TaskType.CLASSIFY_IMAGE, TaskType.RECOGNIZE_FACE]
    def fetch(queued=0, reserved=None):
        return worker._fetch_tasks_to_queues_sync(kinds, {'AI': queued}, reserved_task_ids=reserved)
    first = fetch()
    assert first and all(batch[0]['type'] == TaskType.CLASSIFY_IMAGE for _, batch in first)
    scene.status = TaskStatus.PROCESSING; db.commit()
    assert fetch() == []  # final batch is still running or awaiting completion persistence
    scene.status = TaskStatus.PENDING
    scene.next_retry_at = datetime.now() + timedelta(seconds=30); db.commit()
    assert fetch() == []  # a retry deadline does not admit the face model
    scene.status = TaskStatus.COMPLETED; db.commit()
    assert fetch(queued=1) == []
    assert fetch(reserved={scene.id}) == []
    second = fetch()
    assert second and all(batch[0]['type'] == TaskType.RECOGNIZE_FACE for _, batch in second)


def test_paused_ai_phase_can_yield_when_drained(face_sqlite_session, monkeypatch):
    from app.service import task_worker
    db = face_sqlite_session
    owner, _ = seed(db, 1)
    db.add_all([Task(type=kind, priority=priority, owner_id=owner, payload={})
                for kind, priority in [(TaskType.CLASSIFY_IMAGE, 10), (TaskType.RECOGNIZE_FACE, 9)]])
    db.commit()
    monkeypatch.setattr(task_worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(db, 'close', lambda: None)
    worker = task_worker.TaskWorker()
    worker.ai_phase_type = TaskType.CLASSIFY_IMAGE
    worker.paused_categories = {TaskType.CLASSIFY_IMAGE.value}
    batches = worker._fetch_tasks_to_queues_sync([TaskType.RECOGNIZE_FACE], {'AI': 0})
    assert batches and all(batch[0]['type'] == TaskType.RECOGNIZE_FACE for _, batch in batches)


def test_ai_batch_uses_thread_owned_session_and_keeps_loop_responsive(face_sqlite_session):
    db = face_sqlite_session
    owner, photos = seed(db, 1)
    task = Task(type=TaskType.OCR, owner_id=owner, payload={'photo_id': str(photos[0].id)})
    db.add(task); db.commit()
    tid = task.id
    main_thread = threading.get_ident()
    ticks = []
    class Strategy:
        resource_key = 'ocr'
        timeout = 1
        async def process_batch(self, worker, tasks, session):
            assert threading.get_ident() != main_thread
            assert session is not db
            time.sleep(.08)
            return [{'task_id': tasks[0].id, 'status': 'completed'}]
    async def run():
        future = asyncio.create_task(asyncio.to_thread(run_ai_batch, db.get_bind(), Strategy(), None, [tid]))
        while not future.done():
            ticks.append(True)
            await asyncio.sleep(.01)
        assert (await future)[0]['task_id'] == tid
    asyncio.run(run())
    assert len(ticks) >= 3


def test_uncommitted_ocr_batch_rolls_back_on_failure(face_sqlite_session):
    bind = face_sqlite_session.get_bind()
    _, photos = seed(face_sqlite_session, 1)
    pid = photos[0].id
    with pytest.raises(RuntimeError):
        with AIBatchSession(bind=bind, autoflush=False) as db:
            crud_ocr.create_ocr(db, OCRCreate(photo_id=pid, text='partial', text_score=.9, polygon=[]), commit=False)
            db.flush()
            raise RuntimeError('failed batch')
    with AIBatchSession(bind=bind) as db:
        assert db.query(OCR).count() == 0
        crud_ocr.create_ocr(db, OCRCreate(photo_id=pid, text='retry', text_score=.9, polygon=[]), commit=False)
        db.commit()
        assert db.query(OCR).count() == 1
