"""HTTP-layer coverage for chapter endpoints left under-tested by previous nightly passes.

Tied to ``app.api.chapter`` endpoints that pure service-level tests do not exercise:
year-link validation (>30 or out-of-range), the discover idempotency path that
returns the active Task row instead of starting a new scan, the discovery task
lookup with ownership boundary, and the chapter action whitelist (any unknown
``action`` short-circuits to 404).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chapter import router
from app.api.deps import get_current_user
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.dependencies import get_db

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _build_client(db, owner):
    app = FastAPI()
    app.include_router(router, prefix="/api/chapters")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed_owner(db, name="chapter-http"):
    owner = User(id=uuid4(), username=name, hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    return owner


def _insert_task(db, *, owner_id, status=TaskStatus.PENDING, kind=TaskType.DISCOVER_CHAPTERS):
    row = Task(
        id=uuid4(),
        owner_id=owner_id,
        type=kind,
        status=status,
        payload={},
        result={"created": 0} if status == TaskStatus.COMPLETED else None,
    )
    db.add(row)
    db.commit()
    return row


def _stub_task_manager_module(monkeypatch, *, start_worker_returns=None, add_task_returns=None, add_task_calls=None):
    """Patch ``app.service.task_manager.TaskManager`` so the lazy import in
    ``app.api.chapter.discover_chapters`` sees the stub class. Returns the
    ``add_task`` stub so tests can introspect calls.
    """

    class _Stub:
        def __init__(self):
            self.start_worker_if_needed = lambda: start_worker_returns
            self._add_task_returns = add_task_returns
            self._add_task_calls = add_task_calls if add_task_calls is not None else []

        @staticmethod
        def get_instance():
            return instance

        def add_task(self, db, *, type, payload, owner_id, **kwargs):
            self._add_task_calls.append({"type": type, "payload": payload, "owner_id": owner_id})
            return self._add_task_returns or SimpleNamespace(id=uuid4(), status=TaskStatus.PENDING, result=None)

    instance = _Stub()
    monkeypatch.setattr("app.service.task_manager.TaskManager", _Stub)
    return instance, instance._add_task_calls


def test_year_links_validates_year_count_and_range(face_sqlite_session):
    db = face_sqlite_session
    owner = _seed_owner(db)
    client = _build_client(db, owner)

    too_many = client.get("/api/chapters/year-links", params=[("years", y) for y in range(2020, 2052)])
    assert too_many.status_code == 400
    assert "\u5e74\u4efd\u8303\u56f4\u65e0\u6548" in too_many.json()["detail"]

    under = client.get("/api/chapters/year-links", params={"years": [1899]})
    assert under.status_code == 400
    above = client.get("/api/chapters/year-links", params={"years": [2201]})
    assert above.status_code == 400

    ok = client.get("/api/chapters/year-links", params={"years": [2024, 2025]})
    assert ok.status_code == 200
    payload = ok.json()["data"]
    assert payload == {"2024": [], "2025": []}


def test_discover_returns_existing_active_task_and_does_not_start_new(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _seed_owner(db)
    active = _insert_task(db, owner_id=owner.id, status=TaskStatus.PROCESSING)
    stub, calls = _stub_task_manager_module(monkeypatch)

    client = _build_client(db, owner)
    response = client.post("/api/chapters/discover")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(active.id)
    assert data["status"] == TaskStatus.PROCESSING.value
    assert data["error"] is None
    assert calls == []


def test_discover_with_no_active_task_creates_new(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _seed_owner(db)
    new_task_id = uuid4()
    stub, calls = _stub_task_manager_module(
        monkeypatch,
        add_task_returns=SimpleNamespace(id=new_task_id, status=TaskStatus.PENDING, result=None),
    )

    client = _build_client(db, owner)
    response = client.post("/api/chapters/discover")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(new_task_id)
    assert data["status"] == TaskStatus.PENDING.value
    assert data["error"] is None
    assert len(calls) == 1
    assert calls[0]["type"] == TaskType.DISCOVER_CHAPTERS
    assert calls[0]["owner_id"] == owner.id


def test_latest_discovery_task_returns_none_when_idle(face_sqlite_session):
    db = face_sqlite_session
    owner = _seed_owner(db)
    _insert_task(db, owner_id=owner.id, status=TaskStatus.COMPLETED)
    client = _build_client(db, owner)

    response = client.get("/api/chapters/discover/tasks/latest")
    assert response.status_code == 200
    assert response.json()["data"] is None


def test_discovery_task_lookup_returns_404_for_foreign_or_missing(face_sqlite_session):
    db = face_sqlite_session
    owner = _seed_owner(db)
    stranger = _seed_owner(db, name="chapter-stranger")
    foreign = _insert_task(db, owner_id=stranger.id, status=TaskStatus.PENDING)

    client = _build_client(db, owner)
    foreign_resp = client.get(f"/api/chapters/discover/tasks/{foreign.id}")
    assert foreign_resp.status_code == 404

    missing_resp = client.get(f"/api/chapters/discover/tasks/{uuid4()}")
    assert missing_resp.status_code == 404


def test_discovery_task_lookup_returns_shape_for_owner(face_sqlite_session):
    db = face_sqlite_session
    owner = _seed_owner(db)
    task = _insert_task(db, owner_id=owner.id, status=TaskStatus.FAILED)
    client = _build_client(db, owner)

    response = client.get(f"/api/chapters/discover/tasks/{task.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(task.id)
    assert data["status"] == TaskStatus.FAILED.value
    assert data["error"] == "\u53d1\u73b0\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5"
    assert data["created"] == 0


def test_chapter_action_rejects_unknown_action_with_404(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    db = face_sqlite_session
    owner = _seed_owner(db)
    chapter_id = uuid4()

    def fail(*_args, **_kwargs):
        raise AssertionError("transition/serialize should not be called for unknown action")

    monkeypatch.setattr(service, "transition", fail)
    monkeypatch.setattr(service, "serialize", fail)

    client = _build_client(db, owner)
    response = client.post(
        f"/api/chapters/{chapter_id}/archive",
        json={"version": 1},
    )
    assert response.status_code == 404
    body = response.json()
    assert "\u64cd\u4f5c\u4e0d\u5b58\u5728" in body["detail"]


def test_chapter_action_whitelist_passes_to_transition(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _seed_owner(db)
    chapter_id = uuid4()

    captured = {}

    def fake_transition(_db, _owner, _cid, action, version):
        captured["args"] = (_owner, _cid, action, version)
        return SimpleNamespace(id=_cid, version=version + 1)

    def fake_serialize(_db, row):
        return {"id": str(row.id), "version": row.version}

    monkeypatch.setattr("app.service.chapter.transition", fake_transition)
    monkeypatch.setattr("app.service.chapter.serialize", fake_serialize)

    client = _build_client(db, owner)
    for action in ("confirm", "ignore", "restore", "hide", "unhide"):
        captured.clear()
        response = client.post(
            f"/api/chapters/{chapter_id}/{action}",
            json={"version": 2},
        )
        assert response.status_code == 200
        assert captured["args"][0] == owner.id
        assert captured["args"][1] == chapter_id
        assert captured["args"][2] == action
        assert captured["args"][3] == 2
        body = response.json()["data"]
        assert body == {"id": str(chapter_id), "version": 3}

