"""HTTP-layer coverage for the unified ticket-wallet endpoints.

The matching service-level module ``app.service.ticket_wallet`` is exercised
by ``test_ticket_wallet.py``; this file targets the FastAPI handlers in
``app.api.ticket_wallet`` (``/import``, ``GET /``, ``/contexts``, the per-ticket
``GET``/``DELETE`` pair, and the validation paths of ``/links``) that were left
untouched and dragged the module down to ~55% coverage.
"""
from io import BytesIO
from uuid import uuid4
import json
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.ticket_wallet import router
from app.db.models import Album, TrainTicket, FlightTicket, User
from app.db.models.memory import Memory, MemoryStatus
from app.db.models.ticket_wallet import AlbumTicket
from app.dependencies import get_db
from app.service import ticket_wallet as wallet

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _build_client(db, owner):
    app = FastAPI()
    app.include_router(router, prefix="/api/ticket-wallet")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed(db, *, train=True, flight=True, album=True, memory=True):
    owner = User(id=uuid4(), username="wallet-http", hashed_password="x", is_active=True)
    stranger = User(id=uuid4(), username="wallet-stranger", hashed_password="x", is_active=True)
    db.add_all([owner, stranger])
    db.flush()
    payload = {"owner": owner, "stranger": stranger}
    if album:
        payload["album"] = Album(
            id=uuid4(),
            name="huzhou-memories",
            owner_id=owner.id,
            type="user",
        )
        db.add(payload["album"])
    if memory:
        payload["memory"] = Memory(
            id=uuid4(),
            title="qiandao-weekend",
            owner_id=owner.id,
            status=MemoryStatus.CONFIRMED,
        )
        db.add(payload["memory"])
    if train:
        payload["train_id"] = str(uuid4())
        payload["train"] = TrainTicket(
            id=payload["train_id"],
            owner_id=owner.id,
            train_code="G7556",
            departure_station="Shanghai-Hongqiao",
            arrival_station="Huzhou",
            date_time=datetime(2026, 6, 12, 9, 0),
            carriage="04",
            seat_num="12A",
            price=184,
            seat_type="second-class",
            name="nightrain",
        )
        db.add(payload["train"])
    if flight:
        payload["flight_id"] = str(uuid4())
        payload["flight"] = FlightTicket(
            id=payload["flight_id"],
            owner_id=owner.id,
            flight_code="MU5402",
            departure_city="Shanghai-Hongqiao",
            arrival_city="Hangzhou-Xiaoshan",
            date_time=datetime(2026, 6, 10, 7, 30),
            price=620,
            name="nightrain",
        )
        db.add(payload["flight"])
    db.commit()
    return payload


def test_import_wallet_csv_round_trip_and_rejects_over_size(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=False)
    client = _build_client(db, payload["owner"])
    rows = wallet.list_tickets(db, payload["owner"].id)
    train_row = next(item for item in rows if item["type"] == "train")
    record = wallet.owned_ticket(db, payload["owner"].id, "train", train_row["id"])
    headers = [
        "type", "id", "train_code", "departure_station", "arrival_station",
        "date_time", "carriage", "seat_num", "price", "seat_type", "name",
    ]
    line_values = [
        "train", record.id, record.train_code, record.departure_station,
        record.arrival_station, record.date_time.isoformat(), record.carriage,
        record.seat_num, str(record.price), record.seat_type, record.name,
    ]
    body = (",".join(headers) + "\n" + ",".join(str(value) for value in line_values)).encode("utf-8")
    response = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("wallet.csv", BytesIO(body), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["success"] == 1 and data["failed"] == 0

    oversize = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("big.csv", BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "text/csv")},
    )
    assert oversize.status_code == 413
    assert "10MB" in oversize.json()["detail"]


def test_import_wallet_json_v1_and_legacy_array_and_invalid_extension(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=False, flight=True)
    client = _build_client(db, payload["owner"])
    rows = wallet.list_tickets(db, payload["owner"].id)
    flight_row = next(item for item in rows if item["type"] == "flight")
    record = wallet.owned_ticket(db, payload["owner"].id, "flight", flight_row["id"])
    record_dict = {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
        if column.name not in {"owner_id", "created_at", "updated_at"}
    }
    record_dict["type"] = "flight"
    for decimal_key in ("price", "total_mileage"):
        if decimal_key in record_dict and isinstance(record_dict[decimal_key], Decimal):
            record_dict[decimal_key] = float(record_dict[decimal_key])
    record_dict["date_time"] = record.date_time.isoformat()

    envelope = {"version": 1, "items": [record_dict]}
    response = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("wallet.json", BytesIO(json.dumps(envelope).encode("utf-8")), "application/json")},
    )
    assert response.status_code == 200
    assert response.json()["data"]["success"] == 1

    legacy = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("legacy.json", BytesIO(json.dumps([record_dict]).encode("utf-8")), "application/json")},
    )
    assert legacy.status_code == 200
    assert legacy.json()["data"]["success"] == 1

    bad_version = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("wallet.json", BytesIO(b'{"version": 99, "items": []}'), "application/json")},
    )
    assert bad_version.status_code == 422

    wrong_ext = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("wallet.zip", BytesIO(b"any"), "application/zip")},
    )
    assert wrong_ext.status_code == 422

    too_many = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("huge.json", BytesIO(json.dumps({"version": 1, "items": [{}] * 10001}).encode("utf-8")), "application/json")},
    )
    assert too_many.status_code == 422


