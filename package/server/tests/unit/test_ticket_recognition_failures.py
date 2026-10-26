"""Ticket jobs must never report success after a failed save."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models import User
from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.trip import TrainTicket, FlightTicket
from app.service.tasks import tickets
from app.service.ticket_recovery import recover_ticket_recognition

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


@pytest.fixture
def scenario(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username='ticket-owner', hashed_password='x')
    other = User(id=uuid4(), username='ticket-other', hashed_password='x')
    db.add_all([owner, other])
    db.flush()
    photo = Photo(id=uuid4(), owner_id=owner.id, filename='ticket.jpg', file_path='/tmp/ticket.jpg',
                  file_type=FileType.image, photo_time=datetime(2026, 10, 20), processed_tasks={'tickets': True})
    db.add(photo)
    db.commit()
    return db, owner, other, photo


def train(**kwargs):
    return dict(type='train', train_code='G100', departure_station='北京南', arrival_station='上海虹桥',
                datetime='2026-10-20 10:00', price='100元', **kwargs)


@pytest.mark.asyncio
async def test_reference_lookup_failure_still_saves_and_retry_keeps_id(scenario):
    db, owner, _, photo = scenario
    # The optional offline railway history cache (REQ-196) is filled on
    # developer machines and answers the mileage before the patched live
    # lookup is ever reached. Neutralise it so the test does not depend on
    # whether the machine synced the railway history yet.
    with patch('railway.history_cache.HistoryCache') as history_cache, \
         patch.object(tickets, 'get_schedule_info', new=AsyncMock(side_effect=OSError('railway unavailable'))):
        history_cache.return_value.status.return_value = {'sequence': 0}
        result = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': [train()]}, db)
        saved = db.query(TrainTicket).one()
        saved_id = saved.id
        assert result['status'] == 'success' and result['tickets_added'] == 1
        assert saved.total_mileage == 0
        assert saved.carriage == '' and saved.seat_num == '无座'
        again = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': [train()]}, db)
    assert again['tickets_existing'] == 1
    assert db.query(TrainTicket).one().id == saved_id
    assert photo.processed_tasks['tickets_version'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, {}, {'tickets': None}, {'tickets': [{}]}, {'tickets': [train(), {}]},
                               {'tickets': [dict(train(), price='not-a-price')]}])
async def test_invalid_response_fails_without_marking_done(scenario, bad):
    db, _, _, photo = scenario
    with patch.object(tickets, 'calculate_ticket_mileage_and_time', new=AsyncMock(return_value={'total_mileage': 0, 'total_time': 0, 'stop_stations': []})):
        result = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, bad, db)
    assert result['status'] == 'failed' and result['error']
    assert photo.processed_tasks['tickets'] is False
    assert db.query(TrainTicket).count() == 0


@pytest.mark.asyncio
async def test_insert_failure_rolls_back_all_new_tickets_and_preserves_old(scenario):
    db, owner, _, photo = scenario
    old = FlightTicket(owner_id=owner.id, photo_id=photo.id, flight_code='OLD', departure_city='北京',
                       arrival_city='上海', date_time=datetime(2025, 1, 1), price=1, name='旅人')
    db.add(old); db.commit()
    flights = [dict(type='flight', flight_code=code, datetime='2026-10-20 10:00', price='100',
                    departure_city=None, arrival_city=None) for code in ('MU1', 'MU2')]
    create = tickets.crud_flight_tickets.create_flight_ticket
    def save(db, model, **kwargs):
        if model.flight_code == 'MU2':
            raise RuntimeError('disk write failed')
        return create(db, model, **kwargs)
    with patch.object(tickets.crud_flight_tickets, 'create_flight_ticket', side_effect=save):
        result = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': flights}, db)
    assert result['status'] == 'failed'
    assert db.query(FlightTicket).one().flight_code == 'OLD'
    assert photo.processed_tasks['tickets'] is False


@pytest.mark.asyncio
async def test_null_flight_cities_save_and_empty_result_is_distinct(scenario):
    db, _, _, photo = scenario
    info = dict(type='flight', flight_code='MU1', departure_city=None, arrival_city=None,
                datetime='2026-10-20 10:00', price=None)
    result = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': [info]}, db)
    assert result['status'] == 'success'
    assert db.query(FlightTicket).one().departure_city == '未知'
    empty = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': []}, db)
    assert empty['status'] == 'no_tickets'
    assert db.query(FlightTicket).count() == 1


def test_recovery_is_owned_live_legacy_without_tickets_or_existing_jobs(scenario):
    db, owner, other, photo = scenario
    def add(owner_id=owner.id, processed=None, **kwargs):
        row = Photo(id=uuid4(), owner_id=owner_id, filename='old.jpg', file_path='/tmp/old.jpg',
                    file_type=FileType.image, processed_tasks=processed or {'tickets': True}, **kwargs)
        db.add(row); db.flush()
        return row
    add(owner_id=other.id)
    add(is_deleted=True)
    add(processed={'tickets': True, 'tickets_version': 2})
    existing = add()
    db.add(FlightTicket(owner_id=owner.id, photo_id=existing.id, flight_code='MU1', departure_city='a',
                       arrival_city='b', date_time=datetime(2026, 1, 1), price=1, name='n'))
    for state in (TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.FAILED):
        busy = add()
        db.add(Task(type=TaskType.RECOGNIZE_TICKET, owner_id=owner.id, status=state,
                    payload={'photo_id': str(busy.id)}))
    db.commit()
    from app.crud.task import add_tasks
    manager = SimpleNamespace(add_tasks=add_tasks)
    assert recover_ticket_recognition(db, manager, owner.id) == 1
    assert recover_ticket_recognition(db, manager, owner.id) == 0
    task = db.query(Task).filter(Task.photo_id == photo.id).one()
    assert task.payload['force'] is True
    assert task.owner_id == owner.id


def test_concurrent_recovery_does_not_duplicate_jobs(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.crud.task import add_tasks
    from app.service.tasks.ai_runtime import AIBatchSession
    db, owner, _, photo = scenario
    owner_id, photo_id, bind = owner.id, photo.id, db.get_bind()
    ready = Barrier(2)
    def run():
        with AIBatchSession(bind=bind, expire_on_commit=False) as session:
            ready.wait(timeout=5)
            return recover_ticket_recognition(session, SimpleNamespace(add_tasks=add_tasks), owner_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sum(future.result(timeout=10) for future in futures) == 1
    assert db.query(Task).filter(Task.photo_id == photo_id).count() == 1


@pytest.mark.asyncio
async def test_duplicate_detection_is_scoped_to_owner(scenario):
    db, owner, other, photo = scenario
    db.add(FlightTicket(owner_id=other.id, flight_code='MU1', departure_city='a', arrival_city='b',
                       name='未知', date_time=datetime(2026, 10, 20, 10), price=1))
    db.commit()
    info = dict(type='flight', flight_code='MU1', datetime='2026-10-20 10:00', price='100')
    result = await tickets.RecognizeTicketStrategy().save_recognition_result(photo, {'tickets': [info]}, db)
    assert result['tickets_added'] == 1
    assert db.query(FlightTicket).filter(FlightTicket.owner_id == owner.id).count() == 1


def test_recovery_endpoint_queues_jobs_and_reuses_existing_work(scenario):
    from app.api.tasks import recover_ticket_tasks
    from app.crud.task import add_tasks
    db, owner, _, photo = scenario
    manager = SimpleNamespace(add_tasks=add_tasks)
    with patch('app.api.tasks.TaskManager.get_instance', return_value=manager):
        response = recover_ticket_tasks(db, owner)
        again = recover_ticket_tasks(db, owner)
    assert response.code == 0 and response.data == {'count': 1}
    assert again.data == {'count': 0}
    assert db.query(Task).filter(Task.photo_id == photo.id).count() == 1


@pytest.mark.asyncio
async def test_internal_schedule_serializes_time_and_decimal_without_http(monkeypatch):
    monkeypatch.setenv('RAILWAY_DB_URL', 'sqlite://')
    from datetime import time
    from decimal import Decimal
    data = {'list': [{'arrival_time': time(8, 30), 'accumulated_mileage': Decimal('100.5')}]}
    with patch('railway.db.session.SessionLocal'), \
         patch('railway.crud.get_train_schedule_list', return_value=(200, 'ok', data)), \
         patch.object(tickets.aiohttp, 'ClientSession') as http:
        result = await tickets.get_schedule_info('G100')
    assert result['data']['list'][0]['arrival_time'] == '08:30:00'
    assert result['data']['list'][0]['accumulated_mileage'] == 100.5
    http.assert_not_called()
