"""Nightly watch 2026-11-23 · app/service/cleanup_scan.py 的 similar_groups 盲区。

similar_groups 负责按向量模型对清理范围内照片做「相似照片」分组。当范围内
还没有任何向量索引时，这条路径必须把缺口记进 summary，而不是静默成功。

覆盖：
- 范围内没有向量模型时记录 missing_vectors（happy）
- 范围外的照片不计入缺口数量（edge）
- 范围为空时缺口为 0（edge）
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import FileType, Photo
from app.db.models.toolbox import CleanupScope, ToolboxPlan
from app.db.models.user import User
from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke]


def _plan(db, owner):
    plan = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="running",
                       version=1, request={"source": "library"},
                       summary={}, expires_at=datetime.utcnow() + timedelta(days=1))
    db.add(plan)
    db.flush()
    return plan


def _scoped_photo(db, owner, plan, filename="a.jpg"):
    photo = Photo(id=uuid4(), filename=filename, file_path=filename, file_type=FileType.image,
                  owner_id=owner.id, width=10, height=10)
    db.add(photo)
    db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=True))
    db.flush()
    return photo


def _config(scan_mode="fast"):
    return SimpleNamespace(scan_mode=scan_mode, similarity=0.9)


def test_similar_groups_records_missing_vectors_when_nothing_is_indexed(face_sqlite_session):
    owner = User(id=uuid4(), username=f"owner-{uuid4().hex[:8]}", hashed_password="x")
    face_sqlite_session.add(owner)
    face_sqlite_session.flush()
    plan = _plan(face_sqlite_session, owner)
    _scoped_photo(face_sqlite_session, owner, plan, "one.jpg")
    _scoped_photo(face_sqlite_session, owner, plan, "two.jpg")

    cleanup_scan.similar_groups(face_sqlite_session, plan, _config())

    assert plan.summary["missing_vectors"] == 2


def test_similar_groups_ignores_photos_outside_the_frozen_scope(face_sqlite_session):
    owner = User(id=uuid4(), username=f"owner-{uuid4().hex[:8]}", hashed_password="x")
    face_sqlite_session.add(owner)
    face_sqlite_session.flush()
    plan = _plan(face_sqlite_session, owner)
    _scoped_photo(face_sqlite_session, owner, plan, "in-scope.jpg")
    outside = Photo(id=uuid4(), filename="outside.jpg", file_path="outside.jpg",
                    file_type=FileType.image, owner_id=owner.id, width=10, height=10)
    face_sqlite_session.add(outside)
    face_sqlite_session.flush()

    cleanup_scan.similar_groups(face_sqlite_session, plan, _config())

    assert plan.summary["missing_vectors"] == 1


def test_similar_groups_reports_no_gap_for_an_empty_scope(face_sqlite_session):
    owner = User(id=uuid4(), username=f"owner-{uuid4().hex[:8]}", hashed_password="x")
    face_sqlite_session.add(owner)
    face_sqlite_session.flush()
    plan = _plan(face_sqlite_session, owner)

    cleanup_scan.similar_groups(face_sqlite_session, plan, _config("complete"))

    assert plan.summary["missing_vectors"] == 0
