"""覆盖 app/service/cleanup_scan.py 中此前没有测试引用的三个函数。

盲区来源：函数级静态引用扫描命中 population / hash_population / add_group
——它们是清理扫描的核心路径（冻结范围 -> 哈希 -> 分组），但既有测试
（test_cleanup_scan.py）只走 run_scan 的整体流程，从未直接引用这三个
函数，因此它们的独立行为（范围过滤、哈希缓存复用、失败不写 md5、
单例不建组）从未被断言。

全部使用独立 SQLite 库，不触碰用户数据。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  注册全部 ORM 模型
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.toolbox import (CleanupGroup, CleanupHash, CleanupMember,
                                   CleanupScope, ToolboxPlan)
from app.db.models.user import User
from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def cleanup_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cleanup.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def owner(cleanup_db):
    user = User(id=uuid4(), username="cleanup-nightly", hashed_password="unused", settings={})
    cleanup_db.add(user)
    cleanup_db.commit()
    return user


@pytest.fixture
def plan(cleanup_db, owner):
    item = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="scan_queued",
                       version=1, request={}, summary={},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    cleanup_db.add(item)
    cleanup_db.commit()
    return item


@pytest.fixture
def owner(cleanup_db):
    user = User(id=uuid4(), username="cleanup-nightly", hashed_password="unused", settings={})
    cleanup_db.add(user)
    cleanup_db.commit()
    return user


@pytest.fixture
def plan(cleanup_db, owner):
    item = ToolboxPlan(id=uuid4(), owner_id=owner.id, kind="cleanup", status="scan_queued",
                       version=1, request={}, summary={},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    cleanup_db.add(item)
    cleanup_db.commit()
    return item


@pytest.fixture
def make_photo(tmp_path, cleanup_db, owner, plan):
    counter = {"n": 0}

    def build(*, content=b"payload", in_scope=True, deleted=False,
              file_type=FileType.image, scope=True, name=None, other_owner=False):
        counter["n"] += 1
        filename = name or f"photo-{counter['n']}.jpg"
        path = tmp_path / filename
        path.write_bytes(content)
        photo_owner = owner
        if other_owner:
            photo_owner = User(id=uuid4(), username=f"other-{counter['n']}",
                               hashed_password="unused", settings={})
            cleanup_db.add(photo_owner)
        photo = Photo(id=uuid4(), owner_id=photo_owner.id, filename=filename,
                      file_path=str(path), file_type=file_type, size=len(content),
                      is_deleted=deleted, photo_time=datetime(2024, 1, 1))
        cleanup_db.add(photo)
        cleanup_db.flush()
        if scope:
            cleanup_db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=in_scope))
        cleanup_db.commit()
        return photo

    return build


# --------------------------------------------------------------------------- #
# population
# --------------------------------------------------------------------------- #

def test_population_returns_only_scoped_live_images(cleanup_db, plan, owner, make_photo):
    inside = make_photo()
    # 参考照片（in_scope=False）同样属于被冻结的总体，只是不能被选中删除。
    reference = make_photo(in_scope=False)
    make_photo(deleted=True)
    make_photo(file_type=FileType.video)
    make_photo(other_owner=True)

    found = {photo.id for photo in cleanup_scan.population(cleanup_db, plan)}
    assert found == {inside.id, reference.id}


def test_population_is_empty_without_scope_rows(cleanup_db, plan, make_photo):
    make_photo(scope=False)
    assert list(cleanup_scan.population(cleanup_db, plan)) == []


# --------------------------------------------------------------------------- #
# hash_population
# --------------------------------------------------------------------------- #

def test_hash_population_writes_md5_and_hash_cache(cleanup_db, plan, make_photo):
    photo = make_photo(content=b"hello world")
    cleanup_scan.hash_population(cleanup_db, plan)

    cleanup_db.refresh(photo)
    assert photo.md5 == hashlib.md5(b"hello world").hexdigest()
    cached = cleanup_db.query(CleanupHash).filter(CleanupHash.photo_id == photo.id).one()
    assert cached.md5 == photo.md5
    assert int(cached.size) == len(b"hello world")
    assert len(cached.path_digest) == 64


def test_hash_population_reuses_valid_cache_entry(cleanup_db, plan, make_photo):
    photo = make_photo(content=b"cached bytes")
    cleanup_scan.hash_population(cleanup_db, plan)
    cleanup_db.refresh(photo)
    first_md5 = photo.md5

    # 清掉游标以便重跑同一批照片，并抹掉 md5 让缓存命中路径可被区分。
    plan.summary = {key: value for key, value in plan.summary.items() if key != "hash_cursor"}
    photo.md5 = first_md5
    cleanup_db.commit()

    cleanup_scan.hash_population(cleanup_db, plan)
    # 计数器在 summary 上累加：首次真正计算过一次，本次走缓存复用。
    assert plan.summary["hash_reused"] == 1
    assert plan.summary["hashed"] == 1


def test_hash_population_clears_md5_when_file_is_unreadable(cleanup_db, plan, make_photo):
    photo = make_photo(content=b"vanishing")
    cleanup_scan.hash_population(cleanup_db, plan)
    cleanup_db.refresh(photo)
    assert photo.md5

    import os
    os.remove(photo.file_path)
    plan.summary = {key: value for key, value in plan.summary.items() if key != "hash_cursor"}
    cleanup_db.commit()

    cleanup_scan.hash_population(cleanup_db, plan)
    cleanup_db.refresh(photo)
    assert photo.md5 is None
    assert plan.summary["hash_failed"] == 1


def test_hash_population_finishes_with_groups_phase(cleanup_db, plan, make_photo):
    make_photo()
    cleanup_scan.hash_population(cleanup_db, plan)
    assert plan.summary["phase"] == "groups"


# --------------------------------------------------------------------------- #
# add_group
# --------------------------------------------------------------------------- #

def test_add_group_creates_group_and_members(cleanup_db, plan, make_photo):
    photos = [make_photo() for _ in range(3)]
    cleanup_scan.add_group(cleanup_db, plan, "dup-md5", photos[0].id,
                            (photo.id for photo in photos))
    cleanup_db.flush()

    group = cleanup_db.query(CleanupGroup).filter(CleanupGroup.plan_id == plan.id).one()
    assert group.key == "dup-md5"
    assert group.representative_id == photos[0].id
    assert group.count == 3
    members = cleanup_db.query(CleanupMember).filter(CleanupMember.plan_id == plan.id).all()
    assert {member.photo_id for member in members} == {photo.id for photo in photos}


def test_add_group_skips_singleton_representative(cleanup_db, plan, make_photo):
    only = make_photo()
    cleanup_scan.add_group(cleanup_db, plan, "lonely", only.id, (only.id,))
    cleanup_db.flush()
    assert cleanup_db.query(CleanupGroup).filter(CleanupGroup.plan_id == plan.id).count() == 0
    assert cleanup_db.query(CleanupMember).filter(CleanupMember.plan_id == plan.id).count() == 0


def test_add_group_marks_assigned_ids(cleanup_db, plan, make_photo):
    photos = [make_photo() for _ in range(2)]
    assigned = set()
    cleanup_scan.add_group(cleanup_db, plan, "dup-md5", photos[0].id,
                            (photo.id for photo in photos),
                            batch_ids=[photos[1].id], assigned=assigned)
    assert assigned == {photos[1].id}


def test_add_group_records_out_of_scope_members(cleanup_db, plan, make_photo):
    inside = make_photo(in_scope=True)
    outside = make_photo(in_scope=False)
    cleanup_scan.add_group(cleanup_db, plan, "dup-md5", inside.id,
                            (inside.id, outside.id))
    cleanup_db.flush()
    members = {member.photo_id: member.in_scope
               for member in cleanup_db.query(CleanupMember)
               .filter(CleanupMember.plan_id == plan.id).all()}
    assert members == {inside.id: True, outside.id: False}
