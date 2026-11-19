"""2026-11-16 nightly coverage for ``app/service/memory.py``.

The 2026-11-16 backend coverage scan reported ``service/memory.py`` at
94.4% with 23 missed lines.  The remaining gaps are the *confirmed* write
paths and the candidate housekeeping:

* ``_set_tickets`` refusing a ticket the caller does not own (line 286);
* ``update()`` validating and applying a user chosen cover (lines 325-329);
* ``update()`` re-linking confirmed people and tickets (lines 341 / 343);
* ``remove_photos()`` moving the cover to a surviving photo (lines 387-388);
* ``_choose_cover`` picking the best scored photo (line 406);
* ``_retire_legacy_candidates`` retiring candidates of an old algorithm
  version (lines 420-424);
* ``_enrich_people`` recording the "people" evidence (line 443);
* ``_attach_tickets`` bailing out without a time range (line 452) and
  skipping dismissed flights while recording evidence (lines 461-466);
* ``discover()`` labelling a multi-day segment (line 553);
* ``split()`` refusing a memory whose status cannot be split (line 712).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.db.models.memory import MemoryStatus, MemoryOrigin, Memory
from app.db.models.photo import Photo
from app.db.models.trip import FlightTicket, TrainTicket
from app.db.models.ticket_wallet import TicketDismissal
from app.schemas.memory import MemorySplitRequest, MemoryUpdate
from app.service import memory as memory_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _query(rows=None, *, first=None):
    """A minimal stand-in for a SQLAlchemy query used by the helpers."""
    q = MagicMock(name="query")
    q.filter.return_value = q
    q.options.return_value = q
    q.join.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.with_for_update.return_value = q
    q.all.return_value = list(rows or [])
    q.first.return_value = first
    q.__iter__.side_effect = lambda: iter(list(rows or []))
    return q


# ---------------------------------------------------------------------------
# _set_tickets / update()
# ---------------------------------------------------------------------------


def test_set_tickets_rejects_a_ticket_the_caller_does_not_own():
    db = MagicMock()
    db.query.return_value = _query(first=None)
    memory = SimpleNamespace(tickets=[])

    with pytest.raises(HTTPException) as excinfo:
        memory_service._set_tickets(db, memory, uuid.uuid4(), [{"type": "train", "id": str(uuid.uuid4())}], confirmed=True)

    assert excinfo.value.status_code == 400
    assert "票据不存在或不属于当前用户" in excinfo.value.detail


def test_update_applies_a_user_chosen_cover():
    photo_id = uuid.uuid4()
    memory = SimpleNamespace(
        id=uuid.uuid4(), title="旧标题", title_source="system", story=None, story_source="system",
        cover_photo_id=None, cover_source=None, start_time=None, end_time=None, time_source=None,
        photo_links=[SimpleNamespace(photo_id=photo_id)], people=[], places=[], tickets=[],
        version=1,
    )
    db = MagicMock()
    payload = MemoryUpdate(cover_photo_id=photo_id)

    with patch.object(memory_service, "get_detail", side_effect=lambda *a, **k: memory):
        memory_service.update(db, memory, uuid.uuid4(), payload)

    assert memory.cover_photo_id == photo_id
    assert memory.cover_source == "user"
    assert memory.version == 2


def test_update_rejects_a_cover_outside_the_memory_photos():
    memory = SimpleNamespace(
        id=uuid.uuid4(), title="旧标题", title_source="system", story=None, story_source="system",
        cover_photo_id=None, cover_source=None, start_time=None, end_time=None, time_source=None,
        photo_links=[SimpleNamespace(photo_id=uuid.uuid4())], people=[], places=[], tickets=[],
        version=1,
    )
    db = MagicMock()
    payload = MemoryUpdate(cover_photo_id=uuid.uuid4())

    with pytest.raises(HTTPException) as excinfo:
        memory_service.update(db, memory, uuid.uuid4(), payload)

    assert excinfo.value.status_code == 400
    assert "封面必须属于记忆照片" in excinfo.value.detail


def test_update_relinks_confirmed_people_and_tickets():
    person_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    identity = SimpleNamespace(id=person_id, owner_id=None, is_deleted=False)
    ticket = SimpleNamespace(id=ticket_id, owner_id=None)

    def query(*args, **kwargs):
        model = args[0] if args else None
        if model is TrainTicket:
            return _query(first=ticket)
        return _query([identity])

    db = MagicMock()
    db.query.side_effect = query
    memory = SimpleNamespace(
        id=uuid.uuid4(), title="旧标题", title_source="system", story=None, story_source="system",
        cover_photo_id=None, cover_source=None, start_time=None, end_time=None, time_source=None,
        photo_links=[], people=[], places=[], tickets=[], version=1,
    )
    payload = MemoryUpdate(person_ids=[person_id], ticket_refs=[{"type": "train", "id": str(ticket_id)}])

    with patch.object(memory_service, "get_detail", side_effect=lambda *a, **k: memory):
        memory_service.update(db, memory, uuid.uuid4(), payload)

    assert [person.is_confirmed for person in memory.people] == [True]
    assert [link.is_confirmed for link in memory.tickets] == [True]
    assert [link.source for link in memory.tickets] == ["user"]


# ---------------------------------------------------------------------------
# remove_photos / _choose_cover / _retire_legacy_candidates
# ---------------------------------------------------------------------------


def test_remove_photos_moves_the_cover_to_a_surviving_photo():
    first, second = uuid.uuid4(), uuid.uuid4()
    memory = SimpleNamespace(
        id=uuid.uuid4(), cover_photo_id=first, cover_source="user", version=1,
        photo_links=[SimpleNamespace(photo_id=first), SimpleNamespace(photo_id=second)],
    )
    db = MagicMock()

    with patch.object(memory_service, "get_detail", side_effect=lambda *a, **k: memory):
        memory_service.remove_photos(db, memory, uuid.uuid4(), [first])

    assert memory.cover_photo_id == second
    assert memory.cover_source == "system"


def test_choose_cover_picks_the_best_scoring_photo():
    low, high = uuid.uuid4(), uuid.uuid4()
    db = MagicMock()
    db.query.return_value = _query([
        SimpleNamespace(photo_id=low, memory_score=0.1, quality_score=0.2),
        SimpleNamespace(photo_id=high, memory_score=0.9, quality_score=0.8),
    ])

    assert memory_service._choose_cover(db, [low, high]) == high


def test_choose_cover_falls_back_to_the_first_photo_without_descriptions():
    photo_id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value = _query([])

    assert memory_service._choose_cover(db, [photo_id]) == photo_id


def test_retire_legacy_candidates_marks_old_candidates_as_deleted():
    owner_id = uuid.uuid4()
    legacy = SimpleNamespace(status=MemoryStatus.CANDIDATE, deleted_at=None, candidate_fingerprint="abc")
    db = MagicMock()
    db.query.return_value = _query([legacy])

    assert memory_service._retire_legacy_candidates(db, owner_id) == 1
    assert legacy.status == MemoryStatus.DELETED
    assert legacy.deleted_at is not None
    assert legacy.candidate_fingerprint is None
    db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# _enrich_people / _attach_tickets
# ---------------------------------------------------------------------------


def test_enrich_people_records_the_people_evidence():
    identity_id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value = _query([SimpleNamespace(face_identity_id=identity_id, count=3)])
    memory = SimpleNamespace(people=[], evidence=[])

    memory_service._enrich_people(db, memory, uuid.uuid4(), [uuid.uuid4()])

    assert len(memory.people) == 1
    assert memory.people[0].source == "inferred"
    assert len(memory.evidence) == 1
    assert memory.evidence[0].evidence_type == "people"


def test_enrich_people_without_repeated_people_records_no_evidence():
    db = MagicMock()
    db.query.return_value = _query([])
    memory = SimpleNamespace(people=[], evidence=[])

    memory_service._enrich_people(db, memory, uuid.uuid4(), [uuid.uuid4()])

    assert memory.people == []
    assert memory.evidence == []


def test_attach_tickets_without_a_flight_records_no_evidence():
    memory = SimpleNamespace(
        start_time=datetime(2026, 5, 1, 10, 0), end_time=datetime(2026, 5, 1, 12, 0),
        id=uuid.uuid4(), tickets=[], evidence=[],
    )

    def query(*args, **kwargs):
        return _query([])

    db = MagicMock()
    db.query.side_effect = query

    memory_service._attach_tickets(db, memory, uuid.uuid4())

    assert memory.tickets == []
    assert memory.evidence == []


def test_attach_tickets_returns_early_without_a_time_range():
    memory = SimpleNamespace(start_time=None, end_time=None, tickets=[], evidence=[])
    db = MagicMock()

    memory_service._attach_tickets(db, memory, uuid.uuid4())

    assert memory.tickets == []
    assert memory.evidence == []
    db.query.assert_not_called()


def test_attach_tickets_skips_dismissed_flights_and_records_evidence():
    kept, dismissed = uuid.uuid4(), uuid.uuid4()
    memory = SimpleNamespace(
        start_time=datetime(2026, 5, 1, 10, 0), end_time=datetime(2026, 5, 1, 12, 0),
        id=uuid.uuid4(), tickets=[], evidence=[],
    )

    def query(*args, **kwargs):
        model = args[0] if args else None
        if model is TicketDismissal:
            return _query([SimpleNamespace(ticket_type="flight", ticket_id=dismissed)])
        return _query([SimpleNamespace(id=kept), SimpleNamespace(id=dismissed)])

    db = MagicMock()
    db.query.side_effect = query

    memory_service._attach_tickets(db, memory, uuid.uuid4())

    assert [link.ticket_id for link in memory.tickets] == [kept]
    assert len(memory.evidence) == 1
    assert memory.evidence[0].evidence_type == "ticket"


# ---------------------------------------------------------------------------
# discover() / split()
# ---------------------------------------------------------------------------


def test_discover_labels_a_segment_that_spans_two_days():
    owner_id = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()
    start = datetime(2026, 5, 1, 23, 0)
    end = datetime(2026, 5, 2, 1, 0)
    photos = [
        SimpleNamespace(id=first, photo_time=start, owner_id=owner_id, is_deleted=False, image_type=None),
        SimpleNamespace(id=second, photo_time=end, owner_id=owner_id, is_deleted=False, image_type=None),
    ]
    metadata = [
        SimpleNamespace(photo_id=first, city="北京"),
        SimpleNamespace(photo_id=second, city="北京"),
    ]

    def query(*args, **kwargs):
        model = args[0] if args else None
        if model is Memory:
            return _query(first=None)
        if model is Photo:
            return _query(list(zip(photos, metadata)))
        return _query([])

    db = MagicMock()
    db.query.side_effect = query

    with patch.object(memory_service, "_enrich_people"), \
            patch.object(memory_service, "_attach_tickets"), \
            patch("app.service.journey.discover", return_value=[]), \
            patch.object(memory_service, "get_detail", side_effect=lambda *a, **k: MagicMock()):
        created = memory_service.discover(db, owner_id, min_photos=2, max_candidates=5)

    assert len(created) == 1
    # discover() returns the reloaded rows, so inspect the persisted candidate.
    added = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Memory)]
    assert len(added) == 1
    assert "至" in added[0].title


def test_split_refuses_a_memory_whose_status_cannot_be_split():
    memory = SimpleNamespace(status=MemoryStatus.DELETED)
    db = MagicMock()
    db.query.return_value = _query(first=memory)

    payload = MemorySplitRequest(parts=[
        {"title": "第一部分", "photo_ids": [str(uuid.uuid4())]},
        {"title": "第二部分", "photo_ids": [str(uuid.uuid4())]},
    ])

    with pytest.raises(HTTPException) as excinfo:
        memory_service.split(db, uuid.uuid4(), uuid.uuid4(), payload)

    assert excinfo.value.status_code == 400
    assert "当前状态不能拆分" in excinfo.value.detail


