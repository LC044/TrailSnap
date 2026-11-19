"""2026-11-16 nightly coverage for ``app/service/ticket_wallet.py``.

The 2026-11-16 backend coverage scan reported ``service/ticket_wallet.py``
at 95.3% with 7 missed lines.  The remaining gaps are the import guards:

* ``validate_photo`` refusing a photo the caller does not own (line 20);
* ``import_records`` refusing a record that is not an object (line 32) and
  an unsupported ticket type (line 35);
* ``import_records`` dropping empty optional CSV cells (line 40) and keeping
  the ticket id supplied by the export (line 57);
* ``owned_context`` refusing a malformed UUID (lines 82-83).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.db.models.trip import TrainTicket
from app.service import ticket_wallet


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _query(first=None):
    q = MagicMock(name="query")
    q.filter.return_value = q
    q.first.return_value = first
    return q


def _train_record(**overrides):
    record = {
        "type": "train",
        "train_code": "G1",
        "departure_station": "北京南",
        "arrival_station": "上海虹桥",
        "date_time": "2026-05-01 10:00:00",
        "carriage": "08",
        "seat_num": "12F",
        "price": "553.5",
        "seat_type": "二等座",
        "name": "张三",
    }
    record.update(overrides)
    return record


def test_validate_photo_refuses_a_photo_the_caller_does_not_own():
    db = MagicMock()
    db.query.return_value = _query(first=None)

    with pytest.raises(HTTPException) as excinfo:
        ticket_wallet.validate_photo(db, uuid.uuid4(), uuid.uuid4())

    assert excinfo.value.status_code == 404
    assert "原票图片不存在或无权访问" in excinfo.value.detail


def test_import_records_refuses_a_record_that_is_not_an_object():
    db = MagicMock()

    result = ticket_wallet.import_records(db, uuid.uuid4(), ["not-a-ticket"])

    assert result["success"] == 0
    assert result["failed"] == 1
    assert result["details"]["errors"]


def test_import_records_refuses_an_unsupported_ticket_type():
    db = MagicMock()

    result = ticket_wallet.import_records(db, uuid.uuid4(), [{"type": "ferry"}])

    assert result["success"] == 0
    assert result["failed"] == 1


def test_import_records_drops_empty_cells_and_keeps_the_export_id():
    ticket_id = str(uuid.uuid4())
    db = MagicMock()
    db.query.return_value = _query(first=None)

    record = _train_record(
        id=ticket_id,
        photo_id="",
        berth_type="",
        discount_type="",
        total_running_time="",
        total_mileage="",
    )

    with patch("app.service.journey_queue.enqueue") as enqueue:
        result = ticket_wallet.import_records(db, uuid.uuid4(), [record])

    assert result["success"] == 1
    assert result["failed"] == 0
    enqueue.assert_called_once()

    added = db.add.call_args.args[0]
    assert isinstance(added, TrainTicket)
    assert str(added.id) == ticket_id
    # The empty CSV cells fall back to the schema defaults.
    assert added.berth_type == "无"
    assert added.total_mileage == 0
    assert added.photo_id is None


def test_owned_context_refuses_a_malformed_uuid():
    db = MagicMock()

    with pytest.raises(HTTPException) as excinfo:
        ticket_wallet.owned_context(db, uuid.uuid4(), "album", "not-a-uuid")

    assert excinfo.value.status_code == 422
    assert "关联对象 ID 无效" in excinfo.value.detail

