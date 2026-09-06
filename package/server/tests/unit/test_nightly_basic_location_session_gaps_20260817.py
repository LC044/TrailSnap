"""Unit tests for nightly coverage gap scan (round 13, 2026-08-17).

Targets:
  * app.service.tasks.basic.BasicTaskStrategy.process_batch (happy,
    file-not-found, batch failure, min_width filter, live_photo).
  * app.crud.location.get_map_markers, get_location_statistics,
    get_timeline_nodes, search_locations.
  * app.db.session engine creation (sqlite / postgres branches).

Other nightly rounds already cover:
  * BasicTaskStrategy happy/release_resources (test_basic_tasks.py).
  * location_stats pure helpers (test_nightly_crud_location_stats_helpers_gaps_20260812.py).
  * sqlalchemy session/transaction (test_sqlalchemy_session.py).
"""
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _task(task_id=None, owner_id=None, payload=None):
    return SimpleNamespace(
        id=task_id if task_id is not None else uuid4(),
        type="process_basic",
        payload=payload if payload is not None else {},
        owner_id=owner_id if owner_id is not None else uuid4(),
    )


def _filter(min_width=0, min_height=0, enable=True):
    return SimpleNamespace(
        enable=enable,
        min_width=min_width,
        min_height=min_height,
    )


