"""Nightly watch 2026-11-23 - app/service/tasks/face_cluster.py 的延迟重试盲区。

人脸聚类必须等识别任务跑完才有意义。ClusterFacesStrategy 用
_recognition_in_flight 判断当前 owner 是否还有识别任务在跑，
_defer 把聚类任务退回 pending 并推迟重试。

本文件用真实 SQLite（face_sqlite_session）覆盖：

- 存在 pending / processing 的识别任务时 _recognition_in_flight 为真（happy）
- 只有聚类任务或识别任务已完成时为假（edge）
- 其它 owner 的识别任务不影响判定（edge）
- _defer 把状态退回 pending、清空错误、推迟重试且保留 attempt_count（happy）
- _defer 会提交事务（happy）
"""

from datetime import datetime
from uuid import uuid4

import pytest

from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service.tasks.face_cluster import DEFER_SECONDS, ClusterFacesStrategy

pytestmark = [pytest.mark.smoke]


def _user(db):
    user = User(id=uuid4(), username="owner-" + uuid4().hex[:8], hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _task(db, owner, *, type_, status):
    task = Task(
        id=uuid4(),
        type=type_,
        status=status,
        owner_id=owner.id,
    )
    db.add(task)
    db.flush()
    return task


def test_recognition_in_flight_is_true_for_a_pending_recognition_task(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    _task(db, owner, type_=TaskType.RECOGNIZE_FACE.value, status=TaskStatus.PENDING.value)

    assert ClusterFacesStrategy._recognition_in_flight(db, owner.id) is True


def test_recognition_in_flight_is_true_for_a_processing_recognition_task(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    _task(db, owner, type_=TaskType.RECOGNIZE_FACE.value, status=TaskStatus.PROCESSING.value)

    assert ClusterFacesStrategy._recognition_in_flight(db, owner.id) is True


def test_recognition_in_flight_is_false_without_a_recognition_task(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    _task(db, owner, type_=TaskType.CLUSTER_FACES.value, status=TaskStatus.PENDING.value)

    assert ClusterFacesStrategy._recognition_in_flight(db, owner.id) is False


def test_recognition_in_flight_ignores_finished_recognition_tasks(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    _task(db, owner, type_=TaskType.RECOGNIZE_FACE.value, status=TaskStatus.COMPLETED.value)

    assert ClusterFacesStrategy._recognition_in_flight(db, owner.id) is False


def test_recognition_in_flight_ignores_other_owners(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    other = _user(db)
    _task(db, other, type_=TaskType.RECOGNIZE_FACE.value, status=TaskStatus.PENDING.value)

    assert ClusterFacesStrategy._recognition_in_flight(db, owner.id) is False


def test_defer_resets_the_task_to_pending(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    task = _task(db, owner, type_=TaskType.CLUSTER_FACES.value, status=TaskStatus.FAILED.value)
    task.error = "boom"
    task.attempt_count = 2
    db.commit()

    ClusterFacesStrategy._defer(db, task)
    db.refresh(task)

    assert task.status == TaskStatus.PENDING
    assert task.error is None
    assert task.attempt_count == 2


def test_defer_schedules_the_next_retry(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    task = _task(db, owner, type_=TaskType.CLUSTER_FACES.value, status=TaskStatus.PENDING.value)
    db.commit()

    ClusterFacesStrategy._defer(db, task)
    db.refresh(task)

    assert task.next_retry_at is not None
    remaining = task.next_retry_at.replace(tzinfo=None) - datetime.now()
    assert 0 < remaining.total_seconds() <= DEFER_SECONDS + 5
