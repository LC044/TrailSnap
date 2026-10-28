"""Nightly coverage for the ticket-recognition task, the upgrade cleanup and
the portable-conversion target guards.

The 2026-10-27 backend coverage scan (round 2) reported:

* ``service/tasks/tickets.py`` at 82.5% -- 48 missed lines.  The missed code
  is the *validation* half of ``save_recognition_result``: the incomplete
  field guard, the "interface text pasted into a station name" guard and the
  duplicated departure/arrival guard.  A wrong answer here writes a nonsense
  ticket into the user's library.
* ``utils/automatic_upgrade.py`` at 58.4% -- 107 missed lines.  The cleanup
  path of ``finish`` (the code that actually *deletes* the old library) had
  never been executed; only its guards were covered.
* ``utils/portable_conversion.py`` at 46.7% -- 153 missed lines.  The
  ``validate_external_target`` guard, which keeps the new instance out of
  every scanned external gallery, had never been executed.

Every branch is exercised with a throw-away directory or a mocked session; no
service, database or network is required.
"""

from __future__ import annotations

import datetime
import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.tasks import tickets as tickets_task
from app.utils import automatic_upgrade, portable_conversion


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# service/tasks/tickets.py -- calculate_ticket_mileage_and_time
# ---------------------------------------------------------------------------


def _ticket(**overrides):
    from app.schemas.train_ticket import TrainTicketCreate

    defaults = dict(
        train_code="G1",
        departure_station="北京南",
        arrival_station="上海虹桥",
        date_time=datetime.datetime(2026, 1, 1, 8, 0),
        carriage="08",
        seat_num="12F",
        price="553.5",
        seat_type="二等座",
        name="张三",
    )
    defaults.update(overrides)
    return TrainTicketCreate(**defaults)


@pytest.mark.asyncio
async def test_calculate_mileage_uses_the_historical_distance(monkeypatch):
    ticket = _ticket()

    async def fake_schedule(code, day, departure, arrival):
        return {"distance_km": 1318.0, "duration_minutes": 300, "stops": []}

    monkeypatch.setattr(tickets_task, "get_schedule_info", fake_schedule)

    result = await tickets_task.calculate_ticket_mileage_and_time(ticket)

    assert result["total_mileage"] == 1318.0
    assert result["total_time"] == 300


@pytest.mark.asyncio
async def test_calculate_mileage_uses_the_endpoint_distance_as_a_fallback(monkeypatch):
    """Without a schedule distance the GPS endpoints provide an estimate."""
    ticket = _ticket()

    async def fake_schedule(code, day, departure, arrival):
        return {"duration_minutes": 300, "stops": []}

    async def fake_distance(candidate):
        return 1200.0

    monkeypatch.setattr(tickets_task, "get_schedule_info", fake_schedule)
    monkeypatch.setattr(tickets_task, "get_endpoint_distance", fake_distance)

    result = await tickets_task.calculate_ticket_mileage_and_time(ticket, evidence={"x": 1})

    assert result["total_mileage"] == 1200.0
    assert result["sources"]["distance_source"] == "gps-endpoints-haversine-x1.2"


@pytest.mark.asyncio
async def test_calculate_mileage_survives_an_unavailable_history(monkeypatch):
    ticket = _ticket()

    async def broken(code, day, departure, arrival):
        raise RuntimeError("history offline")

    monkeypatch.setattr(tickets_task, "get_schedule_info", broken)

    result = await tickets_task.calculate_ticket_mileage_and_time(ticket)

    assert result["total_mileage"] is None
    assert result["total_time"] is None
    assert result["stop_stations"] == []


@pytest.mark.asyncio
async def test_calculate_mileage_estimates_the_duration_from_the_distance(monkeypatch):
    """Without a schedule the duration is a rough speed estimate, never a schedule."""
    ticket = _ticket()

    async def fake_schedule(code, day, departure, arrival):
        return {"distance_km": 1200.0, "duration_minutes": None, "stops": []}

    monkeypatch.setattr(tickets_task, "get_schedule_info", fake_schedule)

    result = await tickets_task.calculate_ticket_mileage_and_time(ticket, evidence={})

    assert result["total_time"] == 360
    assert result["sources"]["duration_source"] == "estimated-distance-speed"


# ---------------------------------------------------------------------------
# service/tasks/tickets.py -- save_recognition_result validation
# ---------------------------------------------------------------------------


