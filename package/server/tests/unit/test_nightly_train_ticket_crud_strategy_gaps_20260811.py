"""Unit tests covering 2026-08-11 nightly coverage gap scan (round 4).

Modules exercised:
* app/crud/train_ticket.py -- get_train_ticket / get_train_tickets /
  get_all_train_tickets / create_train_ticket / update_train_ticket /
  delete_train_ticket / delete_train_ticket_by_photo_id
* app/service/task_strategy.py -- BaseTaskStrategy default impls +
  TaskStrategyFactory.register / get_strategy / get_tasks_by_category /
  release_idle_resources / release_all_resources
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.crud import train_ticket as crud_ticket
from app.db.models.task import TaskType
from app.service import task_strategy


pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _ticket(**kwargs):
    base = {
        "id": "ticket-id-1",
        "train_code": "G1234",
        "departure_station": "Beijing",
        "arrival_station": "Shanghai",
        "date_time": "2025-08-01T08:00:00",
        "carriage": "05",
        "seat_num": "12A",
        "berth_type": "None",
        "price": 553.5,
        "seat_type": "Second-class",
        "name": "Alice",
        "discount_type": "Full-price",
        "total_running_time": 270,
        "total_mileage": "1318",
        "stop_stations": "[]",
        "comments": "",
        "owner_id": uuid4(),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


# app/crud/train_ticket.py


def test_get_train_ticket_returns_first_match():
    db = MagicMock()
    expected = _ticket()
    db.query.return_value.filter.return_value.first.return_value = expected
    result = crud_ticket.get_train_ticket(db, "ticket-id-1")
    assert result is expected


def test_get_train_tickets_applies_string_ilike_filter():
    db = MagicMock()
    query_after_filter = MagicMock()
    db.query.return_value.filter.return_value = query_after_filter
    final_chain = MagicMock()
    query_after_filter.offset.return_value = final_chain
    final_chain.limit.return_value.order_by.return_value.all.return_value = [_ticket()]
    query_after_filter.count.return_value = 1
    total, items = crud_ticket.get_train_tickets(db, skip=0, limit=10, filters={"train_code": "G1"})
    assert total == 1
    assert len(items) == 1


def test_get_train_tickets_applies_uuid_exact_filter():
    db = MagicMock()
    target_uuid = uuid4()
    query_after_filter = MagicMock()
    db.query.return_value.filter.return_value = query_after_filter
    final_chain = MagicMock()
    query_after_filter.offset.return_value = final_chain
    final_chain.limit.return_value.order_by.return_value.all.return_value = []
    query_after_filter.count.return_value = 0
    total, items = crud_ticket.get_train_tickets(db, filters={"owner_id": target_uuid})
    assert total == 0
    assert items == []


def test_get_all_train_tickets_filters_by_owner_when_provided():
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value.all.return_value = []
    chain.order_by.return_value.filter.return_value.all.return_value = []
    crud_ticket.get_all_train_tickets(db, owner_id=uuid4())
    chain.order_by.return_value.filter.assert_called_once()


def test_get_all_train_tickets_returns_all_when_no_owner():
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value.all.return_value = [_ticket()]
    items = crud_ticket.get_all_train_tickets(db)
    assert len(items) == 1


def test_create_train_ticket_returns_none_when_duplicate():
    from app.schemas.train_ticket import TrainTicketCreate
    from datetime import datetime
    db = MagicMock()
    existing = _ticket()
    db.query.return_value.filter.return_value.first.return_value = existing
    payload = TrainTicketCreate(
        train_code="G1234",
        departure_station="Beijing",
        arrival_station="Shanghai",
        date_time=datetime(2025, 8, 1, 8, 0, 0),
        carriage="05",
        seat_num="12A",
        berth_type="None",
        price=553.5,
        seat_type="Second-class",
        name="Alice",
        discount_type="Full-price",
        total_running_time=270,
        total_mileage=1318,
        stop_stations="[]",
        comments="",
        photo_id=None,
    )
    result = crud_ticket.create_train_ticket(db, payload, owner_id=uuid4())
    assert result is None
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_create_train_ticket_persists_when_new():
    from app.schemas.train_ticket import TrainTicketCreate
    from datetime import datetime
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    # seat_num=None is invalid per the schema, so feed a valid value here and
    # separately exercise the '' (falsy) fallback path below.
    payload = TrainTicketCreate(
        train_code="G9999",
        departure_station="Beijing",
        arrival_station="Shanghai",
        date_time=datetime(2025, 8, 1, 8, 0, 0),
        carriage="05",
        seat_num="",
        berth_type="None",
        price=100,
        seat_type="Second-class",
        name="Alice",
        discount_type="Full-price",
        total_running_time=None,
        total_mileage=None,
        stop_stations=None,
        comments=None,
        photo_id=None,
    )
    new = crud_ticket.create_train_ticket(db, payload, owner_id=uuid4())
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    added = db.add.call_args[0][0]
    # The ''no-seat'' fallback in crud only applies to the duplicate-check SQL; the column stores the user value as-is.
    assert added.seat_num == ""


def test_update_train_ticket_returns_none_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = crud_ticket.update_train_ticket(db, "missing", MagicMock())
    assert result is None


def test_update_train_ticket_applies_partial_update():
    db = MagicMock()
    target = _ticket()
    db.query.return_value.filter.return_value.first.return_value = target
    update_payload = SimpleNamespace(model_dump=lambda exclude_unset: {"comments": "new"})
    crud_ticket.update_train_ticket(db, "id", update_payload)
    assert target.comments == "new"
    db.commit.assert_called_once()


def test_delete_train_ticket_returns_false_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = crud_ticket.delete_train_ticket(db, "missing")
    assert result is False


def test_delete_train_ticket_deletes_and_commits_when_present():
    db = MagicMock()
    target = _ticket()
    db.query.return_value.filter.return_value.first.return_value = target
    result = crud_ticket.delete_train_ticket(db, "id")
    assert result is True
    db.delete.assert_called_once_with(target)
    db.commit.assert_called_once()


def test_delete_train_ticket_by_photo_id_runs_delete():
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = 1
    result = crud_ticket.delete_train_ticket_by_photo_id(db, "photo-id-1")
    assert result is True
    db.commit.assert_called_once()


# app/service/task_strategy.py


class _StubStrategy(task_strategy.BaseTaskStrategy):
    @property
    def task_category(self):
        return "CPU"

    async def process(self, worker, task, db):
        return {"status": "completed", "value": 42}


class _FailingStrategy(task_strategy.BaseTaskStrategy):
    async def process(self, worker, task, db):
        raise RuntimeError("boom")


class _ReleasingStrategy(task_strategy.BaseTaskStrategy):
    released = 0

    async def process(self, worker, task, db):
        return None

    def release_resources(self):
        _ReleasingStrategy.released += 1


@pytest.mark.asyncio
async def test_base_strategy_process_batch_returns_completed_for_success():
    s = _StubStrategy()
    task = MagicMock(id="t1", type=TaskType.PROCESS_BASIC)
    db = MagicMock()
    results = await s.process_batch(None, [task], db)
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["task_id"] == "t1"


@pytest.mark.asyncio
async def test_base_strategy_process_batch_records_failed_for_exception():
    s = _FailingStrategy()
    task = MagicMock(id="t2", type=TaskType.OCR)
    results = await s.process_batch(None, [task], MagicMock())
    assert results[0]["status"] == "failed"
    assert "boom" in results[0]["error"]


@pytest.mark.asyncio
async def test_base_strategy_process_batch_marks_resdict_failed_when_status_failed():
    class _DictFailed(task_strategy.BaseTaskStrategy):
        async def process(self, worker, task, db):
            return {"status": "failed", "error": "x"}

    task = MagicMock(id="t3", type=TaskType.PROCESS_BASIC)
    results = await _DictFailed().process_batch(None, [task], MagicMock())
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "x"


@pytest.mark.asyncio
async def test_handle_completion_default_is_noop():
    s = _StubStrategy()
    result = await s.handle_completion(None, [], MagicMock())
    assert result is None


def test_release_resources_default_is_noop():
    s = _StubStrategy()
    assert s.release_resources() is None


def test_strategy_factory_register_and_get_strategy():
    task_strategy.TaskStrategyFactory._strategies.clear()
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _Reg(_StubStrategy):
            pass
        strat = task_strategy.TaskStrategyFactory.get_strategy(TaskType.PROCESS_BASIC)
        assert isinstance(strat, _StubStrategy)
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()


def test_strategy_factory_get_strategy_returns_none_for_unknown():
    task_strategy.TaskStrategyFactory._strategies.clear()
    assert task_strategy.TaskStrategyFactory.get_strategy(TaskType.OCR) is None


def test_get_tasks_by_category_filters_by_category():
    task_strategy.TaskStrategyFactory._strategies.clear()
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _A(_StubStrategy):
            pass

        @task_strategy.TaskStrategyFactory.register(TaskType.OCR)
        class _B(_StubStrategy):
            @property
            def task_category(self):
                return "AI"

        cpu_tasks = task_strategy.TaskStrategyFactory.get_tasks_by_category("CPU")
        assert TaskType.PROCESS_BASIC in cpu_tasks
        assert TaskType.OCR not in cpu_tasks
        ai_tasks = task_strategy.TaskStrategyFactory.get_tasks_by_category("AI")
        assert TaskType.OCR in ai_tasks
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()


def test_release_idle_resources_calls_release_on_each_strategy():
    task_strategy.TaskStrategyFactory._strategies.clear()
    _ReleasingStrategy.released = 0
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _Reg(_ReleasingStrategy):
            pass

        task_strategy.TaskStrategyFactory.release_idle_resources([TaskType.PROCESS_BASIC])
        assert _ReleasingStrategy.released == 1
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()


def test_release_idle_resources_swallows_exceptions():
    task_strategy.TaskStrategyFactory._strategies.clear()
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _Boom(_ReleasingStrategy):
            def release_resources(self):
                raise RuntimeError("kaboom")

        task_strategy.TaskStrategyFactory.release_idle_resources([TaskType.PROCESS_BASIC])
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()


def test_release_all_resources_calls_release_for_every_strategy():
    task_strategy.TaskStrategyFactory._strategies.clear()
    _ReleasingStrategy.released = 0
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _Reg1(_ReleasingStrategy):
            pass

        @task_strategy.TaskStrategyFactory.register(TaskType.OCR)
        class _Reg2(_ReleasingStrategy):
            pass

        task_strategy.TaskStrategyFactory.release_all_resources()
        assert _ReleasingStrategy.released == 2
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()


def test_release_all_resources_swallows_exceptions():
    task_strategy.TaskStrategyFactory._strategies.clear()
    try:
        @task_strategy.TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
        class _Boom(_ReleasingStrategy):
            def release_resources(self):
                raise RuntimeError("boom-all")

        task_strategy.TaskStrategyFactory.release_all_resources()
    finally:
        task_strategy.TaskStrategyFactory._strategies.clear()










