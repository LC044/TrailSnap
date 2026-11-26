"""Nightly watch 2026-11-26 · app/service/cleanup_scan.py 的「范围冻结 / 参考集」盲区。

清理扫描在受理时会把待处理总体**冻结**下来（``snapshot_upper``），并在
``compare_all=True`` 时额外冻结一份**参考总体**（``reference_upper``）：

- 参考总体只用于比对，永远不会成为清理目标（``in_scope=False``）；
- 目录范围必须在受理阶段就校验归属，越权目录必须当场拒绝；
- 断点续扫不能重复写入同一张照片。

这几条分支此前没有被独立断言过，本文件补齐。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  注册全部 ORM 模型
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task
from app.db.models.toolbox import CleanupScope, ToolboxPlan
from app.db.models.user import User
from app.schemas.toolbox import MediaScope, PlanRequest, ToolConfig
from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]

SCOPE_PHOTO_ID = UUID("00000000-0000-0000-0000-000000000001")
REFERENCE_PHOTO_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def scan_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cleanup-scope.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def owner(scan_db):
    user = User(id=uuid4(), username="cleanup-scope-nightly", hashed_password="unused", settings={})
    scan_db.add(user)
    scan_db.commit()
    return user


def add_photo(db, owner, photo_id, *, file_type=FileType.image, deleted=False, name=None):
    name = name or f"photo-{photo_id}.jpg"
    photo = Photo(id=photo_id, owner_id=owner.id, filename=name, file_path=f"/tmp/{name}",
                  file_type=file_type, size=3, is_deleted=deleted, photo_time=datetime(2024, 1, 1))
    db.add(photo)
    db.commit()
    return photo


def plan_request(*, source="all", compare_all=False, folders=None):
    scope = MediaScope(source=source, folders=folders or [], media_type="image")
    config = ToolConfig(kind="cleanup", compare_all=compare_all)
    return PlanRequest(scope=scope, config=config)


def test_enqueue_scan_rejects_a_folder_outside_the_owned_roots(scan_db, owner):
    request = plan_request(source="folders", folders=["C:/Windows/System32/drivers/etc"])

    with pytest.raises(ValueError) as error:
        cleanup_scan.enqueue_scan(scan_db, owner, request)

    assert "不属于当前用户" in str(error.value)
    assert scan_db.query(ToolboxPlan).count() == 0


def test_enqueue_scan_freezes_the_upper_bounds_and_queues_a_task(scan_db, owner):
    add_photo(scan_db, owner, REFERENCE_PHOTO_ID)
    add_photo(scan_db, owner, SCOPE_PHOTO_ID)

    plan = cleanup_scan.enqueue_scan(scan_db, owner, plan_request())

    assert plan.status == "scan_queued"
    assert plan.summary["phase"] == "snapshot"
    assert plan.summary["snapshot_upper"] == str(REFERENCE_PHOTO_ID)
    assert plan.summary["reference_upper"] == str(REFERENCE_PHOTO_ID)
    task = scan_db.get(Task, plan.task_id)
    assert task.status == "pending"
    assert task.payload["cleanup_scan_id"] == str(plan.id)


def test_snapshot_keeps_the_compare_all_reference_out_of_scope(scan_db, owner):
    add_photo(scan_db, owner, SCOPE_PHOTO_ID)
    add_photo(scan_db, owner, REFERENCE_PHOTO_ID)
    plan = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="scan_queued", version=1,
                       request={}, summary={"total": 0, "processed": 0, "phase": "snapshot",
                                            "snapshot_upper": str(SCOPE_PHOTO_ID),
                                            "reference_upper": str(REFERENCE_PHOTO_ID)},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    scan_db.add(plan)
    scan_db.commit()

    cleanup_scan.snapshot(scan_db, plan, owner, plan_request(compare_all=True))

    rows = {row.photo_id: row.in_scope for row in
            scan_db.query(CleanupScope).filter_by(plan_id=plan.id).all()}
    assert rows == {SCOPE_PHOTO_ID: True, REFERENCE_PHOTO_ID: False}
    assert plan.summary["total"] == 1
    assert plan.summary["phase"] == "hash"


def test_snapshot_does_not_duplicate_rows_when_it_resumes(scan_db, owner):
    add_photo(scan_db, owner, SCOPE_PHOTO_ID)
    plan = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="scan_queued", version=1,
                       request={}, summary={"total": 0, "processed": 0, "phase": "snapshot",
                                            "snapshot_upper": str(SCOPE_PHOTO_ID)},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    scan_db.add(plan)
    scan_db.commit()

    cleanup_scan.snapshot(scan_db, plan, owner, plan_request())
    cleanup_scan.snapshot(scan_db, plan, owner, plan_request())

    assert scan_db.query(CleanupScope).filter_by(plan_id=plan.id).count() == 1
