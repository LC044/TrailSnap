"""Nightly watch 2026-11-24 — app/service/person_timeline.py 的范围与代表照片补测。

覆盖：
* scope：选同一个人时报 400；人物不存在或不可访问时报 404。
* photo_dict：文件名为空时回退成「照片」。
* representatives：跨不同日期的照片最多取 3 张代表，并在取满后提前结束。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.service import person_timeline


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _photo(photo_id, when, filename="photo.jpg"):
    return SimpleNamespace(id=photo_id, photo_time=when, filename=filename)


def _identity(identity_id):
    return SimpleNamespace(id=identity_id)


def test_scope_rejects_selecting_the_same_person():
    """with_id 与 person_id 相同时直接报 400。"""
    db = MagicMock()
    person_id = uuid.uuid4()

    with pytest.raises(HTTPException) as excinfo:
        person_timeline.scope(db, uuid.uuid4(), person_id, person_id)

    assert excinfo.value.status_code == 400


def test_scope_reports_missing_or_inaccessible_person():
    """人物不存在 / 已删除 / 已隐藏时统一报 404。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with pytest.raises(HTTPException) as excinfo:
        person_timeline.scope(db, uuid.uuid4(), uuid.uuid4(), None)

    assert excinfo.value.status_code == 404


def test_scope_sorts_the_pair_deterministically():
    """双人时间线里的两个身份按 ID 排序，保证 (A,B) 与 (B,A) 落在同一区间。"""
    db = MagicMock()
    first, second = uuid.uuid4(), uuid.uuid4()
    db.query.return_value.filter.return_value.all.return_value = [
        _identity(first),
        _identity(second),
    ]

    low, high, people = person_timeline.scope(db, uuid.uuid4(), first, second)

    assert (str(low), str(high)) == tuple(sorted((str(first), str(second))))
    assert len(people) == 2


def test_photo_dict_falls_back_to_a_generic_filename():
    """照片没有文件名时用「照片」占位。"""
    photo = _photo(uuid.uuid4(), datetime(2026, 7, 1, 10, 0), filename=None)

    payload = person_timeline.photo_dict(photo)

    assert payload["filename"] == "照片"
    assert payload["id"] == str(photo.id)
    assert payload["thumbnail_url"] == f"/api/medias/{photo.id}/thumbnail"


def test_representatives_picks_at_most_three_distinct_days():
    """代表照片最多 3 张，且必须来自不同日期。"""
    db = MagicMock()
    rows = [
        _photo(uuid.uuid4(), datetime(2026, 7, 1, 10, 0)),
        _photo(uuid.uuid4(), datetime(2026, 7, 2, 10, 0)),
        _photo(uuid.uuid4(), datetime(2026, 7, 3, 10, 0)),
        _photo(uuid.uuid4(), datetime(2026, 7, 4, 10, 0)),
    ]
    db.query.return_value.filter.return_value.all.return_value = []

    chosen = person_timeline.representatives(db, rows)

    assert len(chosen) == 3
    days = {row.photo_time.date() for row in chosen}
    assert len(days) == 3


def test_representatives_prefers_higher_scored_photos():
    """有描述评分时，评分更高的照片应排在前面被选中。"""
    db = MagicMock()
    low = _photo(uuid.uuid4(), datetime(2026, 7, 1, 10, 0))
    high = _photo(uuid.uuid4(), datetime(2026, 7, 2, 10, 0))
    rows = [low, high]
    db.query.return_value.filter.return_value.all.return_value = [
        (low.id, 0.1, 0.1),
        (high.id, 1.0, 1.0),
    ]

    chosen = person_timeline.representatives(db, rows)

    assert chosen[0].id == high.id
