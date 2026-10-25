from datetime import datetime, timedelta
from types import ModuleType
from uuid import uuid4
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.memory import Memory, MemoryStatus
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.trip import TrainTicket
from app.db.models.user import User
from app.schemas.train_ticket import TrainTicketCreate, TrainTicketUpdate
from app.service import journey
from app.service.journey_queue import enqueue

pytestmark = [pytest.mark.smoke, pytest.mark.module_album, pytest.mark.module_photo, pytest.mark.module_ticket]
DEPARTURE = datetime(2026, 10, 1, 12)


@pytest.fixture
def railway(tmp_path, monkeypatch):
    from railway.db.models.models import Station
    engine = create_engine(f"sqlite:///{(tmp_path / 'railway.sqlite').as_posix()}")
    Station.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            Station(telecode="HGH", station_name="杭州东", station_pinyin="hangzhoudong",
                    station_py="hzd", province="浙江省", city="杭州"),
            Station(telecode="SHA", station_name="上海虹桥", station_pinyin="shanghaihongqiao",
                    station_py="shhq", province="上海市", city="上海"),
        ])
        db.commit()
    module = ModuleType("railway.db.session")
    module.SessionLocal = factory
    monkeypatch.setitem(sys.modules, "railway.db.session", module)
    yield factory
    engine.dispose()


@pytest.fixture
def railway_with_alias(tmp_path, monkeypatch):
    """12306 改名站：canonical 是新名，旧名挂在 alias_names。"""
    from railway.db.models.models import Station
    if not hasattr(Station, "alias_names"):
        pytest.skip("当前 railway schema 不包含 alias_names")
    engine = create_engine(f"sqlite:///{(tmp_path / 'railway.sqlite').as_posix()}")
    Station.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            Station(telecode="HGH", station_name="杭州东", station_pinyin="hangzhoudong",
                    station_py="hzd", province="浙江省", city="杭州"),
            Station(telecode="KAW", station_name="开江南", station_pinyin="kaijiangnan",
                    station_py="kjn", province="四川省", city="达州",
                    **({"alias_names": ["开江"]} if hasattr(Station, "alias_names") else {})),
        ])
        db.commit()
    module = ModuleType("railway.db.session")
    module.SessionLocal = factory
    monkeypatch.setitem(sys.modules, "railway.db.session", module)
    yield factory
    engine.dispose()


def user(db):
    row = User(id=uuid4(), username=str(uuid4()), hashed_password="x")
    db.add(row)
    db.commit()
    return row


def ticket(db, owner, **kwargs):
    values = dict(id=str(uuid4()), owner_id=owner.id, train_code="G1", date_time=DEPARTURE,
                  departure_station="杭州东", arrival_station="上海虹桥", carriage="1",
                  seat_num="1A", price=100, seat_type="二等座", name="测试乘客")
    values.update(kwargs)
    row = TrainTicket(**values)
    db.add(row)
    db.flush()
    return row


def photo(db, owner, hours, city="杭州", province="浙江省", **kwargs):
    row = Photo(id=uuid4(), owner_id=owner.id, filename="trip.jpg", file_path="/test/trip.jpg",
                file_type=FileType.image, photo_time=DEPARTURE + timedelta(hours=hours),
                is_deleted=False, **kwargs)
    db.add(row)
    db.flush()
    db.add(PhotoMetadata(photo_id=row.id, city=city, province=province))
    db.flush()
    return row


def test_endpoint_city_time_boundaries_and_ownership(face_sqlite_session, railway):
    db = face_sqlite_session
    owner, stranger = user(db), user(db)
    source = photo(db, owner, -2)
    t = ticket(db, owner, departure_station="杭州东站", photo_id=source.id)
    before = photo(db, owner, -24, city="杭州市")
    after = photo(db, owner, 48, city="上海市", province="上海市")
    for hours, city, province in [(-25,"杭州","浙江省"), (49,"上海","上海市"),
                                  (1,"杭州","浙江省"), (-1,"上海","上海市"),
                                  (-1,"杭州","其他省"), (-1,None,"浙江省")]:
        photo(db, owner, hours, city, province)
    photo(db, stranger, -1)
    photo(db, owner, -1, image_type=ImageType.SCREENSHOT)
    removed = photo(db, owner, -1)
    removed.is_deleted = True
    db.commit()
    rows = journey.discover(db, owner.id)
    db.commit()
    assert len(rows) == 1
    row = rows[0]
    assert {link.photo_id for link in row.photo_links} == {before.id, after.id}
    assert row.tickets[0].ticket_id == t.id
    assert row.status == MemoryStatus.CANDIDATE
    assert {e.payload.get("side") for e in row.evidence if e.evidence_type == "place"} == {"departure", "arrival"}
    assert all(not link.is_confirmed for link in row.photo_links + row.tickets)


