"""Nightly coverage for the person-timeline hide rules in app/api/face.py.

覆盖此前完全没被单测走到的分支：时间范围校验（起点>=终点 / 超过 31 天）、
dry_run 预演（不落库）、隐藏片段列表（photo_count 统计）、恢复隐藏（删除规则
与 404 分支）。person_timeline 的 DB 查询全部打桩，避免依赖 Postgres。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import face as face_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _scope(first=None, second=None):
    return first or uuid4(), second or uuid4(), []


def _payload(start, end):
    return face_api.TimelineHideInput(start_at=start, end_at=end)


def _photo_query(count=0, photos=None):
    """构造一个链式查询桩：filter(...).count() / .order_by(...).limit(...).all()。"""
    query = MagicMock()
    query.filter.return_value = query
    query.count.return_value = count
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = photos if photos is not None else []
    return query


def test_hide_rejects_inverted_time_range():
    user = _user()
    db = MagicMock()
    start = datetime(2025, 5, 10)
    end = datetime(2025, 5, 1)

    with patch.object(face_api.person_timeline, "scope", return_value=_scope()):
        with pytest.raises(HTTPException) as exc_info:
            face_api.hide_person_timeline_segment(
                id=uuid4(), payload=_payload(start, end), with_id=None,
                dry_run=False, db=db, current_user=user,
            )

    assert exc_info.value.status_code == 400


def test_hide_rejects_range_longer_than_31_days():
    user = _user()
    db = MagicMock()
    start = datetime(2025, 1, 1)
    end = start + timedelta(days=32)

    with patch.object(face_api.person_timeline, "scope", return_value=_scope()):
        with pytest.raises(HTTPException) as exc_info:
            face_api.hide_person_timeline_segment(
                id=uuid4(), payload=_payload(start, end), with_id=None,
                dry_run=False, db=db, current_user=user,
            )

    assert exc_info.value.status_code == 400


def test_hide_dry_run_reports_count_without_persisting():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4())
    start = datetime(2025, 5, 1)
    end = datetime(2025, 5, 8)

    with patch.object(face_api.person_timeline, "scope", return_value=_scope()):
        with patch.object(face_api.person_timeline, "photo_query", return_value=_photo_query(count=3, photos=[photo])):
            with patch.object(face_api.person_timeline, "photo_dict", return_value={"id": str(photo.id)}):
                response = face_api.hide_person_timeline_segment(
                    id=uuid4(), payload=_payload(start, end), with_id=None,
                    dry_run=True, db=db, current_user=user,
                )

    assert response.code == 0
    assert response.data["photo_count"] == 3
    assert response.data["photos"] == [{"id": str(photo.id)}]
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_hide_persists_rule_and_returns_new_id():
    user = _user()
    db = MagicMock()
    start = datetime(2025, 5, 1)
    end = datetime(2025, 5, 8)

    with patch.object(face_api.person_timeline, "scope", return_value=_scope()):
        with patch.object(face_api.person_timeline, "photo_query", return_value=_photo_query(count=2)):
            response = face_api.hide_person_timeline_segment(
                id=uuid4(), payload=_payload(start, end), with_id=None,
                dry_run=False, db=db, current_user=user,
            )

    assert response.code == 0
    assert response.data["photo_count"] == 2
    assert response.data["id"]
    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.start_at == start
    assert added.end_at == end
    assert added.owner_id == user.id


def test_list_hidden_rules_counts_photos_in_each_range():
    user = _user()
    db = MagicMock()
    first, second, _ = _scope()
    rule = SimpleNamespace(
        id=uuid4(), start_at=datetime(2025, 5, 1), end_at=datetime(2025, 5, 8),
    )
    db.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [rule]

    with patch.object(face_api.person_timeline, "scope", return_value=(first, second, [])):
        with patch.object(face_api.person_timeline, "photo_query", return_value=_photo_query(count=4)):
            response = face_api.list_person_timeline_hides(
                id=uuid4(), with_id=None, db=db, current_user=user,
            )

    assert response.code == 0
    assert len(response.data) == 1
    assert response.data[0]["id"] == str(rule.id)
    assert response.data[0]["photo_count"] == 4
    assert response.data[0]["start_at"] == rule.start_at.isoformat()


def test_restore_hidden_rule_deletes_row():
    user = _user()
    db = MagicMock()
    first, second, _ = _scope()
    rule = SimpleNamespace(id=uuid4())
    db.query.return_value.filter_by.return_value.first.return_value = rule

    with patch.object(face_api.person_timeline, "scope", return_value=(first, second, [])):
        response = face_api.restore_person_timeline_segment(
            id=uuid4(), rule_id=rule.id, with_id=None, db=db, current_user=user,
        )

    assert response.code == 0
    assert response.data == {"restored": True}
    db.delete.assert_called_once_with(rule)
    db.commit.assert_called_once()


def test_restore_missing_hidden_rule_returns_404():
    user = _user()
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None

    with patch.object(face_api.person_timeline, "scope", return_value=_scope()):
        with pytest.raises(HTTPException) as exc_info:
            face_api.restore_person_timeline_segment(
                id=uuid4(), rule_id=uuid4(), with_id=None, db=db, current_user=user,
            )

    assert exc_info.value.status_code == 404
    db.delete.assert_not_called()
