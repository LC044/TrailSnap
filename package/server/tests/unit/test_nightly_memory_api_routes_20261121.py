"""Nightly watch 2026-11-21 · app/api/memory.py 的路由盲区。

被测模块：app/api/memory.py。上一轮静态扫描显示该 router 有 12 个顶层
函数没有任何测试引用（list_memories / memory_counts / discover_memories /
merge_memories / create_memory / get_memory / update_memory / confirm_memory /
ignore_memory / restore_memory / archive_memory / add_memory_photos /
remove_memory_photos / split_memory / delete_memory）。

这些路由的价值集中在「状态机守卫」：只有候选记忆能忽略、只有已确认记忆能
归档、只有被忽略或已归档的记忆能恢复、只有候选或被忽略的记忆能确认。
本文件替换 service 协作者，逐条验证状态守卫与错误码映射。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import memory as memory_api
from app.db.models.memory import MemoryStatus
from app.schemas.memory import MemoryPhotoChange, MemorySplitRequest, MemorySplitPart

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def _row(status):
    return SimpleNamespace(id=uuid4(), status=status)


def _stub_detail(monkeypatch, row):
    from app.service import memory as memory_service

    monkeypatch.setattr(memory_service, "get_detail", lambda db, memory_id, owner_id: row)
    monkeypatch.setattr(memory_service, "serialize", lambda db, value, detail=False: {"status": value.status.value})
    return memory_service


def test_list_memories_wraps_the_items_and_the_total(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    captured = {}

    def fake_list_items(db, owner_id, status, skip, limit):
        captured.update({"owner_id": owner_id, "status": status, "skip": skip, "limit": limit})
        return [{"id": "m1"}], 1

    monkeypatch.setattr(memory_service, "list_items", fake_list_items)
    result = memory_api.list_memories(MemoryStatus.CONFIRMED, 0, 20, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == {"items": [{"id": "m1"}], "total": 1, "skip": 0, "limit": 20}
    assert captured["status"] == MemoryStatus.CONFIRMED


def test_confirm_memory_rejects_an_already_confirmed_memory(face_sqlite_session, monkeypatch):
    _stub_detail(monkeypatch, _row(MemoryStatus.CONFIRMED))
    with pytest.raises(HTTPException) as failure:
        memory_api.confirm_memory(uuid4(), _user(), face_sqlite_session)
    assert failure.value.status_code == 400
    assert failure.value.detail == "当前状态不能确认"


def test_confirm_memory_accepts_a_candidate(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    row = _row(MemoryStatus.CANDIDATE)
    _stub_detail(monkeypatch, row)
    changed = {}

    def fake_change_status(db, value, status):
        changed["status"] = status
        value.status = status
        return value

    monkeypatch.setattr(memory_service, "change_status", fake_change_status)
    result = memory_api.confirm_memory(row.id, _user(), face_sqlite_session)

    assert result.code == 0
    assert changed["status"] == MemoryStatus.CONFIRMED
    assert result.data == {"status": "confirmed"}


def test_ignore_memory_rejects_a_confirmed_memory(face_sqlite_session, monkeypatch):
    _stub_detail(monkeypatch, _row(MemoryStatus.CONFIRMED))
    with pytest.raises(HTTPException) as failure:
        memory_api.ignore_memory(uuid4(), _user(), face_sqlite_session)
    assert failure.value.status_code == 400
    assert failure.value.detail == "只有候选记忆可以忽略"


def test_archive_memory_rejects_a_candidate(face_sqlite_session, monkeypatch):
    _stub_detail(monkeypatch, _row(MemoryStatus.CANDIDATE))
    with pytest.raises(HTTPException) as failure:
        memory_api.archive_memory(uuid4(), _user(), face_sqlite_session)
    assert failure.value.status_code == 400
    assert failure.value.detail == "只有已确认记忆可以归档"


def test_restore_memory_rejects_a_candidate(face_sqlite_session, monkeypatch):
    _stub_detail(monkeypatch, _row(MemoryStatus.CANDIDATE))
    with pytest.raises(HTTPException) as failure:
        memory_api.restore_memory(uuid4(), _user(), face_sqlite_session)
    assert failure.value.status_code == 400
    assert failure.value.detail == "当前状态不能恢复"


def test_restore_memory_reactivates_an_ignored_memory(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    row = _row(MemoryStatus.IGNORED)
    _stub_detail(monkeypatch, row)
    changed = {}

    def fake_change_status(db, value, status):
        changed["status"] = status
        value.status = status
        return value

    monkeypatch.setattr(memory_service, "change_status", fake_change_status)
    result = memory_api.restore_memory(row.id, _user(), face_sqlite_session)

    assert result.code == 0
    assert changed["status"] == MemoryStatus.CANDIDATE


def test_add_memory_photos_forwards_the_photo_ids(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    row = _row(MemoryStatus.CONFIRMED)
    _stub_detail(monkeypatch, row)
    captured = {}

    def fake_add_photos(db, value, owner_id, photo_ids):
        captured["photo_ids"] = list(photo_ids)
        return value

    monkeypatch.setattr(memory_service, "add_photos", fake_add_photos)
    photo_ids = [uuid4(), uuid4()]
    result = memory_api.add_memory_photos(
        row.id, MemoryPhotoChange(photo_ids=photo_ids), _user(), face_sqlite_session
    )

    assert result.code == 0
    assert captured["photo_ids"] == photo_ids


def test_remove_memory_photos_forwards_the_photo_ids(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    row = _row(MemoryStatus.CONFIRMED)
    _stub_detail(monkeypatch, row)
    captured = {}

    def fake_remove_photos(db, value, owner_id, photo_ids):
        captured["photo_ids"] = list(photo_ids)
        return value

    monkeypatch.setattr(memory_service, "remove_photos", fake_remove_photos)
    photo_ids = [uuid4()]
    result = memory_api.remove_memory_photos(
        row.id, MemoryPhotoChange(photo_ids=photo_ids), _user(), face_sqlite_session
    )

    assert result.code == 0
    assert captured["photo_ids"] == photo_ids


def test_split_memory_serializes_every_part(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    rows = [_row(MemoryStatus.CONFIRMED), _row(MemoryStatus.CONFIRMED)]
    _stub_detail(monkeypatch, rows[0])
    monkeypatch.setattr(memory_service, "split", lambda db, owner_id, memory_id, payload: rows)

    payload = MemorySplitRequest(parts=[
        MemorySplitPart(title="第一段", photo_ids=[uuid4()]),
        MemorySplitPart(title="第二段", photo_ids=[uuid4()]),
    ])
    result = memory_api.split_memory(rows[0].id, payload, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == [{"status": "confirmed"}, {"status": "confirmed"}]


def test_delete_memory_marks_the_memory_deleted(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    row = _row(MemoryStatus.CONFIRMED)
    _stub_detail(monkeypatch, row)
    changed = {}

    def fake_change_status(db, value, status):
        changed["status"] = status
        return value

    monkeypatch.setattr(memory_service, "change_status", fake_change_status)
    result = memory_api.delete_memory(row.id, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == {"deleted": True}
    assert changed["status"] == MemoryStatus.DELETED


def test_memory_counts_returns_the_service_payload(face_sqlite_session, monkeypatch):
    from app.service import memory as memory_service

    monkeypatch.setattr(memory_service, "count_owned", lambda db, owner_id: {"confirmed": 3, "candidate": 1})
    result = memory_api.memory_counts(_user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == {"confirmed": 3, "candidate": 1}

