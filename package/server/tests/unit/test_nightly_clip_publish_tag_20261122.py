"""Nightly watch 2026-11-22 · app/service/clip_classification.py::publish_tag 盲区。

publish_tag 是 CLIP 分类结果的落库入口：它决定「某张照片是否保留某个独立分类」，
同时要尊重用户在 TagDecision 里做过的人工决策。

本文件覆盖：
- 无人工决策 + 有 score  -> 新建关联（happy）
- 有 keep=True 的人工决策 -> 关联存在且置信度为 1.0（edge）
- 有 keep=False 的人工决策 -> 关联被删除（error / 手动否决）
- tag_id 传字符串形式 -> 归一化成 UUID（edge）
"""

from uuid import uuid4

import pytest

from app.db.models.photo import Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.service.clip_classification import publish_tag

pytestmark = [pytest.mark.smoke]


def _photo(db):
    photo = Photo(id=uuid4(), filename="p.jpg", file_path="p.jpg", owner_id=uuid4(), file_type="image")
    db.add(photo)
    db.flush()
    return photo


def _tag(db):
    tag = PhotoTag(id=uuid4(), tag_name="cat", owner_id=uuid4())
    db.add(tag)
    db.flush()
    return tag


def test_publish_tag_creates_the_relation_when_a_score_is_given(face_sqlite_session):
    db = face_sqlite_session
    photo, tag = _photo(db), _tag(db)

    publish_tag(db, photo.id, tag.id, 0.82)
    db.flush()

    relation = db.query(PhotoTagRelation).filter_by(
        photo_id=photo.id, tag_id=tag.id).first()
    assert relation is not None
    assert relation.confidence == pytest.approx(0.82)
    assert relation.is_deleted is False


def test_publish_tag_without_a_score_and_without_a_decision_keeps_nothing(face_sqlite_session):
    db = face_sqlite_session
    photo, tag = _photo(db), _tag(db)

    publish_tag(db, photo.id, tag.id, None)
    db.flush()

    assert db.query(PhotoTagRelation).filter_by(
        photo_id=photo.id, tag_id=tag.id).first() is None


def test_publish_tag_honours_a_manual_keep_decision(face_sqlite_session):
    from app.db.models.clip_classification import TagDecision

    db = face_sqlite_session
    photo, tag = _photo(db), _tag(db)
    db.add(TagDecision(photo_id=photo.id, tag_id=tag.id, keep=True))
    db.flush()

    publish_tag(db, photo.id, tag.id, None)
    db.flush()

    relation = db.query(PhotoTagRelation).filter_by(
        photo_id=photo.id, tag_id=tag.id).first()
    assert relation is not None
    assert relation.confidence == pytest.approx(1.0)


def test_publish_tag_removes_the_relation_on_a_manual_rejection(face_sqlite_session):
    from app.db.models.clip_classification import TagDecision

    db = face_sqlite_session
    photo, tag = _photo(db), _tag(db)
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=0.9))
    db.add(TagDecision(photo_id=photo.id, tag_id=tag.id, keep=False))
    db.flush()

    publish_tag(db, photo.id, tag.id, 0.9)
    db.flush()

    assert db.query(PhotoTagRelation).filter_by(
        photo_id=photo.id, tag_id=tag.id).first() is None


def test_publish_tag_normalises_a_string_tag_id(face_sqlite_session):
    db = face_sqlite_session
    photo, tag = _photo(db), _tag(db)

    publish_tag(db, photo.id, str(tag.id), 0.5)
    db.flush()

    relation = db.query(PhotoTagRelation).filter_by(
        photo_id=photo.id, tag_id=tag.id).first()
    assert relation is not None