def test_renamed_station_alias_resolves_both_names(face_sqlite_session, railway_with_alias):
    """票面用旧名（开江）和新名（开江南）都应解析到同一省市。"""
    db = face_sqlite_session
    owner = user(db)
    stations = journey.load_stations({"开江", "开江南", "杭州东"})
    assert stations["开江"] == ("四川省", "达州")
    assert stations["开江南"] == ("四川省", "达州")
    assert stations["杭州东"] == ("浙江省", "杭州")


def test_old_station_name_on_ticket_still_discovers(face_sqlite_session, railway_with_alias):
    db = face_sqlite_session
    owner = user(db)
    source = photo(db, owner, -2)
    t = ticket(db, owner, departure_station="开江", arrival_station="杭州东", photo_id=source.id)
    before = photo(db, owner, -24, city="达州", province="四川省")
    db.commit()
    rows = journey.discover(db, owner.id)
    db.commit()
    assert len(rows) == 1
    assert rows[0].title.endswith("达州 → 杭州")
    assert rows[0].tickets[0].ticket_id == t.id


def test_arrival_duration_handles_overnight(face_sqlite_session, railway):
    db = face_sqlite_session
    owner = user(db)
    ticket(db, owner, total_running_time=15*60)
    too_early = photo(db, owner, 14, "上海", "上海市")
    after = photo(db, owner, 15, "上海", "上海市")
    last = photo(db, owner, 63, "上海", "上海市")
    db.commit()
    row = journey.discover(db, owner.id)[0]
    assert {x.photo_id for x in row.photo_links} == {after.id, last.id}
    assert too_early.id not in {x.photo_id for x in row.photo_links}
    assert row.evidence[0].payload["after_anchor"] == "estimated_arrival"


def test_refresh_is_idempotent_and_photo_can_arrive_later(face_sqlite_session, railway):
    db = face_sqlite_session
    owner = user(db)
    ticket(db, owner)
    db.commit()
    assert journey.discover(db, owner.id) == []
    first = photo(db, owner, -1)
    db.commit()
    row = journey.discover(db, owner.id)[0]
    db.commit()
    second = photo(db, owner, 1, "上海", "上海市")
    db.commit()
    assert journey.discover(db, owner.id) == []
    db.commit()
    assert db.query(Memory).count() == 1
    assert {x.photo_id for x in row.photo_links} == {first.id, second.id}
    assert journey.discover(db, owner.id) == []
    db.commit()  # Unique association constraints must still hold.
    assert len(row.tickets) == 1


@pytest.mark.parametrize("decision", ["confirmed", "ignored", "edited", "removed"])
def test_user_decisions_survive_refresh(face_sqlite_session, railway, decision):
    from app.service import memory as memories
    from app.service import ticket_wallet
    db = face_sqlite_session
    owner = user(db)
    t = ticket(db, owner)
    first = photo(db, owner, -2)
    second = photo(db, owner, -1)
    db.commit()
    row = journey.discover(db, owner.id)[0]
    db.commit()
    if decision in ("confirmed", "ignored"):
        memories.change_status(db, row, MemoryStatus(decision))
    elif decision == "edited":
        from app.schemas.memory import MemoryUpdate
        memories.update(db, row, owner.id, MemoryUpdate(title="用户的标题"))
    else:
        memories.remove_photos(db, row, owner.id, [second.id])
    photo(db, owner, 1, "上海", "上海市")
    db.commit()
    journey.discover(db, owner.id)
    db.commit()
    assert len(row.photo_links) == (1 if decision == "removed" else 2)
    if decision == "edited":
        assert row.title == "用户的标题"
    if decision == "confirmed":
        ticket_wallet.set_link(db, owner.id, "train", t.id, "memory", row.id, False)
        db.commit()
        journey.discover(db, owner.id)
        assert row.tickets == []


