"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/service/tasks/tickets.py -- RecognizeTicketStrategy.task_category + factory
  registration, process() generator mode (empty batch / batch with photos force +
  no-force / exception), process_batch() routing (photo tasks grouped by owner),
  process_batch() generator tasks delegated to process(), process_single_photo()
  happy path with train ticket (TrainTicketCreate bypassed to test surrounding
  logic), file-not-found path, AI service 5xx path, release_resources() no-op,
  get_schedule_info() non-200 response.
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _photo(**kw):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "file_type": 0,
        "file_path": "/tmp/photo.jpg",
        "filename": "photo.jpg",
        "processed_tasks": {},
        "photo_time": datetime(2024, 5, 1, 10, 0),
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _task(**kw):
    base = {"id": uuid4(), "type": "recognize_ticket", "owner_id": uuid4(), "payload": {}}
    base.update(kw)
    return SimpleNamespace(**base)


def _chain_db_query(db, batches):
    chain = db.query.return_value
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    calls = {"i": 0}

    def _consume(_=None):
        idx = calls["i"]
        calls["i"] += 1
        if idx < len(batches):
            return batches[idx]
        return []

    chain.all.side_effect = _consume
    return chain


def _ai_config(api_url="http://ai:8001"):
    return SimpleNamespace(ai=SimpleNamespace(ai_api_url=api_url))


# --- strategy basics --------------------------------------------------------


def test_recognize_ticket_strategy_task_category_is_ai():
    from app.service.tasks import tickets
    strategy = tickets.RecognizeTicketStrategy()
    assert strategy.task_category == "AI"
    assert strategy.resource_key == "tickets"


def test_recognize_ticket_strategy_registered_in_factory():
    from app.db.models.task import TaskType
    from app.service.task_strategy import TaskStrategyFactory
    from app.service.tasks.tickets import RecognizeTicketStrategy
    s = TaskStrategyFactory.get_strategy(TaskType.RECOGNIZE_TICKET)
    assert isinstance(s, RecognizeTicketStrategy)


def test_release_resources_is_noop():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    assert RecognizeTicketStrategy().release_resources() is None


# --- process() generator mode -----------------------------------------------


def test_process_generator_empty_db_returns_zero():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    _chain_db_query(db, [[]])
    res = _run(RecognizeTicketStrategy().process(MagicMock(), _task(), db))
    assert res["processed"] == 0
    assert res["generated_tasks"] == 0


def test_process_generator_with_photos_creates_tasks():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    photo = _photo(processed_tasks={})
    _chain_db_query(db, [[photo], []])
    worker = MagicMock()
    res = _run(RecognizeTicketStrategy().process(worker, _task(payload={"force": False}), db))
    assert res["generated_tasks"] == 1
    worker.add_tasks.assert_called_once()
    payload = worker.add_tasks.call_args.args[1]
    assert payload[0]["type"]
    assert payload[0]["payload"]["photo_id"] == str(photo.id)


def test_process_generator_force_skips_processed_check():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    photo = _photo(processed_tasks={"tickets": True})
    _chain_db_query(db, [[photo], []])
    worker = MagicMock()
    res = _run(RecognizeTicketStrategy().process(worker, _task(payload={"force": True}), db))
    assert res["generated_tasks"] == 1


def test_process_generator_skips_video_photos():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    from app.db.models.photo import FileType
    db = MagicMock()
    video = _photo(file_type=FileType.video)
    _chain_db_query(db, [[video], []])
    worker = MagicMock()
    res = _run(RecognizeTicketStrategy().process(worker, _task(), db))
    assert res["generated_tasks"] == 0
    worker.add_tasks.assert_not_called()


def test_process_generator_exception_propagates():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    db.query.side_effect = RuntimeError("db boom")
    with pytest.raises(RuntimeError):
        _run(RecognizeTicketStrategy().process(MagicMock(), _task(), db))


def test_process_skips_already_processed_when_not_force():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    photo = _photo(processed_tasks={"tickets": True})
    res = _run(
        RecognizeTicketStrategy().process(
            MagicMock(), _task(payload={"photo_id": str(photo.id), "force": False}), db
        )
    )
    db.query.assert_called_once()
    assert res["status"] == "skipped"
    assert res["reason"] == "already processed"


