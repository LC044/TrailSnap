"""Lazy CLIP initialization, migration replay and recoverable AI startup."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
import requests
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.db.clip_upgrade import queue_clip_classification, remove_clip_classification
from app.db.models import User, Photo
from app.db.models.clip_classification import ClipCategory, ClipRuleRevision
from app.db.models.photo import FileType
from app.db.models.tag import PhotoTag
from app.db.models.task import Task, TaskStatus, TaskType
from app.service import clip_classification as svc, ai_model_state as state
from app.service.tasks.clip_classification import ClipClassificationStrategy

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def add_owner(db):
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.flush()
    photo = Photo(owner_id=owner.id, filename="test.jpg", file_path="test.jpg",
                  file_type=FileType.image)
    db.add(photo)
    db.commit()
    return owner, photo


def test_first_photo_initializes_enabled_rules_with_bounded_writes(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, photo = add_owner(db)
    assert db.query(ClipCategory).count() == 0
    monkeypatch.setattr(svc.requests, "post", lambda *a, **kw: pytest.fail("initialization called AI"))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        task = svc.enqueue_photo(db, photo)
        db.commit()
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    count = len(svc.load_catalog()["categories"])
    assert db.query(ClipCategory).filter_by(owner_id=owner.id, enabled=True).count() == count
    assert len(task.payload["revisions"]) == count
    assert len([sql for sql in statements if sql.startswith("INSERT")]) == 4
    cat = db.query(ClipCategory).first()
    cat.enabled, cat.is_deleted = False, True
    rule = db.get(ClipRuleRevision, (cat.id, 1))
    rule.descriptions = ["my edited description"]
    db.commit()
    assert not svc.ensure_presets(db, owner.id)
    assert rule.descriptions == ["my edited description"]
    assert not cat.enabled and cat.is_deleted


def test_concurrent_sessions_initialize_once(face_sqlite_session):
    db = face_sqlite_session
    owner, _ = add_owner(db)
    owner_id = owner.id
    db.commit()
    sessions = sessionmaker(bind=db.bind, autoflush=False)
    barrier = threading.Barrier(4)

    def initialize():
        with sessions() as session:
            barrier.wait(timeout=5)
            created = svc.ensure_presets(session, owner_id)
            session.commit()
            return created

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: initialize(), range(4)))
    count = len(svc.load_catalog()["categories"])
    assert sum(results) == 1
    assert db.query(ClipCategory).count() == count
    assert db.query(PhotoTag).count() == count
    assert db.query(ClipRuleRevision).count() == count


def test_concurrent_vector_generation_reuses_one_fill(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    url = str(uuid4())

    def encode(*args, **kwargs):
        calls.append(kwargs["json"])
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(raise_for_status=lambda: None,
                               headers={"X-Embedding-Model": "test"},
                               json=lambda: [[1.0, 0.0]])

    monkeypatch.setattr(svc.requests, "post", encode)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(svc.category_vector, url, "test", ["one"]) for _ in range(4)]
        assert entered.wait(3)
        release.set()
        vectors = [future.result(timeout=5) for future in futures]
    assert len(calls) == 1
    assert all(np.allclose(vector, [1, 0]) for vector in vectors)
    assert (url, "test") not in svc._vector_locks


def test_failed_vector_fill_releases_lock_and_can_resume(monkeypatch):
    url = str(uuid4())

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError()

    monkeypatch.setattr(svc.requests, "post", unavailable)
    with pytest.raises(RuntimeError, match="等待 AI 模型"):
        svc.category_vector(url, "test", ["one"])
    assert (url, "test") not in svc._vector_locks
    monkeypatch.setattr(svc.requests, "post", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, headers={"X-Embedding-Model": "test"}, json=lambda: [[1, 0]]))
    assert np.allclose(svc.category_vector(url, "test", ["one"]), [1, 0])


def test_upgrade_queue_is_idempotent_and_lazy(face_sqlite_session):
    db = face_sqlite_session
    owner, photo = add_owner(db)
    other = User(username=str(uuid4()))
    db.add(other)
    db.flush()
    db.add(Photo(owner_id=other.id, filename="video.mp4", file_path="video.mp4", file_type=FileType.video))
    db.commit()
    queue_clip_classification(db.connection())
    queue_clip_classification(db.connection())
    db.commit()
    task = db.query(Task).one()
    assert task.owner_id == owner.id
    assert task.payload["wait_for_embeddings"]
    assert db.query(ClipCategory).count() == 0
    task.status = TaskStatus.COMPLETED
    db.commit()
    queue_clip_classification(db.connection())
    remove_clip_classification(db.connection())
    db.commit()
    assert db.query(Task).one().status == TaskStatus.COMPLETED


def test_upgrade_waits_for_legacy_rebuild_and_merges_photo_job(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, photo = add_owner(db)
    legacy = Task(type=TaskType.IMAGE_EMBEDDING, payload={"force": True, "model": "test"})
    db.add(legacy)
    db.commit()
    queue_clip_classification(db.connection())
    db.commit()
    root = db.query(Task).filter_by(type=TaskType.CLASSIFY_IMAGE_CLIP).one()
    strategy = ClipClassificationStrategy()
    with pytest.raises(RuntimeError, match="图片特征重建"):
        asyncio.run(strategy.process(None, root, db))
    assert db.query(ClipCategory).count() == 0
    legacy.status = TaskStatus.COMPLETED
    db.commit()
    photo_task = svc.enqueue_photo(db, photo)
    db.commit()
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *a: "test")
    result = asyncio.run(strategy.process(None, root, db))
    assert result == {"generated_tasks": 0, "photos_checked": 1}
    assert db.query(Task).filter(Task.photo_id == photo.id).one().id == photo_task.id
    assert photo_task.payload["model"] == "test"


@pytest.mark.parametrize("task_type", [TaskType.IMAGE_EMBEDDING, TaskType.CLASSIFY_IMAGE_CLIP])
def test_unavailable_ai_waits_then_ready_resumes(monkeypatch, task_type):
    monkeypatch.setattr(state, "_cache", {})
    monkeypatch.setattr(state, "_refreshing", {})

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError()

    monkeypatch.setattr(state.requests, "get", unavailable)
    assert "暂不可达" in state.get_model_wait_reason("http://lazy-ai", task_type)
    state.invalidate_model_state("http://lazy-ai")
    monkeypatch.setattr(state.requests, "get", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {
            "tasks": {"embedding": {"selected": "test"}},
            "models": [{"id": "test", "status": "ready"}]}))
    assert state.get_model_wait_reason("http://lazy-ai", task_type) is None


@pytest.mark.parametrize("status", [409, 502, 503, 504])
def test_transient_text_service_errors_are_model_waits(monkeypatch, status):
    response = requests.Response()
    response.status_code = status
    response.url = "http://lazy-ai/embedding/text"
    monkeypatch.setattr(svc.requests, "post", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="等待 AI 模型"):
        svc.category_vector(str(uuid4()), "test", ["one"])


def test_first_classification_batch_uses_all_presets(face_sqlite_session, monkeypatch):
    from app.db.models.image_vector import ImageVector
    from app.db.models.tag import PhotoTagRelation

    db = face_sqlite_session
    owner, photo = add_owner(db)
    vector = [1.0] + [0.0] * 511
    db.add(ImageVector(photo_id=photo.id, model_name="test", embedding=vector))
    task = svc.enqueue_photo(db, photo)
    db.commit()
    monkeypatch.setattr(svc, "ai_url", lambda *a: "http://lazy-ai")
    monkeypatch.setattr(svc, "category_vectors", lambda url, model, groups: [vector] * len(groups))
    results = asyncio.run(ClipClassificationStrategy().process_batch(None, [task], db))
    count = len(svc.load_catalog()["categories"])
    assert results[0]["result"]["rules_checked"] == count
    assert db.query(PhotoTagRelation).filter_by(photo_id=photo.id).count() == count


def test_model_wait_does_not_consume_retry_budget(face_sqlite_session, monkeypatch):
    from app.service.task_worker import TaskWorker

    db = face_sqlite_session
    owner, _ = add_owner(db)
    task = Task(owner_id=owner.id, type=TaskType.CLASSIFY_IMAGE_CLIP,
                status=TaskStatus.PROCESSING, attempt_count=2, payload={})
    db.add(task)
    db.commit()
    worker = TaskWorker()
    monkeypatch.setattr(worker, "_publish_task_row", lambda *a: None)
    assert worker._schedule_retry(db, task, "等待 AI 模型：AI 服务暂不可达", 3)
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 2 and task.next_retry_at is not None
