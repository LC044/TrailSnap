"""Nightly watch 2026-11-26 · app/service/cleanup_scan.py 的 quality 模式物化盲区。

低质量照片清理（``cleanup_mode="quality"``）与重复/相似清理走的是完全不同的
候选判定逻辑：重复/相似依赖 hash 分组得到的 ``CleanupMember``，而 quality 模式
直接在 ``materialize`` 里按 ``ImageDescription`` 的
``quality_score + memory_score`` 是否不超过 ``quality_max`` 决定是否成为候选。

这段判定此前没有独立断言过（既有用例只覆盖 duplicate / similar 分支），因此：

- 评分之和不超过阈值时，照片应成为 candidate，且明细里带上评分与标签；
- 评分之和超过阈值时，照片不应成为候选（但仍要计入 processed）；
- 没有评分记录（无 ImageDescription）的照片不产生候选；
- 物化结束后计划状态应为 preview，summary 记录 candidate / skipped 计数。

全部使用独立 SQLite 库，不触碰用户数据。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  注册全部 ORM 模型
from app.db.base import Base
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.toolbox import CleanupScope, ToolboxPlan, ToolboxPlanItem
from app.db.models.user import User
from app.schemas.toolbox import ToolConfig
from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def cleanup_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cleanup-quality.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def owner(cleanup_db):
    user = User(id=uuid4(), username="cleanup-quality-nightly", hashed_password="unused", settings={})
    cleanup_db.add(user)
    cleanup_db.commit()
    return user


@pytest.fixture
def plan(cleanup_db, owner):
    item = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="scanning",
                       version=1, request={}, summary={"total": 0, "processed": 0, "phase": "items"},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    cleanup_db.add(item)
    cleanup_db.commit()
    return item


@pytest.fixture
def make_photo(tmp_path, cleanup_db, owner, plan):
    counter = {"n": 0}

    def build(*, content=b"payload", in_scope=True, deleted=False, quality=None, memory=None,
              described=False):
        counter["n"] += 1
        filename = f"photo-{counter['n']}.jpg"
        path = tmp_path / filename
        path.write_bytes(content)
        photo = Photo(id=uuid4(), owner_id=owner.id, filename=filename, file_path=str(path),
                      file_type=FileType.image, size=len(content), is_deleted=deleted,
                      photo_time=datetime(2024, 1, 1))
        cleanup_db.add(photo)
        cleanup_db.flush()
        cleanup_db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=in_scope))
        if described:
            cleanup_db.add(ImageDescription(photo_id=photo.id, description="一张照片",
                                            quality_score=quality, memory_score=memory))
        cleanup_db.commit()
        return photo

    return build


def _config(**kwargs):
    return ToolConfig(kind="cleanup", cleanup_mode="quality", quality_max=40, **kwargs)


def test_materialize_promotes_a_low_scoring_photo_to_a_candidate(cleanup_db, plan, owner, make_photo):
    photo = make_photo(quality=12.5, memory=7.5, described=True)

    cleanup_scan.materialize(cleanup_db, plan, owner, _config())

    items = cleanup_db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).all()
    assert len(items) == 1
    item = items[0]
    assert item.photo_id == photo.id
    assert item.status == "candidate"
    assert item.detail["group"] == "quality"
    assert item.detail["label"] == "评分 20"
    assert item.detail["quality_score"] == 12.5
    assert item.detail["memory_score"] == 7.5
    assert plan.status == "preview"
    assert plan.summary["phase"] == "done"
    assert plan.summary["candidate"] == 1


def test_materialize_skips_a_photo_whose_score_is_above_the_threshold(cleanup_db, plan, owner, make_photo):
    make_photo(quality=60, memory=30, described=True)

    cleanup_scan.materialize(cleanup_db, plan, owner, _config())

    assert cleanup_db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).count() == 0
    assert plan.summary["candidate"] == 0
    assert plan.summary["processed"] == 1


def test_materialize_skips_a_photo_without_any_description(cleanup_db, plan, owner, make_photo):
    make_photo(described=False)

    cleanup_scan.materialize(cleanup_db, plan, owner, _config())

    assert cleanup_db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).count() == 0
    assert plan.summary["candidate"] == 0


def test_materialize_treats_a_missing_score_as_zero(cleanup_db, plan, owner, make_photo):
    photo = make_photo(quality=None, memory=None, described=True)

    cleanup_scan.materialize(cleanup_db, plan, owner, _config())

    items = cleanup_db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).all()
    assert len(items) == 1
    assert items[0].detail["label"] == "评分 0"
    assert items[0].detail["quality_score"] == 0
    assert items[0].detail["memory_score"] == 0
    assert photo.id == items[0].photo_id


def test_materialize_never_promotes_a_photo_outside_the_frozen_scope(cleanup_db, plan, owner, make_photo):
    make_photo(in_scope=False, quality=5, memory=5, described=True)

    cleanup_scan.materialize(cleanup_db, plan, owner, _config())

    assert cleanup_db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).count() == 0
