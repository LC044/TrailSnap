"""Nightly watch 2026-11-26 · app/crud/scene.py 的「场景列表」盲区。

``get_scenes`` 是场景页的主查询：按 owner 过滤（自有 + 系统公共场景）、
统计每个场景的照片数量、挑出封面（最新一张），并支持日期区间过滤。
这条 SQL 比较复杂（多表 outer join + 窗口函数取封面），此前只有
``test_location_covers.py`` 覆盖了相近逻辑，边界分支没有断言：

- 空结果返回空列表（不会因为没有场景就去查封面）；
- 自有场景与系统场景同时出现；
- 其他用户的场景不出现；
- 封面取拍摄时间最新的那张；
- 日期区间只统计区间内的照片。

使用独立 SQLite，不触碰用户数据。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  注册全部 ORM 模型
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.user import User
from app.crud import scene as scene_crud

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def scene_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'scene-crud.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def users(scene_db):
    owner = User(id=uuid4(), username="scene-owner-nightly", hashed_password="unused", settings={})
    other = User(id=uuid4(), username="scene-other-nightly", hashed_password="unused", settings={})
    scene_db.add_all([owner, other])
    scene_db.commit()
    return owner, other


def add_scene(db, name, owner_id=None):
    scene = Scene(id=uuid4(), name=name, owner_id=owner_id)
    db.add(scene)
    db.flush()
    return scene


def add_photo(db, owner_id, scene, *, when, name="p.jpg", deleted=False):
    photo = Photo(id=uuid4(), owner_id=owner_id, filename=name, file_path=f"/tmp/{name}",
                  file_type=FileType.image, size=1, is_deleted=deleted, photo_time=when)
    db.add(photo)
    db.flush()
    db.add(PhotoMetadata(photo_id=photo.id, scene_id=scene.id))
    db.commit()
    return photo


def test_get_scenes_returns_an_empty_list_when_no_scene_exists(scene_db, users):
    owner, _ = users

    assert scene_crud.get_scenes(scene_db, owner_id=owner.id) == []


def test_get_scenes_lists_own_and_shared_scenes_but_not_other_owners(scene_db, users):
    owner, other = users
    own = add_scene(scene_db, "我的场景", owner.id)
    shared = add_scene(scene_db, "公共场景", None)
    add_scene(scene_db, "别人的场景", other.id)

    scenes = scene_crud.get_scenes(scene_db, owner_id=owner.id)

    names = {scene.name for scene in scenes}
    assert names == {"我的场景", "公共场景"}


def test_get_scenes_counts_photos_and_picks_the_latest_one_as_cover(scene_db, users):
    owner, _ = users
    scene = add_scene(scene_db, "海边", owner.id)
    add_photo(scene_db, owner.id, scene, when=datetime(2024, 5, 1, 9, 0), name="old.jpg")
    newest = add_photo(scene_db, owner.id, scene, when=datetime(2024, 6, 1, 9, 0), name="new.jpg")

    scenes = scene_crud.get_scenes(scene_db, owner_id=owner.id)

    assert len(scenes) == 1
    assert scenes[0].photo_count == 2
    assert scenes[0].cover.id == newest.id


def test_get_scenes_only_counts_photos_inside_the_requested_range(scene_db, users):
    owner, _ = users
    scene = add_scene(scene_db, "区间", owner.id)
    add_photo(scene_db, owner.id, scene, when=datetime(2024, 1, 10, 9, 0), name="inside.jpg")
    add_photo(scene_db, owner.id, scene, when=datetime(2024, 3, 10, 9, 0), name="outside.jpg")

    scenes = scene_crud.get_scenes(scene_db, owner_id=owner.id,
                                   start_date="2024-01-01", end_date="2024-01-31")

    assert len(scenes) == 1
    assert scenes[0].photo_count == 1
    assert scenes[0].cover.filename == "inside.jpg"


def test_get_scenes_hides_photos_that_belong_to_another_owner(scene_db, users):
    owner, other = users
    scene = add_scene(scene_db, "混合", owner.id)
    add_photo(scene_db, owner.id, scene, when=datetime(2024, 4, 1, 9, 0), name="mine.jpg")
    add_photo(scene_db, other.id, scene, when=datetime(2024, 4, 2, 9, 0), name="theirs.jpg")

    scenes = scene_crud.get_scenes(scene_db, owner_id=owner.id)

    assert scenes[0].photo_count == 1
    assert scenes[0].cover.filename == "mine.jpg"


def test_get_scenes_paginates_with_skip_and_limit(scene_db, users):
    owner, _ = users
    first = add_scene(scene_db, "A", owner.id)
    add_scene(scene_db, "B", owner.id)
    add_photo(scene_db, owner.id, first, when=datetime(2024, 2, 1, 9, 0))

    scenes = scene_crud.get_scenes(scene_db, skip=1, limit=1, owner_id=owner.id)

    assert len(scenes) == 1
    assert scenes[0].name != "A"