def _run_async(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _chain(return_value):
    """Build a MagicMock chain where any of the common SQLAlchemy builder
    methods returns the same chain and ``.all()`` returns ``return_value``."""
    chain = MagicMock()
    chain.join.return_value = chain
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    chain.distinct.return_value = chain
    chain.limit.return_value = chain
    chain.group_by.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = return_value
    return chain


# ---------------------------------------------------------------------------
# BasicTaskStrategy.process_batch
# ---------------------------------------------------------------------------
class TestBasicTaskStrategy:
    def _strategy(self):
        from app.service.tasks import basic
        return basic.BasicTaskStrategy()

    def _setup_worker(self):
        worker = MagicMock()
        worker.thread_pool = MagicMock()
        worker.scan_status = {"added": 0, "processed_files": 0}
        return worker

    def _patch_run_in_executor(self, fake_results):
        """Bypass ``loop.run_in_executor`` by returning an awaitable that
        resolves to ``fake_results`` -- avoids invoking the real
        ``concurrent.futures.Future`` wrapper on a MagicMock thread pool."""
        from app.service.tasks import basic

        async def _fake_executor(*_args, **_kwargs):
            return fake_results

        fake_loop = MagicMock()
        fake_loop.run_in_executor.side_effect = _fake_executor
        return patch.object(basic.asyncio, "get_running_loop", return_value=fake_loop)

    def test_process_batch_happy_path_completes(self):
        from app.service.tasks import basic

        worker = self._setup_worker()
        db = MagicMock()
        owner = uuid4()
        task = _task(owner_id=owner, payload={"file_path": "/p/a.jpg", "user_id": str(owner)})

        cfg = MagicMock()
        cfg.filter = _filter(min_width=0, min_height=0, enable=False)

        fake_results = [
            {
                "task_id": task.id,
                "success": True,
                "thumb_path": "/t/a.jpg",
                "meta": {"photo_time": datetime(2026, 1, 1, 12, 0, 0), "exif_info": "{}"},
                "size": 1024,
                "width": 800,
                "height": 600,
                "duration": 0.0,
                "file_name": "a.jpg",
                "is_motion_photo": False,
                "md5_hash": "abc",
                "color_info": None,
            }
        ]

        with patch.object(basic.os.path, "exists", return_value=True), \
             self._patch_run_in_executor(fake_results), \
             patch.object(basic, "storage") as fake_storage, \
             patch.object(basic, "config_manager") as fake_cm:
            fake_storage._get_storage_root.return_value = "/srv"
            fake_cm.get_user_config.return_value = cfg

            results = _run_async(self._strategy().process_batch(worker, [task], db))

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert results[0]["result"]["photo_create_data"]["file_path"] == "/p/a.jpg"

    def test_process_batch_skips_missing_file(self):
        from app.service.tasks import basic

        worker = self._setup_worker()
        db = MagicMock()
        task = _task(payload={"file_path": "/p/missing.jpg", "user_id": "u1"})

        with patch.object(basic.os.path, "exists", return_value=False):
            results = _run_async(self._strategy().process_batch(worker, [task], db))

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert results[0]["result"]["status"] == "skipped"
        assert results[0]["result"]["reason"] == "file not found"

    def test_process_batch_reports_failure_when_batch_returns_error(self):
        from app.service.tasks import basic

        worker = self._setup_worker()
        db = MagicMock()
        task = _task(payload={"file_path": "/p/a.jpg", "user_id": "u1"})

        fake_results = [{"task_id": task.id, "success": False, "error": "boom"}]

        with patch.object(basic.os.path, "exists", return_value=True), \
             self._patch_run_in_executor(fake_results), \
             patch.object(basic, "config_manager") as fake_cm, \
             patch.object(basic, "storage") as fake_storage:
            fake_cm.get_user_config.return_value.filter = _filter(enable=False)
            fake_storage._get_storage_root.return_value = "/srv"

            results = _run_async(self._strategy().process_batch(worker, [task], db))

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "boom" in results[0]["error"]

    def test_process_batch_skips_when_min_width_filter_blocks(self):
        from app.service.tasks import basic

        worker = self._setup_worker()
        db = MagicMock()
        owner = uuid4()
        task = _task(owner_id=owner, payload={"file_path": "/p/tiny.jpg", "user_id": str(owner)})

        cfg = MagicMock()
        cfg.filter = _filter(min_width=1000, min_height=0, enable=True)

        fake_results = [
            {
                "task_id": task.id,
                "success": True,
                "meta": {"photo_time": datetime(2026, 1, 1), "exif_info": "{}"},
                "size": 10,
                "width": 100,
                "height": 50,
                "duration": 0,
                "file_name": "tiny.jpg",
                "is_motion_photo": False,
                "md5_hash": "x",
                "color_info": None,
            }
        ]

        with patch.object(basic.os.path, "exists", return_value=True), \
             self._patch_run_in_executor(fake_results), \
             patch.object(basic, "config_manager") as fake_cm, \
             patch.object(basic, "storage") as fake_storage:
            fake_cm.get_user_config.return_value = cfg
            fake_storage._get_storage_root.return_value = "/srv"

            results = _run_async(self._strategy().process_batch(worker, [task], db))

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert results[0]["result"]["status"] == "skipped"
        assert results[0]["result"]["reason"] == "filtered_by_width"

    def test_process_batch_marks_live_photo_when_flag_set(self):
        from app.service.tasks import basic
        from app.db.models.photo import FileType

        worker = self._setup_worker()
        db = MagicMock()
        owner = uuid4()
        task = _task(
            owner_id=owner,
            payload={
                "file_path": "/p/live.jpg",
                "user_id": str(owner),
                "is_live_photo": True,
            },
        )

        cfg = MagicMock()
        cfg.filter = _filter(enable=False)

        fake_results = [
            {
                "task_id": task.id,
                "success": True,
                "meta": {"photo_time": datetime(2026, 1, 1), "exif_info": "{}"},
                "size": 1,
                "width": 500,
                "height": 500,
                "duration": 0,
                "file_name": "live.jpg",
                "is_motion_photo": False,
                "md5_hash": "y",
                "color_info": None,
            }
        ]

        with patch.object(basic.os.path, "exists", return_value=True), \
             self._patch_run_in_executor(fake_results), \
             patch.object(basic, "config_manager") as fake_cm, \
             patch.object(basic, "storage") as fake_storage, \
             patch.object(basic.photo_schemas, "PhotoCreate") as fake_pc:
            fake_cm.get_user_config.return_value = cfg
            fake_storage._get_storage_root.return_value = "/srv"

            results = _run_async(self._strategy().process_batch(worker, [task], db))

        assert results[0]["status"] == "completed"
        assert fake_pc.call_args.kwargs["file_type"] == FileType.live_photo


# ---------------------------------------------------------------------------
# crud.location
# ---------------------------------------------------------------------------
class TestGetMapMarkers:
    def test_returns_list_of_dicts_with_id_lat_lng(self):
        from app.crud import location

        db = MagicMock()
        rows = [
            (UUID(int=1), 30.5, 114.3),
            (UUID(int=2), 31.0, 121.0),
        ]
        db.query.return_value = _chain(rows)

        markers = location.get_map_markers(db, uuid4())

        assert len(markers) == 2
        assert markers[0]["lat"] == 30.5
        assert markers[1]["lng"] == 121.0
        assert markers[0]["id"] == str(UUID(int=1))


class TestGetLocationStatistics:
    def test_zero_when_no_photos(self):
        from app.crud import location

        db = MagicMock()
        chain = MagicMock()
        chain.join.return_value.first.return_value = (None, None, None, None)
        db.query.return_value = chain

        stats = location.get_location_statistics(db, uuid4())

        assert stats == {
            "province_count": 0,
            "city_count": 0,
            "district_count": 0,
            "country_count": 0,
        }

    def test_positive_counts_when_metadata_present(self):
        from app.crud import location

        db = MagicMock()
        chain = MagicMock()
        chain.join.return_value.first.return_value = (3, 5, 7, 1)
        db.query.return_value = chain

        stats = location.get_location_statistics(db, uuid4())

        assert stats["province_count"] == 3
        assert stats["city_count"] == 5
        assert stats["district_count"] == 7
        assert stats["country_count"] == 1


class TestGetTimelineNodes:
    def test_merges_consecutive_rows_with_same_location(self):
        from app.crud import location

        cover1, cover2 = uuid4(), uuid4()
        row1 = SimpleNamespace(
            date="2026-01-01", loc_name="Shanghai", level="city",
            photo_count=2, lat=31.0, lng=121.0, cover_id=str(cover1),
        )
        row2 = SimpleNamespace(
            date="2026-01-02", loc_name="Shanghai", level="city",
            photo_count=3, lat=31.5, lng=121.5, cover_id=str(cover2),
        )

        db = MagicMock()
        db.query.return_value = _chain([row1, row2])

        resp = location.get_timeline_nodes(db, uuid4(), level="city")

        assert resp.total == 1
        node = resp.nodes[0]
        assert node.locationName == "Shanghai"
        assert node.photoCount == 5
        # Weighted-average lat: (31.0*2 + 31.5*3) / 5
        assert abs(node.lat - 31.3) < 1e-6
        # Merged ranges are normalized regardless of database row order.
        assert node.startDate == "2026-01-01"
        assert node.endDate == "2026-01-02"

        # coverId is NOT updated on merge -- stays at first-append.

    def test_creates_new_node_for_different_location(self):
        from app.crud import location

        row1 = SimpleNamespace(
            date="2026-01-01", loc_name="Shanghai", level="city",
            photo_count=1, lat=31.0, lng=121.0, cover_id=str(uuid4()),
        )
        row2 = SimpleNamespace(
            date="2026-01-02", loc_name="Beijing", level="city",
            photo_count=1, lat=39.9, lng=116.4, cover_id=str(uuid4()),
        )

        db = MagicMock()
        db.query.return_value = _chain([row1, row2])

        resp = location.get_timeline_nodes(db, uuid4(), level="city")

        assert resp.total == 2
        assert {n.locationName for n in resp.nodes} == {"Shanghai", "Beijing"}


class TestSearchLocations:
    def test_dedupes_province_city_district_labels(self):
        from app.crud import location

        province_chain = _chain([("上海",)])
        city_chain = _chain([("上海", "徐汇区")])
        district_chain = _chain([("上海", "徐汇区", "田林路")])

        db = MagicMock()
        db.query.side_effect = [province_chain, city_chain, district_chain]

        suggestions = location.search_locations(db, uuid4(), "上海")

        labels = [s["label"] for s in suggestions]
        assert "上海" in labels
        # city query returns ("上海", "徐汇区") -> label "上海徐汇区";
        # district query returns ("上海", "徐汇区", "田林路") -> label "上海徐汇区田林路".
        # Both province ("上海") and city ("上海徐汇区") labels are unique.
        assert labels.count("上海徐汇区") == 1
        assert "上海徐汇区田林路" in labels


# ---------------------------------------------------------------------------
# app.db.session engine creation branches
# ---------------------------------------------------------------------------
@contextmanager
def _reload_session_module(env):
    import importlib
    import os

    for k in ("TS_DESKTOP", "DB_URL", "TS_DB_URL"):
        os.environ.pop(k, None)
    for k, v in env.items():
        os.environ[k] = v

    import app.db.session as session_mod
    importlib.reload(session_mod)
    try:
        yield session_mod
    finally:
        for k in ("TS_DESKTOP", "DB_URL", "TS_DB_URL"):
            os.environ.pop(k, None)


class TestSessionModule:
    def test_sqlite_branch_creates_engine_with_check_same_thread_false(self):
        from app.core.paths import DATA_DIR

        with _reload_session_module({"TS_DB_URL": f"sqlite:///{DATA_DIR}/unit-test.sqlite"}) as m:
            assert m.IS_SQLITE is True
            assert m.engine is not None
            assert m.SessionLocal is not None

    def test_postgres_branch_creates_engine_with_pool(self):
        with _reload_session_module({"TS_DB_URL": "postgresql://user:pw@localhost:5432/db"}) as m:
            assert m.IS_SQLITE is False
            assert m.engine is not None
            assert m.SessionLocal is not None
