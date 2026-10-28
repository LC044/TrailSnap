"""2026-10-28 nightly coverage for ``app/service/memory.py``.

The 2026-10-28 backend coverage scan reported ``service/memory.py`` at 79.6%
with 84 uncovered lines.  The uncovered helpers are the ones that guard the
*content* of a memory:

* ``_normalize_ai_story`` -- strips the model's reasoning and headings and
  trims an over-long story to a whole sentence;
* ``_require_owned`` / ``_owned_photos`` -- the ownership guards that answer
  404 / 400 instead of leaking another user's photos;
* ``_ticket_dict`` -- the "the linked ticket is gone" payloads;
* ``_photo_dict`` -- the client-facing photo payload.

The cases are pure unit tests: a mocked session and simple namespaces.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke, pytest.mark.module_memory]


def _memory_service():
    from app.service import memory

    return memory


# ---------------------------------------------------------------------------
# _normalize_ai_story
# ---------------------------------------------------------------------------


def test_a_short_story_is_kept_as_is():
    memory = _memory_service()
    assert memory._normalize_ai_story("  一次海边散步。  ") == "一次海边散步。"


def test_the_reasoning_block_is_removed():
    memory = _memory_service()
    raw = "<think>模型先分析了事实</think>真正的故事正文。"
    assert memory._normalize_ai_story(raw) == "真正的故事正文。"


def test_a_leading_heading_is_removed():
    memory = _memory_service()
    raw = "# 故事\n\n正文第一段。"
    assert memory._normalize_ai_story(raw) == "正文第一段。"


def test_a_long_story_is_cut_at_a_sentence_boundary():
    memory = _memory_service()
    # The only sentence end inside the 420 character window is at index 400.
    raw = "内容" * 200 + "。" + "补充" * 50
    result = memory._normalize_ai_story(raw)
    assert len(result) <= 421
    assert result.endswith("。")
    assert "补充" not in result


def test_a_long_story_without_punctuation_ends_with_a_full_stop():
    memory = _memory_service()
    raw = "内容" * 300
    result = memory._normalize_ai_story(raw)
    assert len(result) <= 421
    assert result.endswith("。")


def test_a_long_story_with_an_early_sentence_end_keeps_the_window():
    memory = _memory_service()
    # The only sentence end is far too early to be a sensible cut point, so the
    # window is padded with a full stop instead.
    raw = "开始。" + "内容" * 300
    result = memory._normalize_ai_story(raw)
    assert len(result) <= 421
    assert result.endswith("。")


# ---------------------------------------------------------------------------
# ownership guards
# ---------------------------------------------------------------------------


def test_require_owned_raises_for_an_unknown_memory():
    memory = _memory_service()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as excinfo:
        memory._require_owned(db, uuid.uuid4(), uuid.uuid4())
    assert excinfo.value.status_code == 404


def test_owned_photos_returns_nothing_for_an_empty_list():
    memory = _memory_service()
    db = MagicMock()
    assert memory._owned_photos(db, uuid.uuid4(), []) == []
    db.query.assert_not_called()


def test_owned_photos_rejects_a_foreign_photo():
    memory = _memory_service()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    with pytest.raises(HTTPException) as excinfo:
        memory._owned_photos(db, uuid.uuid4(), [uuid.uuid4()])
    assert excinfo.value.status_code == 400


def test_owned_photos_keeps_the_requested_order():
    memory = _memory_service()
    first, second = uuid.uuid4(), uuid.uuid4()
    photos = [
        SimpleNamespace(id=second),
        SimpleNamespace(id=first),
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = photos
    result = memory._owned_photos(db, uuid.uuid4(), [first, second])
    assert [photo.id for photo in result] == [first, second]


def test_owned_photos_deduplicates_the_requested_ids():
    memory = _memory_service()
    photo_id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [SimpleNamespace(id=photo_id)]
    result = memory._owned_photos(db, uuid.uuid4(), [photo_id, photo_id])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# payloads
# ---------------------------------------------------------------------------


def test_photo_dict_maps_the_client_fields():
    memory = _memory_service()
    photo = SimpleNamespace(
        id=uuid.uuid4(),
        filename="a.jpg",
        photo_time=datetime(2024, 5, 6, 7, 8, 9),
        file_type=SimpleNamespace(value="image"),
        width=100,
        height=200,
        metadata_info=SimpleNamespace(city="上海", province="上海"),
    )
    payload = memory._photo_dict(photo)
    assert payload["filename"] == "a.jpg"
    assert payload["photo_time"].startswith("2024-05-06T07:08:09")
    assert payload["file_type"] == "image"
    assert payload["city"] == "上海"


def test_photo_dict_tolerates_missing_metadata():
    memory = _memory_service()
    photo = SimpleNamespace(
        id=uuid.uuid4(),
        filename="a.jpg",
        photo_time=None,
        file_type=None,
        width=None,
        height=None,
        metadata_info=None,
    )
    payload = memory._photo_dict(photo)
    assert payload["photo_time"] is None
    assert payload["file_type"] is None
    assert payload["city"] is None


def test_ticket_dict_marks_an_unknown_ticket_type_as_unavailable():
    memory = _memory_service()
    link = SimpleNamespace(ticket_type="bus", ticket_id=uuid.uuid4(), is_confirmed=True)
    payload = memory._ticket_dict(MagicMock(), link)
    assert payload["unavailable"] is True
    assert payload["type"] == "bus"


def test_ticket_dict_marks_a_deleted_train_ticket_as_unavailable():
    memory = _memory_service()
    link = SimpleNamespace(ticket_type="train", ticket_id=uuid.uuid4(), is_confirmed=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    payload = memory._ticket_dict(db, link)
    assert payload["unavailable"] is True
    assert payload["confirmed"] is False


def test_ticket_dict_marks_a_deleted_flight_ticket_as_unavailable():
    memory = _memory_service()
    link = SimpleNamespace(ticket_type="flight", ticket_id=uuid.uuid4(), is_confirmed=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    payload = memory._ticket_dict(db, link)
    assert payload["unavailable"] is True


def test_ticket_dict_serialises_a_train_ticket():
    memory = _memory_service()
    link = SimpleNamespace(ticket_type="train", ticket_id=uuid.uuid4(), is_confirmed=True)
    row = SimpleNamespace(
        id=link.ticket_id,
        train_code="G1",
        departure_station="上海虹桥",
        arrival_station="北京南",
        date_time=datetime(2024, 5, 6, 7, 0),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    payload = memory._ticket_dict(db, link)
    assert payload["code"] == "G1"
    assert payload["from"] == "上海虹桥"
    assert payload["to"] == "北京南"
    assert payload["unavailable"] if "unavailable" in payload else True

