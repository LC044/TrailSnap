"""Nightly watch 2026-11-22 · app/service/cleanup_execution.py::start_cleanup 盲区。

start_cleanup 是「清理计划」从预览进入执行的闸门：它校验人工勾选、把候选项
置为 ready/skipped、创建后台任务并把计划置为 queued。

覆盖：
- 勾选为空 -> ValueError（error）
- 没有既有勾选且没有传 selected_items -> ValueError（error）
- 合法勾选 -> 计划进入 queued、任务被创建、未勾选候选被跳过（happy）
- 重复清理但重复组没有保留项 -> ValueError（error）
- 重复清理且存在保留项 -> 放行（happy）
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import Photo
from app.db.models.task import Task
from app.db.models.toolbox import (CleanupGroup, CleanupMember, CleanupSelection,
                                  ToolboxPlan, ToolboxPlanItem)
from app.service.cleanup_execution import start_cleanup

pytestmark = [pytest.mark.smoke]


def _plan(db, owner_id, mode="unused"):
    plan = ToolboxPlan(
        id=uuid4(), owner_id=owner_id, kind="cleanup", status="preview", version=1,
        request={"config": {"cleanup_mode": mode}}, summary={},
        expires_at=datetime.utcnow() + timedelta(days=1))
    db.add(plan)
    db.flush()
    return plan


def _item(db, plan, status="candidate"):
    item = ToolboxPlanItem(
        plan_id=plan.id, photo_id=uuid4(), source="/tmp/a.jpg", target="",
        status=status, reason="", fingerprint={}, detail={})
    db.add(item)
    db.flush()
    return item


def _request(selected_items):
    return SimpleNamespace(selected_items=selected_items)


def test_start_cleanup_rejects_an_empty_selection(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    plan = _plan(db, owner)
    _item(db, plan)

    with pytest.raises(ValueError):
        start_cleanup(db, SimpleNamespace(id=owner), plan, _request([]))


def test_start_cleanup_requires_an_existing_selection(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    plan = _plan(db, owner)
    _item(db, plan)

    with pytest.raises(ValueError):
        start_cleanup(db, SimpleNamespace(id=owner), plan, _request(None))


def test_start_cleanup_queues_the_plan_and_creates_a_task(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    plan = _plan(db, owner)
    selected = _item(db, plan)
    skipped = _item(db, plan)

    result = start_cleanup(db, SimpleNamespace(id=owner), plan, _request([selected.id]))

    assert result.status == "queued"
    assert result.task_id is not None
    assert db.get(Task, result.task_id) is not None
    db.refresh(selected)
    db.refresh(skipped)
    assert selected.status == "ready"
    assert skipped.status == "skipped"
    assert db.query(CleanupSelection).filter_by(plan_id=plan.id).count() == 1


def _duplicate_group(db, plan, item, key):
    group = CleanupGroup(plan_id=plan.id, representative_id=item.photo_id, key=key, count=1)
    db.add(group)
    db.flush()
    db.add(CleanupMember(plan_id=plan.id, photo_id=item.photo_id,
                         group_id=group.id, in_scope=True))
    db.flush()
    return group


def test_start_cleanup_rejects_a_duplicate_group_without_a_keeper(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    plan = _plan(db, owner, mode="duplicate")
    item = _item(db, plan, status="ready")
    db.add(CleanupSelection(plan_id=plan.id, item_id=item.id))
    db.flush()
    _duplicate_group(db, plan, item, "dup-md5")

    with pytest.raises(ValueError):
        start_cleanup(db, SimpleNamespace(id=owner), plan, _request(None))


def test_start_cleanup_accepts_a_duplicate_group_with_a_keeper(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    plan = _plan(db, owner, mode="duplicate")
    item = _item(db, plan, status="ready")
    db.add(CleanupSelection(plan_id=plan.id, item_id=item.id))
    db.flush()
    _duplicate_group(db, plan, item, "dup-md5")
    # 重复组的保留项不在待删除集合里
    db.add(Photo(id=uuid4(), filename="keep.jpg", file_path="keep.jpg", owner_id=owner,
                 file_type="image", md5="dup-md5"))
    db.flush()

    result = start_cleanup(db, SimpleNamespace(id=owner), plan, _request(None))

    assert result.status == "queued"