def test_missing_station_and_incomplete_time_are_skipped(face_sqlite_session, railway):
    db = face_sqlite_session
    owner = user(db)
    ticket(db, owner, departure_station="不存在的站")
    ticket(db, owner, date_time=datetime(1900, 1, 1))
    photo(db, owner, -1)
    db.commit()
    assert journey.discover(db, owner.id) == []


def test_ambiguous_station_is_not_guessed(railway):
    from railway.db.models.models import Station
    with railway() as db:
        db.add(Station(telecode="XYZ", station_name="杭州东", station_pinyin="x", station_py="x",
                       province="其他省", city="其他城"))
        db.commit()
    assert "杭州东" not in journey.load_stations({"杭州东"})


def test_queue_coalesces_pending_but_preserves_changes_during_processing(face_sqlite_session):
    db = face_sqlite_session
    owner = user(db)
    first = enqueue(db, owner.id)
    assert enqueue(db, owner.id) is first
    db.commit()
    assert enqueue(db, owner.id).id == first.id
    first.status = TaskStatus.PROCESSING
    db.flush()
    second = enqueue(db, owner.id)
    assert second is not first
    db.commit()
    assert db.query(Task).count() == 2
    second.status = TaskStatus.COMPLETED
    db.commit()
    enqueue(db, owner.id)
    db.rollback()
    assert db.query(Task).count() == 2


def test_ticket_crud_enqueues_transactional_work(face_sqlite_session, railway):
    from app.crud.train_ticket import create_train_ticket, update_train_ticket
    db = face_sqlite_session
    owner = user(db)
    p = photo(db, owner, -1)
    db.commit()
    values = dict(train_code="G1", date_time=DEPARTURE, departure_station="杭州东",
                  arrival_station="上海虹桥", carriage="1", seat_num="1A", price=100,
                  seat_type="二等座", name="测试乘客")
    t = create_train_ticket(db, TrainTicketCreate(**values), owner_id=owner.id)
    assert db.query(Task).filter(Task.type == TaskType.ASSOCIATE_JOURNEYS).count() == 1
    row = journey.discover(db, owner.id)[0]
    db.commit()
    assert row.photo_links[0].photo_id == p.id
    update_train_ticket(db, t.id, TrainTicketUpdate(date_time=DEPARTURE+timedelta(days=10)))
    journey.discover(db, owner.id)
    db.commit()
    assert row.status == MemoryStatus.SUPERSEDED


def test_memory_discovery_preserves_journey_candidates_and_uses_same_service(face_sqlite_session, railway):
    from app.service import memory as memories
    db = face_sqlite_session
    owner = user(db)
    ticket(db, owner)
    photo(db, owner, -1)
    db.commit()
    row = memories.discover(db, owner.id)[0]
    assert row.algorithm_version == journey.ALGORITHM_VERSION
    assert memories.discover(db, owner.id) == []
    assert row.status == MemoryStatus.CANDIDATE


def test_railway_failure_does_not_break_ticket_save_or_photo_memory_discovery(face_sqlite_session, monkeypatch):
    from app.crud.train_ticket import create_train_ticket
    from app.service import memory as memories
    db = face_sqlite_session
    owner = user(db)
    for i in range(5):
        photo(db, owner, -1 + i/10)
    db.commit()
    def fail(_):
        raise RuntimeError("railway unavailable")
    monkeypatch.setattr(journey, "load_stations", fail)
    values = dict(train_code="G1", date_time=DEPARTURE, departure_station="杭州东",
                  arrival_station="上海虹桥", carriage="1", seat_num="1A", price=100,
                  seat_type="二等座", name="测试乘客")
    create_train_ticket(db, TrainTicketCreate(**values), owner_id=owner.id)
    assert db.query(TrainTicket).count() == 1
    rows = memories.discover(db, owner.id)
    assert len(rows) == 1
    assert rows[0].algorithm_version == memories.ALGORITHM_VERSION