# --- get_schedule_info HTTP paths -------------------------------------------


@pytest.mark.asyncio
async def test_get_schedule_info_returns_none_on_non_200():
    from app.service.tasks import tickets

    fake_session = MagicMock()
    fake_response = MagicMock()
    fake_response.status = 500
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=False)

    fake_session.get = MagicMock(return_value=fake_response)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.service.tasks.tickets.aiohttp.ClientSession", return_value=fake_session):
        result = await tickets.get_schedule_info("G100")
    assert result is None


# --- calculate_ticket_mileage_and_time edge cases ---------------------------


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_returns_empty_on_non_200_schedule():
    from app.service.tasks import tickets
    ticket = SimpleNamespace(train_code="G100", departure_station="A", arrival_station="B")
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value={"code": 500})):
        result = await tickets.calculate_ticket_mileage_and_time(ticket)
    assert result == {"total_mileage": 0, "total_time": 0, "stop_stations": []}


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_returns_empty_when_schedule_none():
    from app.service.tasks import tickets
    ticket = SimpleNamespace(train_code="G100", departure_station="A", arrival_station="B")
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value=None)):
        result = await tickets.calculate_ticket_mileage_and_time(ticket)
    assert result == {"total_mileage": 0, "total_time": 0, "stop_stations": []}


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_returns_empty_on_empty_schedule_list():
    from app.service.tasks import tickets
    ticket = SimpleNamespace(train_code="G100", departure_station="A", arrival_station="B")
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value={"code": 200, "data": {"list": []}})):
        result = await tickets.calculate_ticket_mileage_and_time(ticket)
    assert result == {"total_mileage": 0, "total_time": 0, "stop_stations": []}


# --- process_single_photo ---------------------------------------------------


def test_process_single_photo_returns_failed_when_file_not_found():
    from app.service.tasks.tickets import RecognizeTicketStrategy
    db = MagicMock()
    photo = _photo()
    with patch("app.service.tasks.tickets.storage.get_available_photo_path", return_value=None):
        result = _run(RecognizeTicketStrategy().process_single_photo(MagicMock(), photo, db))
    assert result["status"] == "failed"
    assert "file not found" in result["error"]


@pytest.mark.asyncio
async def test_process_single_photo_happy_path_creates_train_ticket():
    from app.service.tasks.tickets import RecognizeTicketStrategy

    db = MagicMock()
    photo = _photo()
    captured = {}

    def fake_create(db, payload, owner_id):
        captured["payload"] = payload
        captured["owner_id"] = owner_id
        return SimpleNamespace(id=uuid4())

    def fake_create_cls(**kwargs):
        # Bypass pydantic validation; capture kwargs for downstream assertions
        ns = SimpleNamespace(**kwargs)
        captured["payload"] = ns
        return ns

    ai_response = MagicMock()
    ai_response.status = 200
    ai_response.__aenter__ = AsyncMock(return_value=ai_response)
    ai_response.__aexit__ = AsyncMock(return_value=False)

    async def _fake_json():
        return {
            "results": [
                {
                    "tickets": [
                        {
                            "type": "train",
                            "train_code": "G100",
                            "departure_station": "Alpha",
                            "arrival_station": "Bravo",
                            "datetime": "2024-05-01 10:00",
                            "price": "100.5元",
                            "name": "Alice",
                            "seat_type": "二等座",
                        }
                    ]
                }
            ]
        }

    ai_response.json = _fake_json

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=ai_response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.post = MagicMock(return_value=post_cm)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.service.tasks.tickets.storage.get_available_photo_path", return_value="/tmp/photo.jpg"), \
         patch("app.service.tasks.tickets.crud_train_tickets.delete_train_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.crud_flight_tickets.delete_flight_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.crud_train_tickets.create_train_ticket", side_effect=fake_create), \
         patch("app.service.tasks.tickets.crud_flight_tickets.create_flight_ticket"), \
         patch("app.service.tasks.tickets.TrainTicketCreate", side_effect=fake_create_cls), \
         patch("app.service.tasks.tickets.calculate_ticket_mileage_and_time", new=AsyncMock(return_value={"total_mileage": 100, "total_time": 60, "stop_stations": []})), \
         patch("app.service.tasks.tickets.aiohttp.ClientSession", return_value=fake_session), \
         patch("app.service.tasks.tickets.config_manager.get_user_config", return_value=_ai_config()), \
         patch("builtins.open", mock_open(read_data=b"\xff\xd8\xff\xe0fakejpg")):
        result = await RecognizeTicketStrategy().process_single_photo(MagicMock(), photo, db)

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert captured["payload"].total_mileage == 100
    assert captured["payload"].total_running_time == 60
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_process_single_photo_ai_service_error_returns_failed():
    from app.service.tasks.tickets import RecognizeTicketStrategy

    db = MagicMock()
    photo = _photo()

    ai_response = MagicMock()
    ai_response.status = 503
    ai_response.text = AsyncMock(return_value="down")
    ai_response.__aenter__ = AsyncMock(return_value=ai_response)
    ai_response.__aexit__ = AsyncMock(return_value=False)

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=ai_response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.post = MagicMock(return_value=post_cm)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.service.tasks.tickets.storage.get_available_photo_path", return_value="/tmp/photo.jpg"), \
         patch("app.service.tasks.tickets.crud_train_tickets.delete_train_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.crud_flight_tickets.delete_flight_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.aiohttp.ClientSession", return_value=fake_session), \
         patch("app.service.tasks.tickets.config_manager.get_user_config", return_value=_ai_config()), \
         patch("builtins.open", mock_open(read_data=b"\xff\xd8\xff\xe0fakejpg")):
        result = await RecognizeTicketStrategy().process_single_photo(MagicMock(), photo, db)

    assert result["status"] == "failed"
    assert "503" in result["error"]


