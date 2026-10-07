"""Wallet ownership, relationship lifecycle, and transport format regressions."""
from datetime import datetime
from uuid import uuid4
import importlib.util
from pathlib import Path
from io import StringIO

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db.models import User, Album, TrainTicket, FlightTicket
from app.db.models.memory import Memory, MemoryStatus, MemoryTicket
from app.db.models.ticket_wallet import AlbumTicket, TicketDismissal
from app.db.models.photo import Photo, FileType
from app.db.models.album import AlbumPhoto
from app.db.models.memory import MemoryPhoto
from app.service import ticket_wallet as wallet
from app.api.ticket_wallet import LinkRequest, link_tickets

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


@pytest.fixture
def scenario(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="wallet-owner", hashed_password="x")
    stranger = User(id=uuid4(), username="wallet-other", hashed_password="x")
    db.add_all([owner, stranger]); db.flush()
    album = Album(id=uuid4(), name="杭州之旅", owner_id=owner.id, type="user")
    memory = Memory(id=uuid4(), title="西湖回忆", owner_id=owner.id, status=MemoryStatus.CONFIRMED)
    shared_id = str(uuid4())
    train = TrainTicket(id=shared_id, owner_id=owner.id, train_code="G1", departure_station="北京南", arrival_station="杭州东", date_time=datetime(2026, 6, 12, 9), carriage="3", seat_num="4A", price=100, seat_type="二等座", name="旅人")
    flight = FlightTicket(id=shared_id, owner_id=owner.id, flight_code="MU1", departure_city="上海", arrival_city="杭州", date_time=datetime(2026, 6, 10, 9), price=200, name="旅人")
    db.add_all([album, memory, train, flight]); db.commit()
    return db, owner, stranger, album, memory, train, flight


def test_composite_identity_and_bidirectional_links(scenario):
    db, owner, _, album, memory, train, flight = scenario
    wallet.set_link(db, owner.id, "train", train.id, "album", album.id, True)
    wallet.set_link(db, owner.id, "flight", flight.id, "memory", memory.id, True)
    db.commit()
    items = wallet.list_tickets(db, owner.id)
    assert len({item["key"] for item in items}) == 2
    assert wallet.list_tickets(db, owner.id, album_id=str(album.id))[0]["type"] == "train"
    assert wallet.list_tickets(db, owner.id, memory_id=str(memory.id))[0]["type"] == "flight"
    assert not items[0]["memories"]


def test_link_is_idempotent_and_unlink_preserves_entities(scenario):
    db, owner, _, album, memory, train, _ = scenario
    for _ in range(2):
        wallet.set_link(db, owner.id, "train", train.id, "album", album.id, True)
    assert db.query(AlbumTicket).count() == 1
    wallet.set_link(db, owner.id, "train", train.id, "album", album.id, False)
    db.commit()
    assert db.query(AlbumTicket).count() == 0
    assert db.get(TrainTicket, train.id) and db.get(Album, album.id) and db.get(Memory, memory.id)


def test_candidate_exclusion_and_confirmation(scenario):
    db, owner, _, _, memory, train, _ = scenario
    db.add(MemoryTicket(memory_id=memory.id, ticket_type="train", ticket_id=train.id, is_confirmed=False)); db.commit()
    item = wallet.list_tickets(db, owner.id)[0]
    assert not item["memories"] and len(item["candidates"]) == 1
    wallet.set_link(db, owner.id, "train", train.id, "memory", memory.id, False); db.commit()
    assert db.query(TicketDismissal).count() == 1
    assert not wallet.list_tickets(db, owner.id)[0]["candidates"]
    wallet.set_link(db, owner.id, "train", train.id, "memory", memory.id, True); db.commit()
    assert db.query(TicketDismissal).count() == 0
    assert len(wallet.list_tickets(db, owner.id)[0]["memories"]) == 1


def test_foreign_owner_and_generated_album_cannot_be_linked(scenario):
    db, owner, stranger, album, _, train, _ = scenario
    with pytest.raises(HTTPException) as error:
        wallet.set_link(db, stranger.id, "train", train.id, "album", album.id, True)
    assert error.value.status_code == 404
    album.type = "conditional"; db.commit()
    with pytest.raises(HTTPException) as error:
        wallet.set_link(db, owner.id, "train", train.id, "album", album.id, True)
    assert error.value.status_code == 403
    assert wallet.list_tickets(db, stranger.id) == []


