"""Nightly coverage for the journey task strategy, the live-photo parser base
and the agent search-summary error branches.

The 2026-10-27 backend coverage scan reported:

* ``service/tasks/journey.py`` at 81.2% -- lines 24-25 (the ``enqueue`` branch
  that fires once a discovery run creates 200 or more journeys) and lines
  38/41-43 (``AssociateJourneysStrategy.resource_key`` and the whole
  ``process`` body) were never executed.
* ``service/live_photo/base.py`` at 77.8% -- the two ``pass`` bodies of the
  abstract methods were never executed.
* ``service/agent/tools.py`` at 71.1% -- the ``except`` branches of the
  ``top_locations`` and ``top_tags`` aggregations inside
  ``_build_search_summary`` were never executed.

None of the branches need external services: the database is a temporary
SQLite file, the discovery helper and the reference station table are
replaced by small fakes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# service/tasks/journey.py -- AssociateJourneysStrategy
# ---------------------------------------------------------------------------


def _sqlite_bind(tmp_path):
    """A throwaway SQLite database with the full schema.

    ``_run`` opens a second session against the same bind to read the source
    train tickets, so the tables really have to exist.
    """
    import app.db.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'journey.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


class _FakeAiSession:
    """Stand-in for ``AIBatchSession`` -- records the write-lock handshake."""

    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.committed = False
        self.write_started = False
        self.rolled_back = False
        _FakeAiSession.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def begin_write(self):
        self.write_started = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_journey_strategy_reports_its_category_and_resource_key():
    from app.service.tasks.journey import AssociateJourneysStrategy

    strategy = AssociateJourneysStrategy()

    assert strategy.task_category == "CPU"
    assert strategy.resource_key == "journey"


def test_journey_strategy_rejects_a_task_without_owner():
    from app.service.tasks.journey import AssociateJourneysStrategy

    strategy = AssociateJourneysStrategy()
    task = SimpleNamespace(owner_id=None)

    with pytest.raises(ValueError, match="行程关联任务缺少所有者"):
        asyncio.run(strategy.process(worker=None, task=task, db=MagicMock()))


def test_journey_strategy_delegates_to_run_in_a_worker_thread(monkeypatch):
    from app.service.tasks.journey import AssociateJourneysStrategy
    import app.service.tasks.journey as journey_module

    calls = {}

    def fake_run(bind, owner_id):
        calls["bind"] = bind
        calls["owner_id"] = owner_id
        return {"created": 3, "memory_ids": ["a", "b", "c"]}

    monkeypatch.setattr(journey_module, "_run", fake_run)

    bind = object()
    db = MagicMock()
    db.get_bind.return_value = bind
    owner_7 = str(uuid4())
    task = SimpleNamespace(owner_id=owner_7)

    result = asyncio.run(AssociateJourneysStrategy().process(worker=None, task=task, db=db))

    assert result == {"created": 3, "memory_ids": ["a", "b", "c"]}
    assert calls == {"bind": bind, "owner_id": owner_7}


# ---------------------------------------------------------------------------
# service/tasks/journey.py -- _run
# ---------------------------------------------------------------------------


def _patch_journey_dependencies(monkeypatch, rows):
    """Replace the discovery call and the AI batch session."""
    import app.service.journey as journey_service
    import app.service.tasks.ai_runtime as ai_runtime

    monkeypatch.setattr(
        ai_runtime, "AIBatchSession", lambda **kwargs: _FakeAiSession(**kwargs)
    )
    monkeypatch.setattr(
        journey_service,
        "discover",
        lambda db, owner_id, _stations=None: list(rows),
    )
    return journey_service


def test_run_returns_the_created_journey_ids_without_queueing(monkeypatch, tmp_path):
    from app.service.tasks.journey import _run
    import app.service.journey_queue as journey_queue

    enqueued = []
    monkeypatch.setattr(journey_queue, "enqueue", lambda db, owner_id: enqueued.append(owner_id))
    _patch_journey_dependencies(monkeypatch, [SimpleNamespace(id="m-1"), SimpleNamespace(id="m-2")])

    owner_1 = str(uuid4())
    engine = _sqlite_bind(tmp_path)
    try:
        result = _run(engine, owner_1)
    finally:
        engine.dispose()

    assert result == {"created": 2, "memory_ids": ["m-1", "m-2"]}
    # Fewer than 200 journeys -> no queue hand-off.
    assert enqueued == []
    assert _FakeAiSession.instances[-1].committed is True
    assert _FakeAiSession.instances[-1].write_started is True


def test_run_queues_the_owner_once_two_hundred_journeys_are_discovered(monkeypatch, tmp_path):
    from app.service.tasks.journey import _run
    import app.service.journey_queue as journey_queue

    enqueued = []
    monkeypatch.setattr(journey_queue, "enqueue", lambda db, owner_id: enqueued.append(owner_id))
    rows = [SimpleNamespace(id=f"m-{index}") for index in range(200)]
    _patch_journey_dependencies(monkeypatch, rows)

    owner_2 = str(uuid4())
    engine = _sqlite_bind(tmp_path)
    try:
        result = _run(engine, owner_2)
    finally:
        engine.dispose()

    assert result["created"] == 200
    assert len(result["memory_ids"]) == 200
    assert enqueued == [owner_2]


def test_run_reads_the_station_names_from_the_source_tickets(monkeypatch, tmp_path):
    """The source ticket query feeds the reference station lookup.

    With at least one train ticket the helper asks for the station table; the
    empty case must not touch it at all.
    """
    from app.service.tasks.journey import _run
    from app.db.models.trip import TrainTicket
    import app.service.journey as journey_service

    requested = {}

    def fake_load_stations(names):
        requested["names"] = set(names)
        return {}

    monkeypatch.setattr(journey_service, "load_stations", fake_load_stations)
    _patch_journey_dependencies(monkeypatch, [])

    owner_3 = str(uuid4())
    engine = _sqlite_bind(tmp_path)
    Session = sessionmaker(bind=engine)
    try:
        with Session() as db:
            db.add(TrainTicket(
                owner_id=owner_3,
                train_code="G1",
                departure_station="北京",
                arrival_station="上海",
                date_time=datetime(2026, 1, 1, 8, 0, 0),
                carriage="01",
                seat_num="01A",
                price=100,
                seat_type="二等座",
                name="测试乘客",
            ))
            db.commit()
        result = _run(engine, owner_3)
    finally:
        engine.dispose()

    assert result == {"created": 0, "memory_ids": []}
    assert requested["names"] == {"北京", "上海"}


def test_run_skips_the_station_lookup_when_there_are_no_source_tickets(monkeypatch, tmp_path):
    from app.service.tasks.journey import _run
    import app.service.journey as journey_service

    def fail_load_stations(names):
        raise AssertionError("空图库不应触发车站查询")

    monkeypatch.setattr(journey_service, "load_stations", fail_load_stations)
    _patch_journey_dependencies(monkeypatch, [])

    owner_4 = str(uuid4())
    engine = _sqlite_bind(tmp_path)
    try:
        result = _run(engine, owner_4)
    finally:
        engine.dispose()

    assert result == {"created": 0, "memory_ids": []}


# ---------------------------------------------------------------------------
# service/live_photo/base.py -- abstract base
# ---------------------------------------------------------------------------


def test_live_photo_parser_cannot_be_instantiated_directly():
    from app.service.live_photo.base import LivePhotoParser

    with pytest.raises(TypeError):
        LivePhotoParser()


def test_live_photo_parser_base_methods_are_callable_from_a_subclass():
    """The base implementations are ``pass`` -- a subclass delegating to them
    executes the very lines the coverage scan flagged as missing."""
    from app.service.live_photo.base import LivePhotoParser

    class _Concrete(LivePhotoParser):
        def parse(self, file_path: str):
            return super().parse(file_path)

        def is_supported(self, file_path: str) -> bool:
            return super().is_supported(file_path)

    parser = _Concrete()

    assert parser.parse("a.jpg") is None
    assert parser.is_supported("a.jpg") is None


def test_live_photo_parser_subclass_must_implement_both_abstract_methods():
    from app.service.live_photo.base import LivePhotoParser

    class _OnlyParse(LivePhotoParser):
        def parse(self, file_path: str):
            return None

    with pytest.raises(TypeError):
        _OnlyParse()


# ---------------------------------------------------------------------------
# service/agent/tools.py -- _build_search_summary error branches
# ---------------------------------------------------------------------------


def _summary_db(filtered_query):
    """A ``db`` mock whose queries are dispatched by the queried entity.

    ``_build_search_summary`` issues four ``db.query`` calls: the date range,
    the city histogram, the tag histogram and two nested id sub-selects. A
    plain ``side_effect`` list would therefore hand the wrong handle to the
    wrong aggregation, so the mock dispatches on the first argument instead.
    """
    from app.db.models.photo_metadata import PhotoMetadata
    from app.db.models.tag import PhotoTag

    db = MagicMock()
    date_query = MagicMock()
    date_query.filter.return_value.first.return_value = (None, None)
    city_query = MagicMock()
    tag_query = MagicMock()

    def query(*args, **kwargs):
        if len(args) == 1:
            # ``Photo.id.in_(db.query(id_subq.c.id))`` -- the id sub-select.
            return MagicMock()
        if args[0] is PhotoMetadata.city:
            return city_query
        if args[0] is PhotoTag.tag_name:
            return tag_query
        return date_query

    db.query.side_effect = query
    return db, date_query, city_query, tag_query


def test_search_summary_keeps_the_other_sections_when_the_city_aggregation_fails():
    from app.service.agent.tools import _build_search_summary

    filtered = MagicMock()
    db, _date_query, city_query, tag_query = _summary_db(filtered)
    city_query.filter.side_effect = RuntimeError("city query exploded")
    tag_query.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ("海景", 3)
    ]

    summary = _build_search_summary(db, filtered, None)

    # The failing section is dropped, the healthy one is still reported.
    assert "top_locations" not in summary
    assert summary["top_tags"] == {"海景": 3}


def test_search_summary_keeps_the_other_sections_when_the_tag_aggregation_fails():
    from app.service.agent.tools import _build_search_summary

    filtered = MagicMock()
    db, _date_query, city_query, tag_query = _summary_db(filtered)
    city_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ("武汉", 5)
    ]
    tag_query.join.side_effect = RuntimeError("tag query exploded")

    summary = _build_search_summary(db, filtered, None)

    assert summary["top_locations"] == {"武汉": 5}
    assert "top_tags" not in summary
