"""Unit tests for 合影组合相册 (app/crud/face.py: get_group_albums / get_group_album_photos).

Runs against a real SQLite session（conftest.face_sqlite_session）：组合聚合是
多条 join + distinct + 内存分组，MagicMock 无法忠实模拟 SQL 行为。覆盖：

* 单人照片数达到阈值（min_photos）的人物才参与组合；
* 隐藏 / 软删除人物不参与组合；
* 组合 = 照片内出现的可展示人物集合；photo_count = 同时包含全部成员的照片数；
* 三人照归入三人组合，不归入其中的二人子组合；
* get_group_album_photos 只返回同时包含全部指定成员的照片；
* owner 隔离与软删除排除。

以及路由层参数透传（patch crud）。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import face as face_api
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


def _add_photo(session, user, name, *, deleted=False, photo_time=None):
    photo = Photo(
        filename=f"{name}.jpg",
        file_path=f"/{name}.jpg",
        file_type=FileType.image,
        size=1024,
        owner_id=user.id,
        is_deleted=deleted,
        photo_time=photo_time,
    )
    session.add(photo)
    session.flush()
    return photo


def _add_identity(session, user, name, *, deleted=False, hidden=False):
    identity = FaceIdentity(identity_name=name, owner_id=user.id, is_deleted=deleted, is_hidden=hidden)
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


def _find_album(albums, member_ids):
    """按成员集合查找组合。"""
    wanted = frozenset(member_ids)
    for album in albums:
        if frozenset(i.identity_id for i in album.identities) == wanted:
            return album
    return None


# ---------------------------------------------------------------------------
# crud.get_group_albums -- SQLite 行为测试
# ---------------------------------------------------------------------------


def test_group_albums_respect_min_photos_threshold(face_sqlite_session):
    """照片数未达阈值的人物不参与组合（与“个人”栏口径一致）。"""
    user = _make_user(face_sqlite_session, "thr-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")

    # Alice 出现在 3 张照片（达标），Bob 只有 1 张（不达标）
    for i in range(3):
        photo = _add_photo(face_sqlite_session, user, f"a{i}")
        _link_face(face_sqlite_session, photo, alice)
    one_bob = _add_photo(face_sqlite_session, user, "b0")
    _link_face(face_sqlite_session, one_bob, bob)
    # 一张两人同框：Bob 借此仍只有 1 张照片 → min_photos=2 时不达标
    together = _add_photo(face_sqlite_session, user, "together")
    _link_face(face_sqlite_session, together, alice)
    _link_face(face_sqlite_session, together, bob)
    face_sqlite_session.commit()

    # min_photos=2：Bob 的 distinct 照片数只有 2（b0 + together）→ 达标，应出现组合
    # （注意统计口径是 distinct photo 数，together 也算 Bob 的照片）
    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=2, owner_id=user.id)
    found = _find_album(albums, [alice.id, bob.id])
    assert found is not None
    assert found.photo_count == 1
    assert found.cover.id == together.id

    # min_photos=3：Bob（2 张）不达标 → 无组合
    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=3, owner_id=user.id)
    assert albums == []


def test_group_albums_exclude_hidden_and_deleted_identities(face_sqlite_session):
    """隐藏 / 软删除人物不参与组合。"""
    user = _make_user(face_sqlite_session, "hid-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")
    eve = _add_identity(face_sqlite_session, user, "Eve", hidden=True)
    mallory = _add_identity(face_sqlite_session, user, "Mallory", deleted=True)

    # Alice 与每人的同框照
    for identity in (bob, eve, mallory):
        photo = _add_photo(face_sqlite_session, user, f"p-{identity.identity_name}")
        _link_face(face_sqlite_session, photo, alice)
        _link_face(face_sqlite_session, photo, identity)
    # Alice 自身需要独立照片达到阈值（min_photos=1 即可）
    _link_face(face_sqlite_session, _add_photo(face_sqlite_session, user, "a-solo"), alice)
    bob_solo = _add_photo(face_sqlite_session, user, "b-solo")
    _link_face(face_sqlite_session, bob_solo, bob)
    face_sqlite_session.commit()

    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user.id)
    member_sets = {frozenset(i.identity_id for i in a.identities) for a in albums}

    assert frozenset([alice.id, bob.id]) in member_sets
    assert all(eve.id not in s for s in member_sets), "hidden identity must not appear"
    assert all(mallory.id not in s for s in member_sets), "soft-deleted identity must not appear"


def test_group_albums_assign_photo_to_exact_member_set(face_sqlite_session):
    """三人照归入三人组合；“张三+李四”二人组合不含三人照。"""
    user = _make_user(face_sqlite_session, "exact-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")
    carol = _add_identity(face_sqlite_session, user, "Carol")

    duo = _add_photo(face_sqlite_session, user, "duo")
    _link_face(face_sqlite_session, duo, alice)
    _link_face(face_sqlite_session, duo, bob)

    trio = _add_photo(face_sqlite_session, user, "trio")
    for identity in (alice, bob, carol):
        _link_face(face_sqlite_session, trio, identity)
    face_sqlite_session.commit()

    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user.id)

    duo_album = _find_album(albums, [alice.id, bob.id])
    trio_album = _find_album(albums, [alice.id, bob.id, carol.id])

    assert duo_album is not None and duo_album.photo_count == 1
    assert duo_album.cover.id == duo.id
    assert trio_album is not None and trio_album.photo_count == 1
    assert trio_album.cover.id == trio.id


def test_group_albums_cover_is_latest_photo(face_sqlite_session):
    """封面取组合内 photo_time 最新的一张。"""
    from datetime import datetime

    user = _make_user(face_sqlite_session, "cover-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")

    older = _add_photo(face_sqlite_session, user, "older", photo_time=datetime(2024, 1, 1))
    newer = _add_photo(face_sqlite_session, user, "newer", photo_time=datetime(2025, 1, 1))
    for photo in (older, newer):
        _link_face(face_sqlite_session, photo, alice)
        _link_face(face_sqlite_session, photo, bob)
    face_sqlite_session.commit()

    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user.id)
    found = _find_album(albums, [alice.id, bob.id])
    assert found is not None
    assert found.cover.id == newer.id
    assert found.photo_count == 2


def test_group_albums_exclude_soft_deleted_photos_and_faces(face_sqlite_session):
    """软删除照片 / 人脸不参与组合与计数。"""
    user = _make_user(face_sqlite_session, "sf-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")

    deleted_photo = _add_photo(face_sqlite_session, user, "deleted-photo", deleted=True)
    _link_face(face_sqlite_session, deleted_photo, alice)
    _link_face(face_sqlite_session, deleted_photo, bob)

    # 一张脸被软删 → 退化为单人照片 → 不构成组合
    face_gone = _add_photo(face_sqlite_session, user, "face-gone")
    _link_face(face_sqlite_session, face_gone, alice)
    _link_face(face_sqlite_session, face_gone, bob, deleted=True)

    ok = _add_photo(face_sqlite_session, user, "ok")
    _link_face(face_sqlite_session, ok, alice)
    _link_face(face_sqlite_session, ok, bob)
    face_sqlite_session.commit()

    albums = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user.id)
    found = _find_album(albums, [alice.id, bob.id])
    assert found is not None
    assert found.photo_count == 1
    assert found.cover.id == ok.id


def test_group_albums_isolate_by_owner(face_sqlite_session):
    """B 用户不产生 A 用户的组合；B 引用 A 的 identity（异常数据）不算组合。"""
    user_a = _make_user(face_sqlite_session, "owner-a2")
    user_b = _make_user(face_sqlite_session, "owner-b2")
    a1 = _add_identity(face_sqlite_session, user_a, "A1")
    a2 = _add_identity(face_sqlite_session, user_a, "A2")

    # A 自己的合影
    photo_a = _add_photo(face_sqlite_session, user_a, "a-group")
    _link_face(face_sqlite_session, photo_a, a1)
    _link_face(face_sqlite_session, photo_a, a2)

    # B 的照片引用 A 的 identity（异常数据）
    photo_b = _add_photo(face_sqlite_session, user_b, "b-photo")
    face_sqlite_session.add_all([
        Face(photo_id=photo_b.id, face_identity_id=a1.id, is_deleted=False),
        Face(photo_id=photo_b.id, face_identity_id=a2.id, is_deleted=False),
    ])
    face_sqlite_session.commit()

    albums_a = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user_a.id)
    found_a = _find_album(albums_a, [a1.id, a2.id])
    assert found_a is not None
    assert found_a.photo_count == 1  # 只算 A 自己的照片
    assert found_a.cover.id == photo_a.id

    albums_b = crud_face.get_group_albums(face_sqlite_session, min_photos=1, owner_id=user_b.id)
    assert albums_b == []


# ---------------------------------------------------------------------------
# crud.get_group_album_photos -- 组合内照片
# ---------------------------------------------------------------------------


def test_group_album_photos_requires_all_members(face_sqlite_session):
    """只返回同时包含全部指定成员的照片；软删除照片排除；按时间倒序。"""
    from datetime import datetime

    user = _make_user(face_sqlite_session, "gap-user")
    alice = _add_identity(face_sqlite_session, user, "Alice")
    bob = _add_identity(face_sqlite_session, user, "Bob")

    both_old = _add_photo(face_sqlite_session, user, "both-old", photo_time=datetime(2024, 1, 1))
    _link_face(face_sqlite_session, both_old, alice)
    _link_face(face_sqlite_session, both_old, bob)

    both_new = _add_photo(face_sqlite_session, user, "both-new", photo_time=datetime(2025, 1, 1))
    _link_face(face_sqlite_session, both_new, alice)
    _link_face(face_sqlite_session, both_new, bob)

    # 只有 Alice → 不属于组合照片
    alice_only = _add_photo(face_sqlite_session, user, "alice-only")
    _link_face(face_sqlite_session, alice_only, alice)
    face_sqlite_session.commit()

    photos = crud_face.get_group_album_photos(
        face_sqlite_session, identity_ids=[alice.id, bob.id], owner_id=user.id
    )
    assert [p.id for p in photos] == [both_new.id, both_old.id]


# ---------------------------------------------------------------------------
# api -- 路由参数透传
# ---------------------------------------------------------------------------


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def test_list_group_albums_uses_user_config_when_min_photos_missing():
    user = _user()
    db = MagicMock()
    data = [SimpleNamespace(identities=[], photo_count=1, cover=None)]
    config = SimpleNamespace(ai=SimpleNamespace(face_recognition_min_photos=5))

    with patch.object(face_api.crud_face, "get_group_albums", return_value=data) as crud_call, \
         patch.object(face_api.config_manager, "get_user_config", return_value=config) as cfg:
        response = face_api.list_group_albums(min_photos=None, db=db, current_user=user)

    cfg.assert_called_once_with(user.id, db)
    crud_call.assert_called_once_with(db, min_photos=5, owner_id=user.id)
    assert response.code == 200
    assert response.data == data


def test_list_group_albums_passes_explicit_min_photos():
    user = _user()
    db = MagicMock()

    with patch.object(face_api.crud_face, "get_group_albums", return_value=[]) as crud_call:
        response = face_api.list_group_albums(min_photos=2, db=db, current_user=user)

    crud_call.assert_called_once_with(db, min_photos=2, owner_id=user.id)
    assert response.code == 200


def test_list_group_album_photos_passes_identity_ids():
    user = _user()
    db = MagicMock()
    ids = [uuid4(), uuid4()]
    photos = [SimpleNamespace(id=uuid4())]

    with patch.object(face_api.crud_face, "get_group_album_photos", return_value=photos) as crud_call:
        response = face_api.list_group_album_photos(
            identity_ids=ids, skip=0, limit=50, db=db, current_user=user
        )

    crud_call.assert_called_once_with(
        db, identity_ids=ids, skip=0, limit=50, owner_id=user.id
    )
    assert response.code == 200
    assert response.data == photos
