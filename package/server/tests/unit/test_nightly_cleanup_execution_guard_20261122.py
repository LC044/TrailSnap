"""Nightly watch 2026-11-22: ``app/service/cleanup_execution.py``::execute_cleanup 盲区。

执行清理时，每一条候选都会在真正删除前做一次「原文件是否还是扫描时那份」的复核：
路径变了、照片没了都会被标记为 failed 并写明原因，而不是被静默删除。
任务本身也可以被用户中途叫停（stop_requested）。

本文件覆盖：
- 照片已不存在 -> 该候选失败并写明原因，计划状态为 partial（edge）
- 原文件路径已变化 -> 同样失败并提示重新扫描（edge）
- 用户叫停 -> 立即结束，计划状态为 stopped，不处理任何候选（edge）
- 失败计数正确汇总进 summary（happy）
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
from app.db.models.user import User
from app.service import cleanup_execution


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
    user = User(id=uuid4(), username="nightly-cleanup-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def plan(db, owner):
    row = ToolboxPlan(
        id=uuid4(), owner_id=owner.id, kind="cleanup", status="queued", version=1,
        request={"config": {"cleanup_mode": "duplicate"}}, summary={},
        stop_requested=False, expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def task(db, owner):
    row = Task(id=uuid4(), owner_id=owner.id, type="organize_photos", status="running",
               priority=10000, total_items=1, processed_items=0, payload={})
    db.add(row)
    db.commit()
    return row


def _item(db, plan, photo_id, source="/isolated/original.jpg", fingerprint=None):
    item = ToolboxPlanItem(plan_id=plan.id, photo_id=photo_id, source=source, target="",
                           status="ready", reason="", fingerprint=fingerprint or {},
                           detail={"md5": "0" * 32})
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.mark.asyncio
async def test_missing_photo_marks_the_candidate_as_failed(db, owner, plan, task):
    item = _item(db, plan, uuid4())

    result = await cleanup_execution.execute_cleanup(task, db, plan)
    db.refresh(item)

    assert item.status == "failed"
    assert "重新扫描" in item.reason
    assert result == {"status": "completed", "success_count": 0, "failed_count": 1}
    assert plan.status == "partial"
    assert plan.summary["failed"] == 1


@pytest.mark.asyncio
async def test_changed_source_path_marks_the_candidate_as_failed(db, owner, plan, task, tmp_path):
    photo = Photo(id=uuid4(), owner_id=owner.id, filename="photo.jpg",
                  file_path=str(tmp_path / "moved.jpg"), file_type=FileType.image, size=10)
    db.add(photo)
    db.commit()
    item = _item(db, plan, photo.id, source=str(tmp_path / "original.jpg"))

    result = await cleanup_execution.execute_cleanup(task, db, plan)
    db.refresh(item)

    assert item.status == "failed"
    assert "重新扫描" in item.reason
    assert result["failed_count"] == 1


@pytest.mark.asyncio
async def test_stop_requested_ends_the_run_without_touching_candidates(db, owner, plan, task):
    item = _item(db, plan, uuid4())
    plan.stop_requested = True
    db.commit()

    result = await cleanup_execution.execute_cleanup(task, db, plan)
    db.refresh(item)

    assert item.status == "ready"
    assert plan.status == "stopped"
    assert result == {"status": "completed", "success_count": 0, "failed_count": 0}
    assert plan.summary["running"] == 0
