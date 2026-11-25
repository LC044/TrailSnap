"""Nightly watch 2026-11-25: ``app/service/similar_faces.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``service/similar_faces.py`` 为 96.7%，三条错误分支从未执行：

- 第 136 行：样本人脸在候选查询里查不到（人物被隐藏/删除）时返回 404，
  而不是拿一条不可见的样本人脸去算相似度；
- 第 219 行：一次提交里重复提交同一张人脸时返回 422；
- 第 261 行：撤销令牌里的条目为空或超过 500 条时返回 409。

这三条都是「批量改人脸归属」的原子性守卫：重复提交会让同一人脸被改两次，
空撤销记录会让撤销接口静默成功而不恢复任何人脸。

这里用真实的内存 SQLite 会话 + 真实 JWT 令牌复现这三条分支。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.schemas.face import AssignSimilarFaces, SimilarFaceSelection
from app.service import similar_faces


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


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
    user = User(id=uuid4(), username="nightly-similar-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _photo(db, owner, filename="nightly-face.jpg"):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename=filename, file_type=FileType.image,
        file_path=f"/photos/{filename}",
    )
    db.add(photo)
    db.commit()
    return photo


def _face(db, photo, identity=None, value=0.1):
    face = Face(
        photo_id=photo.id, face_identity_id=identity.id if identity else None,
        face_rect=[0.1, 0.1, 0.6, 0.7], face_feature=[value] * 512,
    )
    db.add(face)
    db.commit()
    return face


@pytest.fixture()
def neutral_cluster(monkeypatch):
    """聚类写路径在本机没有真实索引，这里替换成无副作用的桩。"""
    from app.service import face_appearance_clusters as appearance

    monkeypatch.setattr(appearance, "lock_owner", lambda db, owner_id: {})
    monkeypatch.setattr(appearance, "set_identity", lambda db, face, identity_id, owner_id: None)


def test_search_reports_a_sample_face_whose_identity_is_hidden(db, owner):
    hidden = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="已隐藏", is_hidden=True)
    db.add(hidden)
    photo = _photo(db, owner)
    face = _face(db, photo, hidden)

    with pytest.raises(HTTPException) as failure:
        similar_faces.search_similar_faces(db, photo.id, face.id, owner.id, scope="all")

    assert failure.value.status_code == 404
    assert failure.value.detail == "该人脸当前所属人物不可见，无法查找"


def test_search_returns_candidates_for_a_visible_sample_face(db, owner):
    identity = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="可见")
    db.add(identity)
    photo = _photo(db, owner)
    face = _face(db, photo, identity)

    result = similar_faces.search_similar_faces(db, photo.id, face.id, owner.id, scope="all")

    assert result.reference.id == face.id
    assert result.face_count == 0


def test_assign_rejects_a_duplicated_face_selection(db, owner, neutral_cluster):
    photo = _photo(db, owner)
    face = _face(db, photo)

    payload = AssignSimilarFaces(
        identity_id=None,
        selections=[
            SimilarFaceSelection(face_id=face.id, review_token="token"),
            SimilarFaceSelection(face_id=face.id, review_token="token"),
        ],
    )

    with pytest.raises(HTTPException) as failure:
        similar_faces.assign_similar_faces(db, photo.id, face.id, owner.id, payload)

    assert failure.value.status_code == 422
    assert failure.value.detail == "不能重复提交同一张人脸"


def test_undo_rejects_a_token_without_items(db, owner, neutral_cluster):
    token = similar_faces._sign({"items": []}, owner.id, "face-undo", 15)

    with pytest.raises(HTTPException) as failure:
        similar_faces.undo_face_assignment(db, owner.id, token)

    assert failure.value.status_code == 409
    assert failure.value.detail == "撤销记录无效"


def test_undo_rejects_a_token_with_too_many_items(db, owner, neutral_cluster):
    items = [{"id": index, "identity": None, "confidence": None, "expected": "x"}
             for index in range(501)]
    token = similar_faces._sign({"items": items}, owner.id, "face-undo", 15)

    with pytest.raises(HTTPException) as failure:
        similar_faces.undo_face_assignment(db, owner.id, token)

    assert failure.value.status_code == 409
    assert failure.value.detail == "撤销记录无效"
