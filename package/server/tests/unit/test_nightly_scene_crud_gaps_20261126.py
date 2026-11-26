"""Nightly watch 2026-11-26 · app/crud/scene.py 的 CRUD 盲区。

覆盖扫描（§4.1 定向 --cov）显示 ``app/crud/scscene.py`` 只有 32% 覆盖：
既有测试只调用了 ``get_scenes``（列表 + 封面选择），其余分支从未被触达：

- ``point_in_polygon``：射线法判定（含凹多边形、边界、退化输入）
- ``update_scene_photos``：包围盒过滤、多边形内外判定、owner 过滤
- ``create_scene`` / ``update_scene`` / ``get_scene`` / ``delete_scene``

全部用真实 SQLite 会话执行（``Base.metadata.create_all``），不走 MagicMock，
以免只验证 mock 的形状而没有验证行为。
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.crud.scene import (
    create_scene,
    delete_scene,
    get_scene,
    point_in_polygon,
    update_scene,
    update_scene_photos,
)
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.schemas.scene import SceneCreate, SceneUpdate


@pytest.fixture
def scene_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_photo(db, owner, *, latitude=None, longitude=None, scene_id=None):
    photo_id = uuid4()
    db.add(Photo(
        id=photo_id, owner_id=owner, filename="s.jpg", file_path="/isolated/s.jpg",
        file_type=FileType.image, size=1, is_deleted=False,
    ))
    db.add(PhotoMetadata(
        photo_id=photo_id, latitude=latitude, longitude=longitude, scene_id=scene_id,
    ))
    return photo_id


SQUARE = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]


# --- point_in_polygon -------------------------------------------------


def test_point_in_polygon_accepts_inside_and_rejects_outside():
    assert point_in_polygon(5.0, 5.0, SQUARE) is True
    assert point_in_polygon(20.0, 5.0, SQUARE) is False
    assert point_in_polygon(-1.0, 5.0, SQUARE) is False
    assert point_in_polygon(5.0, 20.0, SQUARE) is False


def test_point_in_polygon_handles_concave_shape():
    # L 形：缺口在右上角
    l_shape = [[0.0, 0.0], [0.0, 10.0], [4.0, 10.0], [4.0, 4.0],
               [10.0, 4.0], [10.0, 0.0]]
    assert point_in_polygon(2.0, 8.0, l_shape) is True
    assert point_in_polygon(7.0, 2.0, l_shape) is True
    assert point_in_polygon(7.0, 8.0, l_shape) is False


def test_point_in_polygon_degenerate_polygon_is_never_inside():
    assert point_in_polygon(1.0, 1.0, [[0.0, 0.0]]) is False
    assert point_in_polygon(0.0, 0.0, [[0.0, 0.0]]) is False


# --- update_scene_photos ---------------------------------------------


def test_update_scene_photos_assigns_only_photos_inside_the_polygon(scene_db):
    db = scene_db
    owner = uuid4()
    scene = Scene(id=uuid4(), name="范围", owner_id=owner,
                  polygon=[[30.0, 114.0], [30.0, 115.0], [31.0, 115.0], [31.0, 114.0]])
    db.add(scene)
    inside = add_photo(db, owner, latitude=30.5, longitude=114.5)
    outside = add_photo(db, owner, latitude=35.0, longitude=114.5)
    db.commit()

    update_scene_photos(db, scene)
    db.expire_all()

    assert db.get(PhotoMetadata, inside).scene_id == scene.id
    assert db.get(PhotoMetadata, outside).scene_id is None


def test_update_scene_photos_skips_other_owners_photos(scene_db):
    db = scene_db
    owner, other = uuid4(), uuid4()
    scene = Scene(id=uuid4(), name="私有", owner_id=owner,
                  polygon=[[30.0, 114.0], [30.0, 115.0], [31.0, 115.0], [31.0, 114.0]])
    db.add(scene)
    mine = add_photo(db, owner, latitude=30.5, longitude=114.5)
    theirs = add_photo(db, other, latitude=30.5, longitude=114.5)
    db.commit()

    update_scene_photos(db, scene)

    assert db.get(PhotoMetadata, mine).scene_id == scene.id
    assert db.get(PhotoMetadata, theirs).scene_id is None


def test_update_scene_photos_without_polygon_is_a_noop(scene_db):
    db = scene_db
    owner = uuid4()
    scene = Scene(id=uuid4(), name="无多边形", owner_id=owner)
    db.add(scene)
    photo_id = add_photo(db, owner, latitude=30.5, longitude=114.5)
    db.commit()

    update_scene_photos(db, scene)

    assert db.get(PhotoMetadata, photo_id).scene_id is None


# --- create_scene ----------------------------------------------------


def test_create_scene_persists_the_scene_and_assigns_photos(scene_db):
    db = scene_db
    owner = uuid4()
    photo_id = add_photo(db, owner, latitude=30.5, longitude=114.5)
    db.commit()

    scene = create_scene(
        db,
        SceneCreate(name="新建场景", polygon=[[30.0, 114.0], [30.0, 115.0],
                                             [31.0, 115.0], [31.0, 114.0]]),
        owner_id=owner,
    )

    assert scene.id is not None
    assert scene.name == "新建场景"
    assert db.get(PhotoMetadata, photo_id).scene_id == scene.id


# --- get_scene --------------------------------------------------------


def test_get_scene_returns_owned_or_public_scenes(scene_db):
    db = scene_db
    owner = uuid4()
    mine = Scene(id=uuid4(), name="我的", owner_id=owner)
    public = Scene(id=uuid4(), name="公共", owner_id=None)
    theirs = Scene(id=uuid4(), name="别人的", owner_id=uuid4())
    db.add_all([mine, public, theirs])
    db.commit()

    assert get_scene(db, mine.id, owner_id=owner).id == mine.id
    assert get_scene(db, public.id, owner_id=owner).id == public.id
    assert get_scene(db, theirs.id, owner_id=owner) is None
    # 没有 owner_id 时只暴露公共场景
    assert get_scene(db, public.id).id == public.id
    assert get_scene(db, mine.id) is None


# --- delete_scene ----------------------------------------------------


def test_delete_scene_rejects_other_owners_and_system_scenes(scene_db):
    db = scene_db
    owner = uuid4()
    foreign = Scene(id=uuid4(), name="别人的", owner_id=uuid4())
    system = Scene(id=uuid4(), name="系统内置", owner_id=owner, is_custom=False)
    db.add_all([foreign, system])
    db.commit()

    with pytest.raises(ValueError, match="Permission denied"):
        delete_scene(db, foreign.id, owner_id=owner)
    with pytest.raises(ValueError, match="system default"):
        delete_scene(db, system.id, owner_id=owner)


def test_delete_scene_clears_the_photo_metadata_reference(scene_db):
    db = scene_db
    owner = uuid4()
    scene = Scene(id=uuid4(), name="可删", owner_id=owner)
    db.add(scene)
    photo_id = add_photo(db, owner, latitude=30.5, longitude=114.5, scene_id=scene.id)
    db.commit()

    deleted = delete_scene(db, scene.id, owner_id=owner)

    assert deleted is not None
    assert db.get(PhotoMetadata, photo_id).scene_id is None
    assert db.get(Scene, scene.id) is None


def test_delete_scene_returns_none_for_a_missing_scene(scene_db):
    assert delete_scene(scene_db, uuid4(), owner_id=uuid4()) is None


# --- update_scene ----------------------------------------------------


def test_update_scene_applies_fields_and_reassigns_polygon(scene_db):
    db = scene_db
    owner = uuid4()
    scene = Scene(id=uuid4(), name="旧名", owner_id=owner,
                  polygon=[[30.0, 114.0], [30.0, 115.0], [31.0, 115.0], [31.0, 114.0]])
    db.add(scene)
    photo_id = add_photo(db, owner, latitude=30.5, longitude=114.5)
    db.commit()

    updated = update_scene(
        db, scene.id,
        SceneUpdate(name="新名", polygon=[[40.0, 110.0], [40.0, 111.0],
                                          [41.0, 111.0], [41.0, 110.0]]),
        owner_id=owner,
    )

    assert updated.name == "新名"
    # 多边形变了，照片不再落在范围内
    assert db.get(PhotoMetadata, photo_id).scene_id is None


def test_update_scene_returns_none_for_a_missing_scene(scene_db):
    assert update_scene(scene_db, uuid4(), SceneUpdate(name="x"), owner_id=uuid4()) is None


def test_update_scene_rejects_other_owners(scene_db):
    db = scene_db
    scene = Scene(id=uuid4(), name="别人的", owner_id=uuid4())
    db.add(scene)
    db.commit()

    with pytest.raises(ValueError, match="Permission denied"):
        update_scene(db, scene.id, SceneUpdate(name="x"), owner_id=uuid4())