def _photo():
    return SimpleNamespace(id=uuid.uuid4(), owner_id=uuid.uuid4(), filename="ticket.jpg",
                           photo_time=datetime.datetime(2026, 1, 1, 8, 0), processed_tasks={})


def _strategy():
    return tickets_task.RecognizeTicketStrategy()


@pytest.mark.asyncio
async def test_save_recognition_result_rejects_a_malformed_payload():
    db = MagicMock()

    result = await _strategy().save_recognition_result(_photo(), {"tickets": "not-a-list"}, db)

    assert result["status"] == "failed"
    assert "格式无效" in result["error"]


@pytest.mark.asyncio
async def test_save_recognition_result_rejects_an_ai_error():
    db = MagicMock()

    result = await _strategy().save_recognition_result(
        _photo(), {"tickets": [], "error": "模型不可用"}, db
    )

    assert result["status"] == "failed"
    assert "模型不可用" in result["error"]


@pytest.mark.asyncio
async def test_save_recognition_result_rejects_incomplete_fields():
    db = MagicMock()

    result = await _strategy().save_recognition_result(
        _photo(),
        {"tickets": [{"train_code": "G1", "departure_station": "北京南",
                      "datetime": "2026-01-01 08:00"}]},
        db,
    )

    assert result["status"] == "failed"
    assert "关键字段不完整" in result["error"]


@pytest.mark.asyncio
async def test_save_recognition_result_rejects_interface_text_as_a_station():
    db = MagicMock()

    result = await _strategy().save_recognition_result(
        _photo(),
        {"tickets": [{"train_code": "G1", "departure_station": "去看看",
                      "arrival_station": "上海虹桥", "datetime": "2026-01-01 08:00"}]},
        db,
    )

    assert result["status"] == "failed"
    assert "界面文字" in result["error"]


@pytest.mark.asyncio
async def test_save_recognition_result_rejects_the_same_departure_and_arrival():
    db = MagicMock()

    result = await _strategy().save_recognition_result(
        _photo(),
        {"tickets": [{"train_code": "G1", "departure_station": "北京南",
                      "arrival_station": "北京南站", "datetime": "2026-01-01 08:00"}]},
        db,
    )

    assert result["status"] == "failed"
    assert "重复" in result["error"]


@pytest.mark.asyncio
async def test_save_recognition_result_accepts_a_valid_ticket(monkeypatch):
    db = MagicMock()
    photo = _photo()
    saved = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(tickets_task.crud_train_tickets, "create_train_ticket",
                        lambda db, ticket, owner_id=None, commit=False: saved)

    result = await _strategy().save_recognition_result(
        photo,
        {"tickets": [{"train_code": "G1", "departure_station": "北京南",
                      "arrival_station": "上海虹桥", "datetime": "2026-01-01 08:00"}]},
        db,
    )

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert result["tickets_existing"] == 0
    assert photo.processed_tasks["tickets"] is True


# ---------------------------------------------------------------------------
# utils/automatic_upgrade.py -- finish() cleanup
# ---------------------------------------------------------------------------


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _upgrade_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "instance"
    (root / "maintenance").mkdir(parents=True)
    (root / "userdata" / "data").mkdir(parents=True)
    legacy = tmp_path / "legacy"
    (legacy / "data").mkdir(parents=True)
    return root, legacy


@pytest.fixture
def unlocked_legacy(monkeypatch):
    """Replace the OS-level legacy lock with a no-op context manager.

    The real lock denies access to a library that is still open in another
    client (and needs a real SQLite file on Windows). The cleanup logic under
    test is independent of that guard.
    """
    @contextmanager
    def fake_lock(source):
        yield

    monkeypatch.setattr(automatic_upgrade, "_legacy_lock", fake_lock)


def _journal(root: Path, legacy: Path, **overrides) -> dict:
    job = {
        "schemaVersion": 1,
        "id": str(uuid.uuid4()),
        "source": str(legacy),
        "phase": "validated",
        "instance": {"instanceId": str(uuid.uuid4()),
                     "dataRoot": {"kind": "relative", "path": "userdata"}},
        "media": [],
        "files": [],
    }
    job.update(overrides)
    return job


def _install_job(root: Path, job: dict) -> None:
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json",
                {"instanceId": job["instance"]["instanceId"],
                 "dataRoot": {"kind": "relative", "path": "userdata"}})


