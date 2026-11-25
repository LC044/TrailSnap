"""Nightly watch 2026-11-23 - app/service/task_worker.py 的 _flush_results_db 盲区。

任务结果落库是"至多一次"语义的关卡：DB 提交成功但回执丢失时，worker 会
重放同一批结果。此时已经 COMPLETED / CANCELLED 的行必须被过滤掉，否则会
重复触发下游任务、重复累加计数。

本文件用真实 SQLite 会话覆盖：

- 正常完成的任务行被删除并发出 task.updated 事件（happy）
- 保留类型的任务行（DISCOVER_CHAPTERS）不删除，只更新状态（edge）
- 失败的任务行被写成 failed 并带上错误信息（error）
- 已经是 completed 的行被过滤，不重复发事件（edge，重放幂等）
- 已经是 cancelled 的行同样被过滤（edge）
"""

from uuid import uuid4

import pytest

from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service import task_worker as worker_module
from app.service.task_worker import TaskWorker

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def worker_db(tmp_path, monkeypatch):
    """真实 SQLite 会话；把 worker 内部的 SessionLocal 换成测试会话工厂。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'worker.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _owner(db):
    user = User(id=uuid4(), username="owner-" + uuid4().hex[:8], hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _task(db, owner, task_type):
    task = Task(id=uuid4(), type=task_type.value, status=TaskStatus.PROCESSING.value,
                owner_id=owner.id, priority=1)
    db.add(task)
    db.flush()
    return task


def _item(task, status, **extra):
    item = {"task_id": task.id, "task_type": TaskType(task.type), "status": status,
            "result": extra.get("result", {}), "error": extra.get("error")}
    return item


def _events_by_id(events):
    return {data["id"]: data for name, data in events if name == "task.updated"}


@pytest.mark.asyncio
async def test_completed_task_row_is_deleted_and_an_event_is_emitted(worker_db):
    db = worker_db
    owner = _owner(db)
    task = _task(db, owner, TaskType.OCR)
    task_id = task.id
    db.commit()
    worker = TaskWorker()

    _, events = await worker._flush_results_db([_item(task, TaskStatus.COMPLETED)])

    db.expire_all()
    remaining = db.query(Task).filter(Task.id == task_id).count()
    assert remaining == 0
    emitted = _events_by_id(events)
    assert emitted[str(task_id)]["status"] == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
@pytest.mark.parametrize('task_type', [TaskType.DISCOVER_CHAPTERS, TaskType.REMOVE_GALLERY])
async def test_preserved_task_type_keeps_its_row(worker_db, task_type):
    db = worker_db
    owner = _owner(db)
    task = _task(db, owner, task_type)
    db.commit()
    worker = TaskWorker()

    _, events = await worker._flush_results_db(
        [_item(task, TaskStatus.COMPLETED, result={"chapters": 2})]
    )

    db.expire_all()
    row = db.get(Task, task.id)
    assert row is not None
    assert row.status == TaskStatus.COMPLETED.value
    assert row.result == {"chapters": 2}
    assert str(task.id) in _events_by_id(events)


@pytest.mark.asyncio
async def test_failed_item_marks_the_row_as_failed(worker_db):
    db = worker_db
    owner = _owner(db)
    task = _task(db, owner, TaskType.OCR)
    db.commit()
    worker = TaskWorker()

    _, events = await worker._flush_results_db(
        [_item(task, TaskStatus.FAILED, error="boom")]
    )

    db.expire_all()
    row = db.get(Task, task.id)
    assert row is not None
    assert row.status == TaskStatus.FAILED.value
    assert row.error == "boom"
    emitted = _events_by_id(events)
    assert emitted[str(task.id)]["status"] == TaskStatus.FAILED.value


@pytest.mark.asyncio
async def test_replaying_a_completed_task_is_ignored(worker_db):
    db = worker_db
    owner = _owner(db)
    task = _task(db, owner, TaskType.OCR)
    task.status = TaskStatus.COMPLETED.value
    db.commit()
    worker = TaskWorker()

    _, events = await worker._flush_results_db([_item(task, TaskStatus.COMPLETED)])

    assert events == []
    db.expire_all()
    assert db.get(Task, task.id) is not None


@pytest.mark.asyncio
async def test_replaying_a_cancelled_task_is_ignored(worker_db):
    db = worker_db
    owner = _owner(db)
    task = _task(db, owner, TaskType.OCR)
    task.status = TaskStatus.CANCELLED.value
    db.commit()
    worker = TaskWorker()

    _, events = await worker._flush_results_db([_item(task, TaskStatus.COMPLETED)])

    assert events == []
    db.expire_all()
    row = db.get(Task, task.id)
    assert row is not None
    assert row.status == TaskStatus.CANCELLED.value
