"""2026-10-29 nightly gap tests for ``app/service/tasks/tickets.py``.

The ticket task strategy is exercised with the AI transport, the file system
access and the CRUD layer patched out, so no network or database is needed.

Covered gaps:
* ``get_endpoint_distance`` / ``calculate_ticket_mileage_and_time`` fallbacks
  (missing distance, lookup failure, station-name corrections).
* ``process`` dispatch for a single photo and the generator path.
* ``process_batch`` error branches (missing file, unreadable file, malformed
  AI payload, non-200 response, unexpected exception).
* ``save_recognition_result`` validation and train-code resolution.
* ``process_single_photo`` failure paths.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.service.tasks import tickets as tickets_module
from app.service.tasks.tickets import RecognizeTicketStrategy


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _task(payload=None, task_id="task-1"):
    return SimpleNamespace(
        id=task_id,
        type="RECOGNIZE_TICKET",
        owner_id="user-1",
        payload=payload if payload is not None else {},
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _photo(photo_id=None):
    return SimpleNamespace(
        id=photo_id or uuid4(),
        owner_id="user-1",
        filename="ticket.jpg",
        file_path="C:/photos/ticket.jpg",
        processed_tasks={},
        photo_time=None,
    )


# ----------------------- distance / mileage helpers -----------------------


def test_get_endpoint_distance_uses_history_cache():
    """The endpoint distance is delegated to the offline history cache."""
    ticket = SimpleNamespace(
        departure_station="北京南", arrival_station="上海虹桥", date_time=SimpleNamespace(date=lambda: "2026-01-01")
    )

    class FakeCache:
        def distance(self, first, second, day=None):
            return 1318.0

    with patch("railway.history_cache.HistoryCache", return_value=FakeCache()):
        distance = asyncio.run(tickets_module.get_endpoint_distance(ticket))

    assert distance == 1318.0


def test_calculate_mileage_returns_empty_result_when_lookup_fails():
    """A failing history lookup degrades to empty mileage data."""
    ticket = SimpleNamespace(
        train_code="G1", departure_station="北京南", arrival_station="上海虹桥", date_time=None
    )

    with patch.object(tickets_module, "get_schedule_info", side_effect=RuntimeError("offline")):
        result = asyncio.run(tickets_module.calculate_ticket_mileage_and_time(ticket))

    assert result["total_mileage"] is None
    assert result["total_time"] is None
    assert result["stop_stations"] == []


def test_calculate_mileage_falls_back_to_endpoint_distance():
    """When the schedule has no distance the GPS endpoint estimate is used."""
    ticket = SimpleNamespace(
        train_code="G1", departure_station="北京南", arrival_station="上海虹桥", date_time=None
    )
    historical = {"distance_km": None, "duration_minutes": 300, "stops": []}

    with patch.object(tickets_module, "get_schedule_info", return_value=historical):
        with patch.object(tickets_module, "get_endpoint_distance", new=AsyncMock(return_value=1200.0)):
            with patch("railway.history_seed.station_metadata", return_value={}):
                with patch("app.service.ticket_journey.repair_station_names", return_value={}):
                    with patch("app.service.ticket_journey.enrich_journey", side_effect=lambda result, *a: result):
                        result = asyncio.run(
                            tickets_module.calculate_ticket_mileage_and_time(ticket, evidence={"raw": "face"})
                        )

    assert result["total_mileage"] == 1200.0
    assert result["total_time"] == 300


def test_calculate_mileage_applies_station_corrections():
    """Unknown station names are repaired and reported in ``sources``."""
    ticket = SimpleNamespace(
        train_code="G1",
        departure_station="北京",
        arrival_station="上海",
        date_time=None,
    )
    historical = {"distance_km": 1318, "duration_minutes": 300, "stops": []}
    corrections = {"departure_station": {"resolved": "北京南"}}

    with patch.object(tickets_module, "get_schedule_info", return_value=historical):
        with patch("railway.history_seed.station_metadata", return_value={"x": {"names": []}}):
            with patch("app.service.ticket_journey.repair_station_names", return_value=corrections):
                with patch(
                    "app.service.ticket_journey.enrich_journey",
                    side_effect=lambda result, hist, ev, code: dict(result, sources={"distance_source": "gps-haversine-x1.2"}),
                ):
                    result = asyncio.run(
                        tickets_module.calculate_ticket_mileage_and_time(ticket, evidence={"raw": "票面"})
                    )

    assert ticket.departure_station == "北京南"
    assert result["sources"]["station_corrections"] == corrections


# ----------------------- RecognizeTicketStrategy.process -----------------------


def test_process_skips_photo_that_was_already_recognized():
    """A photo with ``tickets`` already set is skipped."""
    db = MagicMock()
    photo = _photo()
    photo.processed_tasks = {"tickets": True}
    db.query.return_value.filter.return_value.first.return_value = photo
    task = _task({"photo_id": str(photo.id)})

    result = asyncio.run(RecognizeTicketStrategy().process(worker=None, task=task, db=db))

    assert result == {"status": "skipped", "reason": "already processed"}


def test_process_delegates_single_photo_to_process_single_photo():
    """A forced recognition of one photo goes through ``process_single_photo``."""
    db = MagicMock()
    photo = _photo()
    db.query.return_value.filter.return_value.first.return_value = photo
    task = _task({"photo_id": str(photo.id), "force": True})

    strategy = RecognizeTicketStrategy()
    with patch.object(strategy, "process_single_photo", new=AsyncMock(return_value={"status": "success"})) as single:
        result = asyncio.run(strategy.process(worker=None, task=task, db=db))

    single.assert_awaited_once()
    assert result == {"status": "success"}


def test_process_generates_tasks_when_no_photo_id_given():
    """Without a photo id the strategy fans out per-photo tasks."""
    db = MagicMock()
    task = _task({})

    with patch.object(tickets_module, "generate_photo_tasks", return_value=3) as generate:
        result = asyncio.run(RecognizeTicketStrategy().process(worker=None, task=task, db=db))

    generate.assert_called_once()
    assert result["generated_tasks"] == 3
    assert result["processed"] == 0


def test_process_reraises_unexpected_errors():
    """Unexpected errors are logged and re-raised."""
    task = _task({})

    with patch.object(tickets_module, "generate_photo_tasks", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(RecognizeTicketStrategy().process(worker=None, task=task, db=MagicMock()))


# ----------------------- process_batch -----------------------


def _batch_photo_chain(photos):
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = photos
    return query


def test_process_batch_marks_generator_task_failure():
    """A failing generator task is reported as failed instead of raising."""
    task = _task({}, task_id="gen-1")
    strategy = RecognizeTicketStrategy()

    with patch.object(strategy, "process", new=AsyncMock(side_effect=RuntimeError("生成失败"))):
        results = asyncio.run(strategy.process_batch(worker=None, tasks=[task], db=MagicMock()))

    assert results[0]["status"] == "failed"
    assert "生成失败" in results[0]["error"]


def test_process_batch_skips_photo_without_file():
    """A photo whose file cannot be located is reported as failed."""
    photo = _photo()
    db = MagicMock()
    db.query.return_value = _batch_photo_chain([photo])
    task = _task({"photo_id": str(photo.id)}, task_id="photo-1")

    with patch.object(tickets_module.storage, "get_available_photo_path", return_value=None):
        results = asyncio.run(RecognizeTicketStrategy().process_batch(worker=None, tasks=[task], db=db))

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "file not found"


def test_process_batch_reports_unreadable_file():
    """A read error while loading the photo is reported per task."""
    photo = _photo()
    db = MagicMock()
    db.query.return_value = _batch_photo_chain([photo])
    task = _task({"photo_id": str(photo.id)}, task_id="photo-1")

    with patch.object(tickets_module.storage, "get_available_photo_path", return_value="C:/photos/ticket.jpg"):
        with patch("builtins.open", side_effect=OSError("denied")):
            results = asyncio.run(RecognizeTicketStrategy().process_batch(worker=None, tasks=[task], db=db))

    assert results[0]["status"] == "failed"
    assert "read file error" in results[0]["error"]


def test_process_batch_rejects_malformed_ai_payload():
    """A non-list ``results`` payload is an error, not a silent success."""
    photo = _photo()
    db = MagicMock()
    db.query.return_value = _batch_photo_chain([photo])
    task = _task({"photo_id": str(photo.id)}, task_id="photo-1")

    response = SimpleNamespace(status=200, json=AsyncMock(return_value={"results": {"not": "a list"}}))

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *_args, **_kwargs):
            return _FakeCtx(response)

    class _FakeCtx:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, *args):
            return False

    with patch.object(tickets_module.storage, "get_available_photo_path", return_value="C:/photos/ticket.jpg"):
        with patch("builtins.open", side_effect=mock_open_bytes()):
            with patch.object(tickets_module.aiohttp, "ClientSession", return_value=FakeSession()):
                with patch.object(tickets_module.config_manager, "get_user_config") as cfg:
                    cfg.return_value = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai"))
                    results = asyncio.run(
                        RecognizeTicketStrategy().process_batch(worker=None, tasks=[task], db=db)
                    )

    assert results[0]["status"] == "failed"
    assert "格式无效" in results[0]["error"]


def test_process_batch_handles_non_200_response():
    """A failing AI response marks every valid task as failed."""
    photo = _photo()
    db = MagicMock()
    db.query.return_value = _batch_photo_chain([photo])
    task = _task({"photo_id": str(photo.id)}, task_id="photo-1")

    response = SimpleNamespace(status=500, json=AsyncMock(return_value={}))

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *_args, **_kwargs):
            return _FakeCtx(response)

    class _FakeCtx:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, *args):
            return False

    with patch.object(tickets_module.storage, "get_available_photo_path", return_value="C:/photos/ticket.jpg"):
        with patch("builtins.open", side_effect=mock_open_bytes()):
            with patch.object(tickets_module.aiohttp, "ClientSession", return_value=FakeSession()):
                with patch.object(tickets_module.config_manager, "get_user_config") as cfg:
                    cfg.return_value = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai"))
                    with patch.object(tickets_module, "ai_response_error", new=AsyncMock(return_value="AI 服务异常")):
                        results = asyncio.run(
                            RecognizeTicketStrategy().process_batch(worker=None, tasks=[task], db=db)
                        )

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "AI 服务异常"


def test_process_batch_marks_tasks_failed_on_unexpected_error():
    """An unexpected error inside the owner loop fails the pending tasks."""
    photo = _photo()
    db = MagicMock()
    db.query.return_value = _batch_photo_chain([photo])
    task = _task({"photo_id": str(photo.id)}, task_id="photo-1")

    with patch.object(tickets_module.storage, "get_available_photo_path", side_effect=RuntimeError("磁盘炸了")):
        results = asyncio.run(RecognizeTicketStrategy().process_batch(worker=None, tasks=[task], db=db))

    assert results[0]["status"] == "failed"
    assert "磁盘炸了" in results[0]["error"]
    db.rollback.assert_called()


def mock_open_bytes():
    import io
    from unittest.mock import mock_open
    return mock_open(read_data=b"binary-image")


# ----------------------- save_recognition_result -----------------------


def test_save_recognition_result_rejects_invalid_payload():
    """A payload without a ticket list is rejected and the flag is reset."""
    photo = _photo()
    db = MagicMock()

    result = asyncio.run(
        RecognizeTicketStrategy().save_recognition_result(photo, {"tickets": "not-a-list"}, db)
    )

    assert result["status"] == "failed"
    assert "格式无效" in result["error"]
    assert photo.processed_tasks.get("tickets") is False


def test_save_recognition_result_reports_ai_error():
    """An AI reported error is surfaced to the caller."""
    photo = _photo()
    db = MagicMock()

    result = asyncio.run(
        RecognizeTicketStrategy().save_recognition_result(photo, {"tickets": [], "error": "识别失败"}, db)
    )

    assert result["status"] == "failed"
    assert "识别失败" in result["error"]


def test_save_recognition_result_rejects_non_dict_ticket():
    """Each ticket entry must be a mapping."""
    photo = _photo()
    db = MagicMock()

    result = asyncio.run(
        RecognizeTicketStrategy().save_recognition_result(photo, {"tickets": ["oops"]}, db)
    )

    assert result["status"] == "failed"
    assert "无效票据" in result["error"]


def test_save_recognition_result_saves_tickets():
    """A well formed payload creates the tickets and flips the photo flag."""
    photo = _photo()
    db = MagicMock()
    ticket = SimpleNamespace(
        train_code="G1",
        departure_station="北京南",
        arrival_station="上海虹桥",
        date_time=None,
    )

    with patch("app.service.ticket_journey.parse_ticket_datetime", return_value=(datetime(2026, 1, 1, 8, 0, 0), None)):
        with patch.object(tickets_module, "calculate_ticket_mileage_and_time", new=AsyncMock(return_value={
            "total_mileage": 1318, "total_time": 300, "stop_stations": [], "sources": None,
        })):
            with patch.object(tickets_module.crud_train_tickets, "create_train_ticket", return_value=SimpleNamespace(id=uuid4())):
                result = asyncio.run(
                    RecognizeTicketStrategy().save_recognition_result(
                        photo, {"tickets": [ticket.__dict__]}, db
                    )
                )

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert photo.processed_tasks["tickets"] is True


# ----------------------- process_single_photo -----------------------


def test_process_single_photo_reports_missing_file():
    """A photo without an available file fails immediately."""
    photo = _photo()
    db = MagicMock()

    with patch.object(tickets_module.storage, "get_available_photo_path", return_value=None):
        result = asyncio.run(
            RecognizeTicketStrategy().process_single_photo(worker=None, photo=photo, db=db)
        )

    assert result == {"status": "failed", "error": "file not found"}


def test_process_single_photo_handles_unexpected_error():
    """Unexpected errors are rolled back and reported as a failure."""
    photo = _photo()
    db = MagicMock()

    with patch.object(tickets_module.storage, "get_available_photo_path", side_effect=RuntimeError("磁盘不可用")):
        result = asyncio.run(
            RecognizeTicketStrategy().process_single_photo(worker=None, photo=photo, db=db)
        )

    assert result["status"] == "failed"
    assert "磁盘不可用" in result["error"]
    db.rollback.assert_called()