# --- process_batch photo-mode ----------------------------------------------


@pytest.mark.asyncio
async def test_process_batch_groups_photos_by_owner_and_calls_ai():
    from app.service.tasks.tickets import RecognizeTicketStrategy

    owner_id = uuid4()
    photo = _photo(owner_id=owner_id)
    tasks = [_task(owner_id=owner_id, payload={"photo_id": str(photo.id)})]

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]

    ai_response = MagicMock()
    ai_response.status = 200
    ai_response.__aenter__ = AsyncMock(return_value=ai_response)
    ai_response.__aexit__ = AsyncMock(return_value=False)

    async def _fake_json():
        return {"results": [{"tickets": []}]}

    ai_response.json = _fake_json

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=ai_response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    fake_session = MagicMock()
    fake_session.post = MagicMock(return_value=post_cm)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.service.tasks.tickets.storage.get_available_photo_path", return_value="/tmp/photo.jpg"), \
         patch("app.service.tasks.tickets.crud_train_tickets.delete_train_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.crud_flight_tickets.delete_flight_ticket_by_photo_id"), \
         patch("app.service.tasks.tickets.crud_train_tickets.create_train_ticket", return_value=SimpleNamespace(id=uuid4())), \
         patch("app.service.tasks.tickets.crud_flight_tickets.create_flight_ticket", return_value=SimpleNamespace(id=uuid4())), \
         patch("app.service.tasks.tickets.aiohttp.ClientSession", return_value=fake_session), \
         patch("app.service.tasks.tickets.config_manager.get_user_config", return_value=_ai_config()), \
         patch("builtins.open", mock_open(read_data=b"\xff\xd8\xff\xe0fakejpg")):
        results = await RecognizeTicketStrategy().process_batch(MagicMock(), tasks, db)

    assert len(results) == 1
    assert results[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_process_batch_marks_photo_not_found_as_skipped():
    from app.service.tasks.tickets import RecognizeTicketStrategy

    photo_id = uuid4()
    tasks = [_task(payload={"photo_id": str(photo_id)})]

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    results = await RecognizeTicketStrategy().process_batch(MagicMock(), tasks, db)
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_process_batch_routes_generator_tasks_to_process():
    from app.service.tasks.tickets import RecognizeTicketStrategy

    gen_task = _task(payload={})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    fake_process_result = {"status": "failed", "error": "boom"}

    with patch.object(RecognizeTicketStrategy, "process", new=AsyncMock(return_value=fake_process_result)):
        results = await RecognizeTicketStrategy().process_batch(MagicMock(), [gen_task], db)

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"