def test_finish_deletes_only_the_recorded_and_unchanged_files(tmp_path, unlocked_legacy):
    from app.utils.portable_library import file_hash

    root, legacy = _upgrade_root(tmp_path)
    managed = legacy / "data" / "photos.db"
    managed.write_bytes(b"payload")
    keep = legacy / "notes.txt"
    keep.write_bytes(b"notes")

    job = _journal(root, legacy, files=[
        {"path": "data/photos.db", "sha256": file_hash(managed), "cleanup": True},
        {"path": "notes.txt", "sha256": file_hash(keep), "cleanup": False},
    ])
    _install_job(root, job)

    result = automatic_upgrade.finish(root, "cleanup")

    assert result["phase"] == "completed"
    assert not managed.exists()
    # A file that is not marked for cleanup may belong to another application.
    assert keep.exists()


def test_finish_refuses_to_delete_a_changed_file(tmp_path, unlocked_legacy):
    from app.utils.portable_library import file_hash

    root, legacy = _upgrade_root(tmp_path)
    managed = legacy / "data" / "photos.db"
    managed.write_bytes(b"payload")

    job = _journal(root, legacy, files=[
        {"path": "data/photos.db", "sha256": file_hash(managed), "cleanup": True},
    ])
    _install_job(root, job)
    # The user edited the legacy file after the upgrade was published.
    managed.write_bytes(b"changed")

    with pytest.raises(ValueError, match="旧数据已变化"):
        automatic_upgrade.finish(root, "cleanup")

    assert managed.exists()


def test_finish_refuses_an_escaping_cleanup_path(tmp_path, unlocked_legacy):
    root, legacy = _upgrade_root(tmp_path)
    job = _journal(root, legacy, files=[
        {"path": "../outside.txt", "sha256": "0" * 64, "cleanup": True},
    ])
    _install_job(root, job)

    with pytest.raises(ValueError, match="清理路径无效"):
        automatic_upgrade.finish(root, "cleanup")


def test_finish_refuses_an_absolute_cleanup_path(tmp_path, unlocked_legacy):
    root, legacy = _upgrade_root(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"x")

    job = _journal(root, legacy, files=[
        {"path": str(outside), "sha256": "0" * 64, "cleanup": True},
    ])
    _install_job(root, job)

    with pytest.raises(ValueError, match="清理路径无效"):
        automatic_upgrade.finish(root, "cleanup")


def test_finish_stops_when_a_recorded_file_disappeared(tmp_path, unlocked_legacy):
    root, legacy = _upgrade_root(tmp_path)
    job = _journal(root, legacy, files=[
        {"path": "data/gone.db", "sha256": "0" * 64, "cleanup": True},
    ])
    _install_job(root, job)

    with pytest.raises(ValueError, match="旧数据已变化"):
        automatic_upgrade.finish(root, "cleanup")


def test_finish_keeps_going_for_a_missing_file_after_the_commit_phase(tmp_path, unlocked_legacy):
    """Once the journal is committed a vanished file must not abort the run."""
    root, legacy = _upgrade_root(tmp_path)
    job = _journal(root, legacy, phase="committed", files=[
        {"path": "data/gone.db", "sha256": "0" * 64, "cleanup": True},
    ])
    _install_job(root, job)

    result = automatic_upgrade.finish(root, "cleanup")

    assert result["phase"] == "completed"


# ---------------------------------------------------------------------------
# utils/portable_conversion.py -- validate_external_target
# ---------------------------------------------------------------------------


def test_validate_external_target_rejects_the_external_folder_itself(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    preview = {"externalRoots": [{"path": str(external), "ownerId": "u", "available": True}]}

    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        portable_conversion.validate_external_target(preview, external)


def test_validate_external_target_rejects_a_folder_inside_the_external_root(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    inside = external / "instance"
    preview = {"externalRoots": [{"path": str(external), "ownerId": "u", "available": True}]}

    with pytest.raises(ValueError, match="互相包含"):
        portable_conversion.validate_external_target(preview, inside)


def test_validate_external_target_rejects_a_folder_that_contains_the_external_root(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    preview = {"externalRoots": [{"path": str(external), "ownerId": "u", "available": True}]}

    with pytest.raises(ValueError, match="互相包含"):
        portable_conversion.validate_external_target(preview, tmp_path)


def test_validate_external_target_accepts_a_sibling_folder(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    sibling = tmp_path / "instance"
    sibling.mkdir()
    preview = {"externalRoots": [{"path": str(external), "ownerId": "u", "available": True}]}

    portable_conversion.validate_external_target(preview, sibling)
