"""Nightly watch 2026-11-26 · app/service/tasks/photo_generator.py 的边界盲区。

定向覆盖显示 ``generate_photo_tasks`` 只差两个分支：
``batch_size <= 0`` 的入参校验、以及预算耗尽后提前结束的 ``break``。
既有测试（``test_server_refactor_contracts.py``）只覆盖了正常分页路径。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import FileType, Photo
from app.db.models.task import TaskType
from app.service.tasks.photo_generator import generate_photo_tasks


def _photo(db, owner, name, *, deleted=False, file_type=FileType.image, processed=None):
    photo = Photo(
        id=uuid4(), owner_id=owner, filename=name, file_path=f"/isolated/{name}",
        file_type=file_type, size=1, is_deleted=deleted, processed_tasks=processed,
    )
    db.add(photo)
    return photo


def test_a_non_positive_batch_size_is_rejected(face_sqlite_session):
    with pytest.raises(ValueError, match="batch_size"):
        generate_photo_tasks(
            face_sqlite_session, SimpleNamespace(add_tasks=lambda *_: None),
            SimpleNamespace(owner_id=None, payload={}),
            task_type=TaskType.OCR, status_key="ocr", priority=1, batch_size=0,
        )


def test_a_non_positive_budget_generates_nothing(face_sqlite_session):
    entries = []

    generated = generate_photo_tasks(
        face_sqlite_session, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)),
        SimpleNamespace(owner_id=None, payload={"force": True}),
        task_type=TaskType.OCR, status_key="ocr", priority=1, budget=-1,
    )

    assert generated == 0
    assert entries == []


def test_the_budget_stops_the_expansion_once_it_is_used_up(face_sqlite_session):
    owner = uuid4()
    for index in range(5):
        _photo(face_sqlite_session, owner, f"budget-{index}.jpg")
    face_sqlite_session.commit()
    entries = []

    generated = generate_photo_tasks(
        face_sqlite_session, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)),
        SimpleNamespace(owner_id=owner, payload={"force": True}),
        task_type=TaskType.OCR, status_key="ocr", priority=1, budget=2, batch_size=10,
    )

    assert generated == 2
    assert len(entries) == 2


def test_a_task_without_an_owner_sees_every_photo(face_sqlite_session):
    owner = uuid4()
    photo = _photo(face_sqlite_session, owner, "no-owner.jpg")
    face_sqlite_session.commit()
    entries = []

    generated = generate_photo_tasks(
        face_sqlite_session, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)),
        SimpleNamespace(owner_id=None, payload={"force": True}),
        task_type=TaskType.OCR, status_key="ocr", priority=1,
    )

    assert generated == 1
    assert entries[0]["payload"]["photo_id"] == str(photo.id)


def test_an_eligible_filter_can_reject_every_photo(face_sqlite_session):
    owner = uuid4()
    _photo(face_sqlite_session, owner, "filtered.jpg")
    face_sqlite_session.commit()
    entries = []

    generated = generate_photo_tasks(
        face_sqlite_session, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)),
        SimpleNamespace(owner_id=owner, payload={"force": True}),
        task_type=TaskType.OCR, status_key="ocr", priority=1, eligible=lambda _photo: False,
    )

    assert generated == 0
    assert entries == []

