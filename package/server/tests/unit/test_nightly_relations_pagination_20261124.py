"""Nightly watch 2026-11-24 · app/service/relations.py 的分页与参数校验盲区。

覆盖扫描显示 relations.py 仍有 10 行未覆盖，全部集中在「游标 / 参数非法 ->
HTTPException(400)」这条分支上：

- neighbors(): 游标 last 不是一个 [int, str] 二元组 (L704)
- evidence(): kind / limit 非法 (L764)、游标 last 非法 (L780)
- search():   kind / limit 非法 (L801)、memory/photo 查询分支 (L808/L812)、
              游标 last 非法 (L857/L858) 与按 node 续页 (L859)

这些分支是关系图对外唯一的分页契约：游标是「作用域绑定」而非授权令牌，
格式不对必须明确 400 而不是静默返回第一页。测试用真实 SQLite 会话
(conftest 的 face_sqlite_session)，只替换游标解码，验证真实的 SQL 路径。

注意节点 key 用 uuid_key() 生成（hex 无连字符），与 SQL 里的 uuid_expr 一致。
"""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.relations import Relations, uuid_key

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture
def owner(face_sqlite_session):
    db = face_sqlite_session
    user = User(id=uuid4(), username="relations-owner", hashed_password="x")
    db.add(user)
    db.flush()
    photos = []
    for index in range(2):
        photo = Photo(
            id=uuid4(),
            owner_id=user.id,
            filename=f"p{index}.jpg",
            file_path=f"/p{index}.jpg",
            file_type=FileType.image,
            photo_time=datetime(2026, 9, index + 1),
            is_deleted=False,
        )
        db.add(photo)
        photos.append(photo)
    db.flush()
    return user, photos


@pytest.fixture
def relations(owner, face_sqlite_session):
    user, _photos = owner
    return Relations(face_sqlite_session, user.id)


def _photo_key(photo):
    return uuid_key("photo", photo.id)


def test_neighbors_rejects_a_malformed_cursor(relations, owner, monkeypatch):
    _user, photos = owner
    monkeypatch.setattr(relations, "_cursor", lambda cursor, context: ["not-a-pair"])

    with pytest.raises(HTTPException) as failure:
        relations.neighbors(_photo_key(photos[0]), ["person"], limit=20)

    assert failure.value.status_code == 400
    assert failure.value.detail == "无效分页"


def test_evidence_rejects_an_unknown_kind(relations, owner):
    _user, photos = owner
    with pytest.raises(HTTPException) as failure:
        relations.evidence(_photo_key(photos[0]), _photo_key(photos[1]), kind="bogus")

    assert failure.value.status_code == 400
    assert failure.value.detail == "无效的依据类型或数量"


def test_evidence_rejects_a_limit_out_of_range(relations, owner):
    _user, photos = owner
    with pytest.raises(HTTPException) as failure:
        relations.evidence(_photo_key(photos[0]), _photo_key(photos[1]), kind="memory", limit=0)
    assert failure.value.status_code == 400
    assert failure.value.detail == "无效的依据类型或数量"


def test_evidence_rejects_a_malformed_cursor(relations, owner, monkeypatch):
    _user, photos = owner
    monkeypatch.setattr(relations, "_cursor", lambda cursor, context: [1, 2])

    with pytest.raises(HTTPException) as failure:
        relations.evidence(_photo_key(photos[0]), _photo_key(photos[1]), kind="photo")

    assert failure.value.status_code == 400
    assert failure.value.detail == "无效分页"


def test_search_rejects_an_unknown_kind(relations):
    with pytest.raises(HTTPException) as failure:
        relations.search(kind="bogus")
    assert failure.value.status_code == 400
    assert failure.value.detail == "无效的类型或数量"


def test_search_rejects_a_limit_out_of_range(relations):
    with pytest.raises(HTTPException) as failure:
        relations.search(kind="person", limit=51)
    assert failure.value.status_code == 400
    assert failure.value.detail == "无效的类型或数量"


def test_search_supports_the_memory_and_photo_branches(relations, owner):
    _user, photos = owner
    memories = relations.search(kind="memory", q="")
    found = relations.search(kind="photo", q="p0")
    assert memories["items"] == []
    assert [item["id"] for item in found["items"]] == [_photo_key(photos[0])]


def test_search_rejects_a_malformed_cursor(relations, monkeypatch):
    monkeypatch.setattr(relations, "_cursor", lambda cursor, context: [123])
    with pytest.raises(HTTPException) as failure:
        relations.search(kind="person")
    assert failure.value.status_code == 400
    assert failure.value.detail == "无效分页"


def test_search_continues_from_a_valid_cursor(relations, owner, monkeypatch):
    _user, photos = owner
    monkeypatch.setattr(relations, "_cursor", lambda cursor, context: [_photo_key(photos[0])])
    result = relations.search(kind="photo", q="p0")
    assert result["items"] == []
    assert result["has_more"] is False

