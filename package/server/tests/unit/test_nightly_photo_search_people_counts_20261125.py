"""Nightly watch 2026-11-25 · app/service/agent/photo_search.py 的人数区间筛选盲区。

覆盖扫描显示 photo_search.py 未覆盖的 6 行全部落在 min_people / max_people
这条分支上（L66、L69-L71）：搜索工具的「合照 / 仅两人」语义完全依赖它，但既
有用例只测了人物 ID 与地点文本过滤。

本文件用真实 SQLite 会话验证：

- min_people 按张数过滤（只保留人脸数足够的照片）
- max_people 按张数过滤
- min_people == max_people 只保留恰好该人数的照片
- 区间颠倒（最少 > 最多）直接拒绝
- 负数人数直接拒绝
"""

from datetime import datetime
from uuid import uuid4

import pytest

from app.db.models.face import Face
from app.db.models.image_vector import ImageVector
from app.db.models.ocr import OCR
from app.db.models.photo import Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.service.agent import photo_search as photo_search_module
from app.service.agent.photo_search import search_photo_ids

pytestmark = [pytest.mark.regression, pytest.mark.module_agent]


@pytest.fixture
def owner(face_sqlite_session):
    user = User(username="searcher", email="searcher@example.com", hashed_password="x")
    face_sqlite_session.add(user)
    face_sqlite_session.commit()
    return user


def _photo(session, owner, filename, faces=0):
    photo = Photo(
        owner_id=owner.id, filename=filename, photo_time=datetime(2024, 5, 20, 10, 0),
        file_path=f"C:/photos/{filename}", file_type=Photo.__table__.c.file_type.type.enums[0],
    )
    session.add(photo)
    session.commit()
    for _ in range(faces):
        session.add(Face(photo_id=photo.id, is_deleted=False))
    session.commit()
    return photo


def test_min_people_keeps_only_group_shots(face_sqlite_session, owner):
    pair = _photo(face_sqlite_session, owner, "pair.jpg", faces=2)
    _photo(face_sqlite_session, owner, "single.jpg", faces=1)
    _photo(face_sqlite_session, owner, "empty.jpg", faces=0)

    ids = search_photo_ids(face_sqlite_session, str(owner.id), min_people=2)

    assert str(pair.id) in ids
    assert len(ids) == 1


def test_max_people_keeps_only_small_groups(face_sqlite_session, owner):
    single = _photo(face_sqlite_session, owner, "single.jpg", faces=1)
    _photo(face_sqlite_session, owner, "pair.jpg", faces=2)

    ids = search_photo_ids(face_sqlite_session, str(owner.id), max_people=1)

    assert ids == [str(single.id)]


def test_exact_people_range_keeps_only_matching_count(face_sqlite_session, owner):
    _photo(face_sqlite_session, owner, "single.jpg", faces=1)
    _photo(face_sqlite_session, owner, "trio.jpg", faces=3)

    ids = search_photo_ids(face_sqlite_session, str(owner.id), min_people=2, max_people=2)

    assert ids == []


def test_inverted_people_range_is_rejected(face_sqlite_session, owner):
    with pytest.raises(ValueError) as excinfo:
        search_photo_ids(face_sqlite_session, str(owner.id), min_people=3, max_people=2)

    assert "最少人数不能大于最多人数" in str(excinfo.value)


def test_negative_people_counts_are_rejected(face_sqlite_session, owner):
    with pytest.raises(ValueError) as excinfo:
        search_photo_ids(face_sqlite_session, str(owner.id), min_people=-1)

    assert "人数不能为负数" in str(excinfo.value)


def test_ocr_text_filters_photos_by_recognised_text(face_sqlite_session, owner):
    receipt = _photo(face_sqlite_session, owner, "receipt.jpg")
    _photo(face_sqlite_session, owner, "plain.jpg")
    face_sqlite_session.add(OCR(photo_id=receipt.id, text="invoice 2024-05"))
    face_sqlite_session.commit()

    ids = search_photo_ids(face_sqlite_session, str(owner.id), ocr_text="invoice")

    assert ids == [str(receipt.id)]


def test_tag_filter_keeps_only_tagged_photos(face_sqlite_session, owner):
    tagged = _photo(face_sqlite_session, owner, "tagged.jpg")
    _photo(face_sqlite_session, owner, "plain.jpg")
    tag = PhotoTag(tag_name="sunset", owner_id=owner.id)
    face_sqlite_session.add(tag)
    face_sqlite_session.commit()
    face_sqlite_session.add(PhotoTagRelation(photo_id=tagged.id, tag_id=tag.id, is_deleted=False))
    face_sqlite_session.commit()

    ids = search_photo_ids(face_sqlite_session, str(owner.id), tags=["sunset"])

    assert ids == [str(tagged.id)]


def _vector(head, tail=0.0):
    values = [0.0] * 512
    values[0] = head
    values[1] = tail
    return values


def test_description_search_ranks_by_similarity(face_sqlite_session, owner, monkeypatch):
    close = _photo(face_sqlite_session, owner, "close.jpg")
    far = _photo(face_sqlite_session, owner, "far.jpg")
    face_sqlite_session.add(ImageVector(photo_id=close.id, embedding=_vector(1.0)))
    face_sqlite_session.add(ImageVector(photo_id=far.id, embedding=_vector(0.0, 1.0)))
    face_sqlite_session.commit()
    monkeypatch.setattr(photo_search_module, "get_embedding", lambda *args, **kwargs: _vector(1.0))

    ids = search_photo_ids(face_sqlite_session, str(owner.id), description="sunset", threshold=0.2)

    assert ids == [str(close.id)]


def test_description_search_drops_vectors_below_the_threshold(face_sqlite_session, owner, monkeypatch):
    weak = _photo(face_sqlite_session, owner, "weak.jpg")
    face_sqlite_session.add(ImageVector(photo_id=weak.id, embedding=_vector(0.1, 0.1)))
    face_sqlite_session.commit()
    monkeypatch.setattr(photo_search_module, "get_embedding", lambda *args, **kwargs: _vector(1.0))

    ids = search_photo_ids(face_sqlite_session, str(owner.id), description="sunset", threshold=0.9)

    assert ids == []
