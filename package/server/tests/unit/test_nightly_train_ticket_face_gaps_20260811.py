"""Unit tests covering the 2026-08-11 nightly coverage gap scan (round 3, file 2).

Modules exercised:
* app/api/train_ticket.py -- read_tickets (list) + export_tickets (json/csv)
* app/api/face.py -- remove_photos_from_identity + set_identity_cover
  + rescan_identity happy / unhappy paths
"""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import face as face_api
from app.api import train_ticket as train_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _ticket(**kwargs):
    base = {
        "id": uuid4(),
        "train_code": "G1234",
        "departure_station": "Beijing",
        "arrival_station": "Shanghai",
        "date_time": datetime(2025, 8, 1, 8, 0, 0),
        "carriage": "05",
        "seat_num": "12A",
        "berth_type": "None",
        "price": 553.5,
        "seat_type": "Second-class",
        "name": "Alice",
        "discount_type": "Full-price",
        "total_running_time": "4h30m",
        "total_mileage": "1318",
        "stop_stations": "[]",
        "comments": "",
        "created_at": datetime(2025, 7, 25, 0, 0, 0),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


# ============================================================================
# app/api/train_ticket.py -- list endpoint + export endpoint
# ============================================================================


def test_read_tickets_returns_paginated_response():
    user = _user()
    db = MagicMock()
    t1, t2 = _ticket(), _ticket()
    # Set the result for the final .all() call on the chain.
    # Any chain that ends in .all() should return this list.
    db.query.return_value.filter.return_value.order_by.return_value.count.return_value = 2
    # Build the rest of the chain so .all() resolves to our list.
    target = db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value
    target.all.return_value = [t1, t2]

    response = train_api.read_tickets(skip=0, limit=10, db=db, current_user=user)

    assert response.code == 200
    assert "items" in response.data


def test_export_tickets_returns_json_when_format_json():
    user = _user()
    db = MagicMock()
    t = _ticket()
    with patch.object(train_api, "get_all_train_tickets", return_value=[t]):
        response = train_api.export_tickets(format="json", db=db, current_user=user)

    assert response.media_type == "application/json"
    payload = json.loads(response.body)
    assert isinstance(payload, list)
    assert payload[0]["train_code"] == "G1234"


def test_export_tickets_returns_empty_csv_when_no_tickets():
    user = _user()
    db = MagicMock()
    with patch.object(train_api, "get_all_train_tickets", return_value=[]):
        response = train_api.export_tickets(format="csv", db=db, current_user=user)

    assert response.media_type == "text/csv"
    assert response.body == b""


def test_export_tickets_returns_csv_with_header_and_row():
    user = _user()
    db = MagicMock()
    t = _ticket()
    with patch.object(train_api, "get_all_train_tickets", return_value=[t]):
        response = train_api.export_tickets(format="csv", db=db, current_user=user)

    assert response.media_type == "text/csv"
    body = response.body.decode("utf-8")
    header_line = body.splitlines()[0]
    assert header_line.startswith("id,train_code,departure_station")
    assert "G1234" in body


# ============================================================================
# app/api/face.py -- remove-photos / cover / rescan branches
# ============================================================================


def test_remove_photos_from_identity_returns_404_when_missing():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_ids=[uuid4()])
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        response = face_api.remove_photos_from_identity(
            id=uuid4(), payload=payload, db=db, current_user=user
        )
    assert response.code == 404
    assert "Identity not found" in response.msg


def test_remove_photos_from_identity_succeeds_when_ok():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_ids=[uuid4(), uuid4()])
    identity = SimpleNamespace(id=uuid4())
    with patch.object(face_api.crud_face, "get_identity", return_value=identity):
        with patch.object(face_api.crud_face, "remove_photos_from_identity", return_value=2):
            with patch("app.crud.album.trigger_conditional_albums_update") as trigger:
                response = face_api.remove_photos_from_identity(
                    id=identity.id, payload=payload, db=db, current_user=user
                )
    assert response.code == 200
    assert response.data == {"status": "success", "count": 2}
    trigger.assert_called_once()


def test_set_identity_cover_returns_404_when_face_missing():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_id=uuid4())
    identity = SimpleNamespace(id=uuid4())
    with patch.object(face_api.crud_face, "get_identity", return_value=identity):
        with patch.object(face_api.crud_face, "set_identity_cover", return_value=False):
            response = face_api.set_identity_cover(
                id=identity.id, payload=payload, db=db, current_user=user
            )
    assert response.code == 404
    assert "Face not found" in response.msg


def test_rescan_identity_returns_404_when_identity_missing():
    user = _user()
    db = MagicMock()
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            face_api.rescan_identity(id=uuid4(), db=db, current_user=user)
    assert exc_info.value.status_code == 404


def test_rescan_identity_calls_face_cluster_service():
    user = _user()
    db = MagicMock()
    identity = SimpleNamespace(id=uuid4())
    expected = {"added": 3, "removed": 1, "affected_photo_ids": []}
    with patch.object(face_api.crud_face, "get_identity", return_value=identity):
        with patch("app.api.face.FaceClusterService") as service_cls:
            service_cls.return_value.rescan_identity.return_value = expected
            with patch("app.crud.album.trigger_conditional_albums_update"):
                response = face_api.rescan_identity(
                    id=identity.id, db=db, current_user=user
                )
    assert response.code == 200
    assert response.data == {"added": 3, "removed": 1}