def test_metadata_completion_and_manual_edit_enqueue_work(face_sqlite_session, railway, monkeypatch):
    from app.crud.photo import update_photo_metadata, update_photo
    from app.schemas.metadata import PhotoMetadataUpdate
    from app.schemas.photo import PhotoUpdate
    from app.service.tasks.metadata import update_photo_metadata_from_extract
    db = face_sqlite_session
    owner = user(db)
    ticket(db, owner)
    p = photo(db, owner, -1, city=None)
    db.commit()
    assert journey.discover(db, owner.id) == []
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    update_photo_metadata(db, p.id, PhotoMetadataUpdate(city="杭州市", province="浙江省"), owner.id)
    assert db.query(Task).filter(Task.type == TaskType.ASSOCIATE_JOURNEYS).count() == 1
    row = journey.discover(db, owner.id)[0]
    db.commit()
    assert row.photo_links[0].photo_id == p.id
    update_photo(db, p.id, PhotoUpdate(photo_time=DEPARTURE+timedelta(days=10)), owner.id)
    journey.discover(db, owner.id)
    db.commit()
    assert row.status == MemoryStatus.SUPERSEDED
    # Metadata batch writers pass commit=False: the task must be part of that
    # transaction rather than a separately committed side effect.
    db.query(Task).delete()
    db.commit()
    update_photo_metadata_from_extract(db, p, {"photo_time": DEPARTURE-timedelta(hours=1)}, commit=False)
    db.flush()
    assert db.query(Task).count() == 1
    db.rollback()
    assert db.query(Task).count() == 0


def test_wallet_import_and_worker_use_shared_matcher(face_sqlite_session, railway):
    from app.service.ticket_wallet import import_records
    from app.service.tasks.journey import _run
    db = face_sqlite_session
    owner = user(db)
    p = photo(db, owner, -1)
    db.commit()
    result = import_records(db, owner.id, [{
        "type": "train", "train_code": "G1", "date_time": DEPARTURE.isoformat(),
        "departure_station": "杭州东", "arrival_station": "上海虹桥",
        "carriage": "1", "seat_num": "1A", "price": 100,
        "seat_type": "二等座", "name": "测试乘客",
    }])
    assert result["success"] == 1
    assert db.query(Task).count() == 1
    db.commit()
    assert _run(db.get_bind(), owner.id)["created"] == 1
    db.expire_all()
    row = db.query(Memory).one()
    assert row.photo_links[0].photo_id == p.id
    db.commit()
    assert _run(db.get_bind(), owner.id)["created"] == 0


def test_deleted_ticket_retires_untouched_candidate(face_sqlite_session, railway):
    from app.crud.train_ticket import delete_train_ticket
    db = face_sqlite_session
    owner = user(db)
    t = ticket(db, owner)
    photo(db, owner, -1)
    db.commit()
    row = journey.discover(db, owner.id)[0]
    db.commit()
    delete_train_ticket(db, t.id)
    journey.discover(db, owner.id)
    db.commit()
    assert row.status == MemoryStatus.SUPERSEDED
    assert db.query(Photo).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stamp,year_source", [("10月01日 12:00", None),
                                              ("2026-10-01 12:00", "inferred_current_year")])
async def test_inferred_year_requires_manual_time_confirmation(face_sqlite_session, railway, monkeypatch,
                                                              stamp, year_source):
    from app.service.tasks import tickets
    from app.crud.train_ticket import update_train_ticket
    from unittest.mock import AsyncMock
    db = face_sqlite_session
    owner = user(db)
    source = photo(db, owner, -2, image_type=ImageType.SCREENSHOT)
    expected = photo(db, owner, -1)
    db.commit()
    monkeypatch.setattr(tickets, "calculate_ticket_mileage_and_time", AsyncMock(
        return_value={"total_mileage": 0, "total_time": 0, "stop_stations": []}))
    result = await tickets.RecognizeTicketStrategy().save_recognition_result(source, {"tickets": [{
        "type": "train", "train_code": "G1", "datetime": stamp, "year_source": year_source,
        "departure_station": "杭州东", "arrival_station": "上海虹桥", "price": 100,
    }]}, db)
    assert result["status"] == "success"
    t = db.query(TrainTicket).one()
    assert source.processed_tasks["ticket_time_sources"][f"train:{t.id}"] == "inferred_year"
    assert journey.discover(db, owner.id) == []
    update_train_ticket(db, t.id, TrainTicketUpdate(date_time=DEPARTURE))
    row = journey.discover(db, owner.id)[0]
    assert row.photo_links[0].photo_id == expected.id
