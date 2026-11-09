"""Nightly watch 2026-11-09 (round 2): OCR task strategy gaps.

Targets uncovered branches in ``app/service/tasks/ocr.py`` reported by the
2026-11-09 coverage snapshot:

* ``OcrStrategy.process`` - the single-photo admission guards: unknown photo,
  a photo whose OCR flag is already set (and the ``force`` override), and the
  CI task budget that stops the pipeline from flooding the AI service.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task, TaskType
from app.db.models.user import User
from app.service.tasks import ocr as ocr_module

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner(db):
    owner_id = uuid4()
    db.add(User(id=owner_id, username="nightly-ocr-owner", hashed_password="x"))
    db.commit()
    return owner_id


def _photo(db, owner_id, processed_tasks=None):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename="p.jpg",
        file_path="p.jpg",
        file_type=FileType.image,
        processed_tasks=processed_tasks or {},
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    return photo


def _task(photo_id, force=False):
    return Task(
        id=uuid4(),
        type=TaskType.OCR,
        payload={"photo_id": str(photo_id), "force": force},
    )


def _run(coro):
    return asyncio.run(coro)


def test_process_skips_when_photo_is_missing(db):
    strategy = ocr_module.OcrStrategy()
    result = _run(strategy.process(None, _task(uuid4()), db))
    assert result == {"status": "skipped", "reason": "photo not found"}


def test_process_skips_a_photo_that_was_already_ocr_processed(db, owner):
    photo = _photo(db, owner, processed_tasks={"ocr": True})
    strategy = ocr_module.OcrStrategy()
    result = _run(strategy.process(None, _task(photo.id), db))
    assert result == {"status": "skipped", "reason": "already processed"}


def test_process_forwards_to_the_single_photo_handler_when_forced(db, owner):
    photo = _photo(db, owner, processed_tasks={"ocr": True})
    strategy = ocr_module.OcrStrategy()
    expected = {"status": "success", "texts_found": 3}

    with patch.object(ocr_module.OcrStrategy, "process_single_photo", return_value=expected) as handler:
        result = _run(strategy.process(None, _task(photo.id, force=True), db))

    assert result == expected
    assert handler.called


def test_process_stops_when_the_ci_task_budget_is_exhausted(db, owner):
    photo = _photo(db, owner)
    strategy = ocr_module.OcrStrategy()

    with patch.object(ocr_module, "ci_task_limit_reached", return_value=True):
        result = _run(strategy.process(None, _task(photo.id), db))

    assert result["status"] == "skipped"
    assert "CI ocr limit reached" in result["reason"]
    assert str(ocr_module.CI_TASK_PHOTO_LIMIT) in result["reason"]
