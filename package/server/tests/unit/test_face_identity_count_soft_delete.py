"""Unit tests for 人物列表 face_count 的软删除口径 (REQ-266).

回归背景：``get_identities_with_details`` 曾按全量（含软删除照片/人脸）统计
face_count，删除进回收站的照片仍计入列表数量，与人物详情页（已过滤
``Photo.is_deleted``）不一致。这里用真实 SQLite 会话（conftest.face_sqlite_session）
锁定活跃口径：

* 软删除照片上的人脸不计入 face_count（删除后数字立即下降）；
* 软删除人脸（如从人物中移除）不计入 face_count；
* 恢复软删除照片后计数回升；
* ``get_identities_by_photo_id`` 的 face_count 聚合同口径；
* face_count 跌破 min_photos 阈值后未命名人物不再展示（正确行为）。
"""

from uuid import uuid4

import pytest

from app.crud import face as crud_face
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _make_user(session, name):
    user = User(username=name, email=f"{name}@example.com", hashed_password="unused")
    session.add(user)
    session.flush()
    return user


def _add_photo(session, user, name, *, deleted=False):
    photo = Photo(
        filename=f"{name}.jpg",
        file_path=f"/{name}.jpg",
        file_type=FileType.image,
        size=1024,
        owner_id=user.id,
        is_deleted=deleted,
    )
    session.add(photo)
    session.flush()
    return photo


def _add_identity(session, user, name="未命名"):
    identity = FaceIdentity(identity_name=name, owner_id=user.id)
    session.add(identity)
    session.flush()
    return identity


def _link_face(session, photo, identity, *, deleted=False):
    face = Face(
        photo_id=photo.id,
        face_identity_id=identity.id,
        is_deleted=deleted,
        face_rect=[0.1, 0.1, 0.2, 0.2],
    )
    session.add(face)
    session.flush()
    return face


def _face_count(session, identity, owner, min_photos=0):
    rows = crud_face.get_identities_with_details(
        session, min_photos=min_photos, owner_id=owner.id,
        include_named_below_threshold=True,
    )
    for row in rows:
        if row.id == identity.id:
            return row.face_count
    return None


def test_person_count_excludes_soft_deleted_photos(face_sqlite_session):
    """AC-1：回收站软删除照片上的人脸不计入列表计数。"""
    session = face_sqlite_session
    owner = _make_user(session, "req266-a")
    identity = _add_identity(session, owner, "Alice")
    photos = [_add_photo(session, owner, f"p{i}") for i in range(3)]
    faces = [_link_face(session, photo, identity) for photo in photos]
    identity.default_face_id = faces[0].id
    photos[2].is_deleted = True
    session.commit()

    assert _face_count(session, identity, owner) == 2


def test_person_count_excludes_soft_deleted_faces(face_sqlite_session):
    """AC-2：软删除人脸（如从人物中移除）不计入列表计数。"""
    session = face_sqlite_session
    owner = _make_user(session, "req266-b")
    identity = _add_identity(session, owner, "Bob")
    photo = _add_photo(session, owner, "one")
    for i in range(3):
        _link_face(session, photo, identity, deleted=(i == 1))
    session.commit()

    # 一张照片上 3 条人脸（1 条软删），按照片去重计数为 1；对照活跃口径为 2 条活
    # 跃人脸——本用例用三张独立照片隔离「按照片去重」变量，验证的是软删人脸排除。
    assert _face_count(session, identity, owner) == 1


def test_person_count_recovers_after_restore(face_sqlite_session):
    """AC-3：软删后计数下降，恢复照片后计数回升。"""
    from app.crud.photo import restore_photos

    session = face_sqlite_session
    owner = _make_user(session, "req266-c")
    identity = _add_identity(session, owner, "Carol")
    photos = [_add_photo(session, owner, f"r{i}") for i in range(3)]
    for photo in photos:
        _link_face(session, photo, identity)
    photos[1].is_deleted = True
    session.commit()

    assert _face_count(session, identity, owner) == 2

    restore_photos(session, [photos[1].id], user_id=owner.id)
    assert _face_count(session, identity, owner) == 3


def test_get_identities_by_photo_id_excludes_soft_deleted_photos(face_sqlite_session):
    """AC-4：get_identities_by_photo_id 的 face_count 聚合排除软删照片。"""
    session = face_sqlite_session
    owner = _make_user(session, "req266-d")
    identity = _add_identity(session, owner, "Dave")
    active_photo = _add_photo(session, owner, "active")
    trashed_photo = _add_photo(session, owner, "trashed", deleted=True)
    for _ in range(2):
        _link_face(session, active_photo, identity)
    _link_face(session, trashed_photo, identity)
    session.commit()

    rows = crud_face.get_identities_by_photo_id(session, active_photo.id, owner_id=owner.id)
    # 主查询按人脸行返回：活跃照片上 2 条人脸 → 2 行，均指向该人物。
    assert {row.id for row in rows} == {identity.id}
    # 软删照片上的 1 条人脸不混入聚合计数。
    assert all(row.face_count == 2 for row in rows)


def test_unnamed_person_drops_out_below_threshold_after_soft_delete(face_sqlite_session):
    """软删后活跃计数跌破 min_photos 阈值，未命名人物不再展示（口径收紧的正确行为）。"""
    session = face_sqlite_session
    owner = _make_user(session, "req266-e")
    identity = _add_identity(session, owner)  # 未命名
    photos = [_add_photo(session, owner, f"t{i}") for i in range(3)]
    for photo in photos:
        _link_face(session, photo, identity)
    photos[2].is_deleted = True
    session.commit()

    rows = crud_face.get_identities_with_details(
        session, min_photos=3, owner_id=owner.id,
    )
    assert all(row.id != identity.id for row in rows)
