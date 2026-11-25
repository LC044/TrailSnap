"""Nightly watch 2026-11-25: ``app/api/nav.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``api/nav.py`` 为 96.8%，其中两条路径从未被执行：

- 第 70 行：``resolve_single_entity`` 分派到 ``classification``（导航项指向分类标签）；
- 第 114-116 行：人物导航项命中 ``default_face_id`` 时的封面人脸分支
  （取封面照片、人脸框和去重照片数）。

这两条路径决定了导航栏里「分类入口」和「人物入口」能否正确显示封面与数量：
分类入口缺封面会显示空白卡片，人物入口缺封面则看不到缩略图。

这里用真实的内存 SQLite 会话覆盖三条行为：

- 分类命中已有封面（happy）
- 分类没有封面时回退到任意一张关联照片（edge）
- 人物命中默认人脸时带出封面照片 / 人脸框 / 去重照片数（happy）
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import nav as nav_api
from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.schemas.nav import NavItemRef


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


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
    user = User(id=uuid4(), username="nightly-nav-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _photo(db, owner, filename="nightly.jpg"):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename=filename, file_type=FileType.image,
        file_path=f"/photos/{filename}",
    )
    db.add(photo)
    db.commit()
    return photo


def test_resolve_classification_uses_the_tag_cover(db, owner):
    tag = PhotoTag(id=uuid4(), owner_id=owner.id, tag_name="夜景", type="scene")
    cover = _photo(db, owner, "cover.jpg")
    tag.cover_id = cover.id
    db.add(tag)
    db.add(PhotoTagRelation(photo_id=cover.id, tag_id=tag.id))
    db.commit()

    resolved = nav_api.resolve_classification(str(tag.id), owner.id, db)

    assert resolved is not None
    assert resolved.entity_type == "classification"
    assert resolved.name == "夜景"
    assert resolved.cover_photo_id == str(cover.id)
    assert resolved.photo_count == 1
    assert resolved.route_path == f"/album/classification/{tag.tag_name}"


def test_resolve_classification_falls_back_to_a_related_photo(db, owner):
    tag = PhotoTag(id=uuid4(), owner_id=owner.id, tag_name="美食", type="scene")
    db.add(tag)
    photo = _photo(db, owner, "food.jpg")
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id))
    db.commit()

    resolved = nav_api.resolve_classification(str(tag.id), owner.id, db)

    assert resolved is not None
    assert resolved.cover_photo_id == str(photo.id)


def test_resolve_classification_returns_none_for_a_missing_tag(db, owner):
    assert nav_api.resolve_classification(str(uuid4()), owner.id, db) is None


def test_resolve_person_uses_the_default_face_as_cover(db, owner):
    identity = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="小明")
    db.add(identity)
    first = _photo(db, owner, "face-a.jpg")
    second = _photo(db, owner, "face-b.jpg")
    face = Face(photo_id=first.id, face_identity_id=identity.id,
                face_rect=[0.1, 0.1, 0.5, 0.6], face_feature=[0.1] * 512)
    db.add(face)
    db.flush()
    identity.default_face_id = face.id
    db.add(Face(photo_id=second.id, face_identity_id=identity.id,
                face_rect=[0.2, 0.2, 0.4, 0.5], face_feature=[0.2] * 512))
    db.commit()

    resolved = nav_api.resolve_person(str(identity.id), owner.id, db)

    assert resolved is not None
    assert resolved.entity_type == "person"
    assert resolved.name == "小明"
    assert resolved.cover_photo_id == str(first.id)
    assert resolved.cover_photo_face_rect == [0.1, 0.1, 0.5, 0.6]
    assert resolved.photo_count == 2
    assert resolved.route_path == f"/album/people/{identity.id}"


def test_resolve_single_entity_dispatches_classification_refs(db, owner):
    tag = PhotoTag(id=uuid4(), owner_id=owner.id, tag_name="旅行", type="scene")
    db.add(tag)
    db.commit()

    ref = NavItemRef(entity_type="classification", entity_id=str(tag.id))
    resolved = nav_api.resolve_single_entity(ref, owner.id, db)

    assert resolved is not None
    assert resolved.entity_type == "classification"
    assert resolved.name == "旅行"