def test_import_wallet_garbled_payload_returns_422(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=False)
    client = _build_client(db, payload["owner"])
    response = client.post(
        "/api/ticket-wallet/import",
        files={"file": ("wallet.json", BytesIO(b'{"version": 1, "items": "oops"}'), "application/json")},
    )
    assert response.status_code == 422


def test_list_wallet_paginates_validates_range_and_normalizes_timezone(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=True)
    client = _build_client(db, payload["owner"])

    full = client.get("/api/ticket-wallet/")
    assert full.status_code == 200
    body = full.json()["data"]
    assert body["total"] == 2 and len(body["items"]) == 2

    paged = client.get("/api/ticket-wallet/?skip=1&limit=1")
    assert paged.status_code == 200
    assert len(paged.json()["data"]["items"]) == 1 and paged.json()["data"]["total"] == 2

    narrow = client.get(
        "/api/ticket-wallet/?start=2026-06-10T00:00:00Z&end=2026-06-11T00:00:00Z"
    )
    assert narrow.status_code == 200
    assert narrow.json()["data"]["total"] == 1

    tz_narrow = client.get(
        "/api/ticket-wallet/?start=2026-06-10T08:00:00%2B08:00&end=2026-06-10T23:00:00%2B08:00"
    )
    assert tz_narrow.status_code == 200
    assert tz_narrow.json()["data"]["total"] >= 1

    inverted = client.get(
        "/api/ticket-wallet/?start=2026-06-12T00:00:00Z&end=2026-06-11T00:00:00Z"
    )
    assert inverted.status_code == 422


def test_contexts_returns_albums_and_memories_with_query_and_pagination(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=False, flight=False)
    db.add(Album(id=uuid4(), name="suzhou-weekend", owner_id=payload["owner"].id, type="user"))
    db.add(Album(id=uuid4(), name="conditional-album", owner_id=payload["owner"].id, type="conditional"))
    db.commit()
    client = _build_client(db, payload["owner"])

    albums = client.get("/api/ticket-wallet/contexts?kind=album")
    assert albums.status_code == 200
    titles = sorted(item["title"] for item in albums.json()["data"]["items"])
    assert titles == ["huzhou-memories", "suzhou-weekend"]
    assert albums.json()["data"]["total"] == 2

    memories = client.get("/api/ticket-wallet/contexts?kind=memory")
    assert memories.status_code == 200
    assert memories.json()["data"]["items"][0]["title"] == "qiandao-weekend"

    searched = client.get("/api/ticket-wallet/contexts?kind=memory&q=qiandao")
    assert searched.status_code == 200
    assert searched.json()["data"]["total"] == 1

    paged = client.get("/api/ticket-wallet/contexts?kind=album&skip=1&limit=1")
    assert paged.status_code == 200
    body = paged.json()["data"]
    assert len(body["items"]) == 1 and body["total"] == 2


def test_detail_returns_owned_ticket_and_blocks_foreign_user(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=False)
    owner_client = _build_client(db, payload["owner"])
    response = owner_client.get(f"/api/ticket-wallet/train/{payload['train_id']}")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["type"] == "train"
    assert body["photos"] == []
    assert body["code"] == "G7556"
    assert body["from"] == "Shanghai-Hongqiao"
    assert body["to"] == "Huzhou"

    stranger_app = FastAPI()
    stranger_app.include_router(router, prefix="/api/ticket-wallet")
    stranger_app.dependency_overrides[get_current_user] = lambda: payload["stranger"]
    stranger_app.dependency_overrides[get_db] = lambda: db
    stranger_client = TestClient(stranger_app)
    forbidden = stranger_client.get(f"/api/ticket-wallet/train/{payload['train_id']}")
    assert forbidden.status_code == 404


def test_remove_cleans_only_matching_ticket(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=True)
    client = _build_client(db, payload["owner"])
    response = client.delete(f"/api/ticket-wallet/train/{payload['train_id']}")
    assert response.status_code == 200
    assert response.json()["data"]["deleted"] is True
    listing = client.get("/api/ticket-wallet/")
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["items"][0]["type"] == "flight"


def test_link_tickets_validates_all_refs_before_writing(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=True, album=True)
    client = _build_client(db, payload["owner"])
    body = {
        "tickets": [
            {"type": "train", "id": payload["train_id"]},
            {"type": "flight", "id": "missing-flight"},
        ],
        "context_kind": "album",
        "context_id": str(payload["album"].id),
    }
    response = client.post("/api/ticket-wallet/links", json=body)
    assert response.status_code == 404
    assert db.query(AlbumTicket).count() == 0

    happy = client.post(
        "/api/ticket-wallet/links",
        json={
            "tickets": [{"type": "train", "id": payload["train_id"]}],
            "context_kind": "album",
            "context_id": str(payload["album"].id),
        },
    )
    assert happy.status_code == 200
    assert happy.json()["data"]["updated"] == 1
    assert db.query(AlbumTicket).count() == 1


def test_link_tickets_rejects_foreign_context(face_sqlite_session):
    db = face_sqlite_session
    payload = _seed(db, train=True, flight=False, album=True)
    client = _build_client(db, payload["stranger"])
    response = client.post(
        "/api/ticket-wallet/links",
        json={
            "tickets": [{"type": "train", "id": payload["train_id"]}],
            "context_kind": "album",
            "context_id": str(payload["album"].id),
        },
    )
    assert response.status_code == 404
