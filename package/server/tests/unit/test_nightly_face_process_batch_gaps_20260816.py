"""Unit tests covering 2026-08-16 nightly coverage gap scan (round 10).

Modules exercised:
* app/service/tasks/face.py -- RecognizeFaceStrategy.process_batch
* app/service/tasks/face.py -- RecognizeFaceStrategy.process_single_photo
* app/service/tasks/face.py -- RecognizeFaceStrategy.release_resources noop
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _task(**kw):
    base = {
        "id": uuid4(),
        "type": None,
        "owner_id": uuid4(),
        "payload": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _photo(**kw):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "file_type": 0,
        "file_path": "/tmp/p.jpg",
        "processed_tasks": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_ai_config(api_url="http://ai:8001", threshold=0.4):
    class _Ai:
        ai_api_url = api_url
        face_recognition_threshold = threshold
        face_cluster_threshold = 0.5
        face_rescan_auto_match_threshold = 0.45
        face_rescan_candidate_threshold = 0.5
        face_rescan_removal_threshold = 0.6
        face_recognition_min_photos = 5
    class _Cfg:
        ai = _Ai()
    return _Cfg()


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload
    async def json(self):
        return self._payload
    async def __aenter__(self):
        return self
    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.last_payload = None
        self.call_count = 0
    def post(self, url, json=None):
        self.last_payload = json
        self.call_count += 1
        resp = self._responses.pop(0) if self._responses else _FakeResp(500, {})
        return resp
    async def __aenter__(self):
        return self
    async def __aexit__(self, *exc):
        return False


def _patch_aiohttp(monkeypatch, session):
    monkeypatch.setattr("aiohttp.ClientSession", lambda: session)


def _patch_open_ok(monkeypatch, payload=b"x"):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=MagicMock(read=lambda: payload))
    cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("builtins.open", lambda *a, **kw: cm)


def _patch_open_raises(monkeypatch, exc):
    def _boom(*a, **kw):
        raise exc
    monkeypatch.setattr("builtins.open", _boom)


def _patch_cluster(monkeypatch, **methods):
    cluster = MagicMock()
    cluster.assign_face_to_identity.return_value = None
    cluster.process_unassigned_faces.return_value = None
    for k, v in methods.items():
        setattr(cluster, k, v)
    factory = lambda db, owner_id: cluster
    monkeypatch.setattr("app.service.tasks.face.FaceClusterService", factory)
    return cluster


def _patch_user_config(monkeypatch):
    monkeypatch.setattr(
        "app.service.tasks.face.config_manager.get_user_config",
        lambda *a, **kw: _make_ai_config(),
    )


def test_face_process_batch_empty_returns_empty():
    from app.service.tasks.face import RecognizeFaceStrategy
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [], MagicMock()))
    assert res == []


def test_face_process_batch_generator_only_calls_process(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    s = RecognizeFaceStrategy()
    gen_task = _task(payload={})
    async def fake_process(worker, task, db):
        return {"generated_tasks": 3, "processed": 0}
    monkeypatch.setattr(s, "process", fake_process)
    res = _run(s.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["generated_tasks"] == 3


def test_face_process_batch_generator_failed_status_marked(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    s = RecognizeFaceStrategy()
    gen_task = _task(payload={})
    async def fake_process(worker, task, db):
        return {"status": "failed", "error": "boom"}
    monkeypatch.setattr(s, "process", fake_process)
    res = _run(s.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert res[0]["status"] == "failed"
    assert res[0]["error"] == "boom"


def test_face_process_batch_generator_exception_caught(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    s = RecognizeFaceStrategy()
    gen_task = _task(payload={})
    async def fake_process(worker, task, db):
        raise RuntimeError("gen-fail")
    monkeypatch.setattr(s, "process", fake_process)
    res = _run(s.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert res[0]["status"] == "failed"
    assert "gen-fail" in res[0]["error"]


def test_face_process_batch_photo_not_found_skipped(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    p = _photo()
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert len(res) == 1
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["status"] == "skipped"
    assert "photo not found" in res[0]["result"]["reason"]


def test_face_process_batch_already_processed_skipped(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={"face": True})
    db.query.return_value.filter.return_value.all.return_value = [p]
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["result"]["status"] == "skipped"
    assert "already processed" in res[0]["result"]["reason"]


def test_face_process_batch_force_reruns_already_processed(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={"face": True})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/dev/null/photo.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": []}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id), "force": True})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["status"] == "success"
    assert res[0]["result"]["faces_found"] == 0


def test_face_process_batch_file_not_found(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: None)
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["status"] == "failed"
    assert "file not found" in res[0]["error"]


def test_face_process_batch_read_file_error(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_raises(monkeypatch, OSError("disk gone"))
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["status"] == "failed"
    assert "read file error" in res[0]["error"]


def test_face_process_batch_ai_non_200_marks_failed(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([_FakeResp(502, {})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["status"] == "failed"
    assert "AI Service error: 502" in res[0]["error"]


def test_face_process_batch_ai_result_error_marks_failed(monkeypatch):
    """AI 200 but per-photo error field causes that photo's task to fail.

    Both photos share the same owner_id so they end up in a single AI batch.
    """
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    owner = uuid4()
    p1 = _photo(owner_id=owner, processed_tasks={})
    p2 = _photo(owner_id=owner, processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p1, p2]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([_FakeResp(200, {"results": [
        {"error": "decode failed"},
        {"faces": [{"det_score": 0.9, "embedding": [0.1]}]},
    ]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch, assign_face_to_identity=MagicMock(return_value=uuid4()))
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    t1 = _task(owner_id=owner, payload={"photo_id": str(p1.id)})
    t2 = _task(owner_id=owner, payload={"photo_id": str(p2.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t1, t2], db))
    by_task = {r["task_id"]: r for r in res}
    assert by_task[t1.id]["status"] == "failed"
    assert "decode failed" in by_task[t1.id]["error"]
    assert by_task[t2.id]["status"] == "completed"
    assert by_task[t2.id]["result"]["faces_found"] == 1


def test_face_process_batch_groups_by_owner(monkeypatch):
    """Tasks with different owner_ids produce independent AI requests."""
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    pa = _photo(processed_tasks={})
    pb = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [pa, pb]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([
        _FakeResp(200, {"results": [{"faces": []}]}),
        _FakeResp(200, {"results": [{"faces": []}]}),
    ])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    ta = _task(owner_id=pa.owner_id, payload={"photo_id": str(pa.id)})
    tb = _task(owner_id=pb.owner_id, payload={"photo_id": str(pb.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [ta, tb], db))
    assert session.call_count == 2
    assert all(r["status"] == "completed" for r in res)


def test_face_process_batch_threshold_filters_face(monkeypatch):
    """Faces below threshold are skipped."""
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.1, "embedding": [0.1]},
        {"det_score": 0.95, "embedding": [0.2]},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    monkeypatch.setattr("app.service.tasks.face.config_manager.get_user_config", lambda *a, **kw: _make_ai_config(threshold=0.4))
    cluster = _patch_cluster(monkeypatch, assign_face_to_identity=MagicMock(return_value=uuid4()))
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["result"]["faces_found"] == 1
    cluster.assign_face_to_identity.assert_called_once()


def test_face_process_batch_cluster_exception_swallowed(monkeypatch):
    """assign_face_to_identity raising does not fail the photo."""
    from app.service.tasks.face import RecognizeFaceStrategy
    db = MagicMock()
    p = _photo(processed_tasks={})
    db.query.return_value.filter.return_value.all.return_value = [p]
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.9, "embedding": [0.1]},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch, assign_face_to_identity=MagicMock(side_effect=RuntimeError("cluster down")))
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    t = _task(owner_id=p.owner_id, payload={"photo_id": str(p.id)})
    s = RecognizeFaceStrategy()
    res = _run(s.process_batch(MagicMock(), [t], db))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["status"] == "success"


def test_face_process_single_photo_file_not_found(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    _patch_user_config(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: None)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), _photo(), MagicMock()))
    assert res["status"] == "failed"
    assert "file not found" in res["error"]


def test_face_process_single_photo_ai_non_200(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(503, {})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), _photo(), MagicMock()))
    assert res["status"] == "failed"
    assert "AI Service error: 503" in res["error"]


def test_face_process_single_photo_ai_result_error(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(200, {"results": [{"error": "bad image"}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), _photo(), MagicMock()))
    assert res["status"] == "failed"
    assert "bad image" in res["error"]


def test_face_process_single_photo_success_with_embedding(monkeypatch):
    from app.service.tasks.face import RecognizeFaceStrategy
    p = _photo()
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.9, "embedding": [0.1, 0.2]},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    cluster = _patch_cluster(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), p, MagicMock()))
    assert res["status"] == "success"
    assert res["faces_found"] == 1
    cluster.process_unassigned_faces.assert_called_once()


def test_face_process_single_photo_face_no_embedding(monkeypatch):
    """No embedding -> no clustering call; photo still success."""
    from app.service.tasks.face import RecognizeFaceStrategy
    p = _photo()
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.9, "embedding": None},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    cluster = _patch_cluster(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), p, MagicMock()))
    assert res["status"] == "success"
    assert res["faces_found"] == 1
    cluster.assign_face_to_identity.assert_not_called()
    cluster.process_unassigned_faces.assert_not_called()


def test_face_process_single_photo_cluster_exception_swallowed(monkeypatch):
    """assign_face_to_identity raising -> logged, photo still success."""
    from app.service.tasks.face import RecognizeFaceStrategy
    p = _photo()
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.9, "embedding": [0.1]},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch, assign_face_to_identity=MagicMock(side_effect=RuntimeError("cluster down")))
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), p, MagicMock()))
    assert res["status"] == "success"
    assert res["faces_found"] == 1


def test_face_process_single_photo_unassigned_faces_exception(monkeypatch):
    """process_unassigned_faces raising is swallowed; photo still success."""
    from app.service.tasks.face import RecognizeFaceStrategy
    p = _photo()
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_ok(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_image_dimensions", lambda *a, **kw: (10, 10, None))
    session = _FakeSession([_FakeResp(200, {"results": [{"faces": [
        {"det_score": 0.9, "embedding": [0.1]},
    ]}]})])
    _patch_aiohttp(monkeypatch, session)
    _patch_user_config(monkeypatch)
    _patch_cluster(monkeypatch, process_unassigned_faces=MagicMock(side_effect=RuntimeError("batch down")))
    monkeypatch.setattr("app.service.tasks.face.crud_face.delete_faces_by_photo", lambda db, pid: None)
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *a, **kw: None)
    s = RecognizeFaceStrategy()
    res = _run(s.process_single_photo(MagicMock(), p, MagicMock()))
    assert res["status"] == "success"


def test_face_process_single_photo_outer_exception_marks_false_and_reraises(monkeypatch):
    """Outer Exception -> processed_tasks.face=False, then re-raise."""
    from app.service.tasks.face import RecognizeFaceStrategy
    p = _photo()
    _patch_user_config(monkeypatch)
    monkeypatch.setattr("app.service.tasks.face.storage.get_available_photo_path", lambda *a, **kw: "/tmp/x.jpg")
    _patch_open_raises(monkeypatch, RuntimeError("outer boom"))
    s = RecognizeFaceStrategy()
    with pytest.raises(RuntimeError, match="outer boom"):
        _run(s.process_single_photo(MagicMock(), p, MagicMock()))
    assert p.processed_tasks.get("face") is False


def test_face_release_resources_is_noop():
    from app.service.tasks.face import RecognizeFaceStrategy
    RecognizeFaceStrategy().release_resources()
