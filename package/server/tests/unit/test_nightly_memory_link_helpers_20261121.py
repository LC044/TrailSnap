"""夜间盲区补测：记忆域的关联写入辅助函数。

覆盖 app/service/memory.py 的 ``_set_photos`` / ``_set_people`` / ``_set_places``
（此前未被任何单测按名引用）。
"""
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import FaceIdentity
from app.db.models.memory import Memory, MemoryPerson, MemoryPhoto, MemoryPlace
from app.db.models.photo import Photo
from app.service import memory as memory_service

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


def _photo(name, taken):
    return Photo(id=uuid4(), owner_id=uuid4(), filename=name, photo_time=taken)


def _memory():
    return Memory(id=uuid4(), owner_id=uuid4())


def test_set_photos_replaces_links_and_sorts_by_photo_time():
    """重设照片关联时必须先清空旧关联，并按拍摄时间排序后写入 sort_order。"""
    memory = _memory()
    memory.photo_links.append(MemoryPhoto(source="ai", is_confirmed=False, sort_order=0))
    early = _photo("early.jpg", datetime(2026, 3, 1, 8, 0))
    late = _photo("late.jpg", datetime(2026, 5, 2, 9, 30))

    memory_service._set_photos(memory, [late, early], source="user", confirmed=True)

    links = list(memory.photo_links)
    assert len(links) == 2
    assert [link.sort_order for link in links] == [0, 1]
    assert links[0].photo is early
    assert links[1].photo is late
    assert all(link.source == "user" for link in links)
    assert all(link.is_confirmed is True for link in links)


def test_set_photos_treats_missing_photo_time_as_earliest():
    """没有拍摄时间的照片必须排在最前面，而不是被丢弃。"""
    memory = _memory()
    dated = _photo("dated.jpg", datetime(2026, 5, 2, 9, 30))
    undated = _photo("undated.jpg", None)

    memory_service._set_photos(memory, [dated, undated], source="ai", confirmed=False)

    links = list(memory.photo_links)
    assert links[0].photo is undated
    assert links[1].photo is dated
    assert all(link.source == "ai" for link in links)
    assert all(link.is_confirmed is False for link in links)


def test_set_people_clears_links_when_no_person_selected():
    """传入空人员列表时必须清空既有人员关联。"""
    memory = _memory()
    memory.people.append(MemoryPerson(source="ai", is_confirmed=False))

    memory_service._set_people(MagicMock(), memory, uuid4(), [], confirmed=True)

    assert list(memory.people) == []


def test_set_people_links_owned_identities():
    """人员关联只能绑定查询到的身份，并带上确认标记。"""
    identity = FaceIdentity(id=uuid4(), owner_id=uuid4(), identity_name="小明")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [identity]
    memory = _memory()

    memory_service._set_people(db, memory, uuid4(), [identity.id], confirmed=True)

    assert len(memory.people) == 1
    assert memory.people[0].identity is identity
    assert memory.people[0].source == "user"
    assert memory.people[0].is_confirmed is True


def test_set_people_rejects_identity_count_mismatch():
    """查询到的身份数量与请求不一致时必须拒绝（400），不得静默少绑。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    memory = _memory()

    with pytest.raises(HTTPException) as excinfo:
        memory_service._set_people(db, memory, uuid4(), [uuid4()], confirmed=False)

    assert excinfo.value.status_code == 400


def test_set_places_deduplicates_and_trims_names():
    """地点名必须去空白、去重，且 level/source 固定为 custom/user。"""
    memory = _memory()

    memory_service._set_places(memory, [" 北京 ", "北京", "上海", "  "], confirmed=True)

    places = list(memory.places)
    assert [place.name for place in places] == ["北京", "上海"]
    assert all(place.level == "custom" for place in places)
    assert all(place.source == "user" for place in places)
    assert all(place.is_confirmed is True for place in places)


def test_set_places_with_blank_input_empties_places():
    """全部为空白的地点输入必须清空地点关联。"""
    memory = _memory()
    memory.places.append(MemoryPlace(name="旧地点", level="city", source="ai", is_confirmed=False))

    memory_service._set_places(memory, ["", "   "], confirmed=False)

    assert list(memory.places) == []