def test_batch_validates_all_references_before_writing(scenario):
    db, owner, _, album, _, train, _ = scenario
    payload = LinkRequest(tickets=[{"type": "train", "id": train.id}, {"type": "flight", "id": "missing"}], context_kind="album", context_id=str(album.id))
    with pytest.raises(HTTPException):
        link_tickets(payload, db, owner)
    assert db.query(AlbumTicket).count() == 0


def test_delete_cleans_only_matching_type_and_keeps_experiences(scenario):
    db, owner, _, album, memory, train, flight = scenario
    for kind in ("train", "flight"):
        wallet.set_link(db, owner.id, kind, train.id, "album", album.id, True)
        wallet.set_link(db, owner.id, kind, train.id, "memory", memory.id, True)
    wallet.delete_ticket(db, owner.id, "train", train.id); db.commit()
    assert not db.get(TrainTicket, train.id)
    assert db.get(FlightTicket, flight.id)
    assert db.query(AlbumTicket).one().ticket_type == "flight"
    assert db.query(MemoryTicket).one().ticket_type == "flight"
    assert db.get(Album, album.id) and db.get(Memory, memory.id)


def test_import_roundtrip_mixed_types_and_foreign_owner_protection(scenario):
    db, owner, stranger, _, _, train, _ = scenario
    records = []
    for item in wallet.list_tickets(db, owner.id):
        kind = item["type"]
        row = wallet.owned_ticket(db, owner.id, kind, item["id"])
        records.append({column.name: getattr(row, column.name) for column in row.__table__.columns if column.name not in {"owner_id", "created_at", "updated_at"}} | {"type": kind})
    result = wallet.import_records(db, owner.id, records)
    assert result["success"] == 2 and result["details"]["updated"] == 2
    assert wallet.import_records(db, stranger.id, records)["failed"] == 2
    assert db.get(TrainTicket, train.id).owner_id == owner.id


def test_temporal_candidate_range_is_half_open(scenario):
    db, owner, *_ = scenario
    assert len(wallet.list_tickets(db, owner.id, start=datetime(2026,6,10), end=datetime(2026,6,12))) == 1
    assert len(wallet.list_tickets(db, owner.id, start=datetime(2026,6,12,9), end=datetime(2026,6,13))) == 1


def test_related_photos_deduplicate_and_ticket_deletion_preserves_original(scenario):
    db, owner, _, album, memory, train, _ = scenario
    photo = Photo(id=uuid4(), owner_id=owner.id, filename="original.jpg", file_path="/original.jpg", file_type=FileType.image, photo_time=datetime(2026,6,12), upload_time=datetime(2026,6,12), size=100, is_deleted=False)
    db.add(photo); db.flush()
    train.photo_id = photo.id
    db.add_all([AlbumPhoto(album_id=album.id, photo_id=photo.id), MemoryPhoto(memory_id=memory.id, photo_id=photo.id)])
    wallet.set_link(db, owner.id, "train", train.id, "album", album.id, True)
    wallet.set_link(db, owner.id, "train", train.id, "memory", memory.id, True)
    db.commit()
    assert len(wallet.related_photos(db, owner.id, "train", train.id)) == 1
    wallet.delete_ticket(db, owner.id, "train", train.id); db.commit()
    assert db.get(Photo, photo.id) and db.query(AlbumPhoto).count() == 1 and db.query(MemoryPhoto).count() == 1


def test_import_keeps_fractional_train_mileage(scenario):
    db, owner, _, _, _, train, _ = scenario
    row = {column.name: getattr(train, column.name) for column in train.__table__.columns if column.name not in {"owner_id", "created_at", "updated_at"}}
    row["total_mileage"] = "123.4"
    result = wallet.import_records(db, owner.id, [row])
    assert result["success"] == 1
    assert float(db.get(TrainTicket, train.id).total_mileage) == 123.4


@pytest.mark.parametrize("branch,filename", [("alembic", "e15669e7cb95_ticket_wallet_associations.py"), ("alembic_sqlite", "de268f1b37fe_ticket_wallet_associations.py")])
def test_wallet_migrations_compile_postgresql_and_roundtrip_sqlite(face_sqlite_session, branch, filename):
    root = Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location("wallet_migration", root / branch / "versions" / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        module.upgrade(); module.downgrade()
    assert "CREATE TABLE album_tickets" in output.getvalue() and "UUID" in output.getvalue()
    db = face_sqlite_session
    with db.bind.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.downgrade(); module.upgrade()
        assert "album_tickets" in inspect(connection).get_table_names()
