"""Nightly coverage guards for the largest remaining backend blind spots.

These tests deliberately exercise small pure or mockable branches so they stay
fast while covering edge cases found in the 2026-11-04 nightly report.
"""
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from app.api import media
from app.service import face_cluster as face_cluster_module
from app.service.agent import search_planner
from app.service import storage
from app.service import task_worker


def _face_service():
    service = face_cluster_module.FaceClusterService.__new__(
        face_cluster_module.FaceClusterService
    )
    service.DISTANCE_THRESHOLD = 0.4
    service.MAX_RESCAN_PROTOTYPES = 2
    service.MAX_RESCAN_REFERENCE_SAMPLE = 2
    return service


def test_face_cluster_consistent_component_uses_default_as_tie_breaker():
    service = _face_service()
    embeddings = [
        np.array([1.0, 0.0]),
        np.array([1.0, 0.0]),
        np.array([0.0, 1.0]),
        np.array([0.0, 1.0]),
    ]
    selected = service._select_consistent_component(embeddings, [1, 2, 3, 4], 4)
    assert selected == [2, 3]


def test_face_cluster_diverse_prototypes_stop_on_duplicate_embedding():
    service = _face_service()
    duplicate = np.array([1.0, 0.0])
    prototypes = service._select_diverse_prototypes([duplicate] * 4)
    assert len(prototypes) == 1
    np.testing.assert_array_equal(prototypes[0], duplicate)


def test_face_cluster_reference_sampling_includes_default_face():
    service = _face_service()
    faces = [SimpleNamespace(id=index) for index in range(5)]
    indices = service._sample_reference_indices(5, faces, default_face_id=2)
    assert indices == [0, 2, 4]


def _worker_like():
    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker.adaptive_limits = {}
    worker._loop = None
    worker._wake_event = MagicMock()
    return worker


def test_task_worker_wake_sets_event_when_loop_is_closed():
    worker = _worker_like()
    worker._loop = SimpleNamespace(is_closed=lambda: True)
    worker.wake()
    worker._wake_event.set.assert_called_once_with()


def test_task_worker_wake_ignores_loop_shutdown_race():
    worker = _worker_like()
    worker._loop = MagicMock()
    worker._loop.is_closed.return_value = False
    worker._loop.call_soon_threadsafe.side_effect = RuntimeError("loop closed")
    worker.wake()
    worker._wake_event.set.assert_not_called()


def test_task_worker_adaptive_limit_change_persists_synchronously():
    worker = _worker_like()
    worker._save_system_state = MagicMock()
    worker._publish = MagicMock()
    worker._on_resource_limit_change("cpu", 3, "aimd")
    assert worker.adaptive_limits == {"cpu": 3}
    worker._save_system_state.assert_any_call(
        "adaptive_resource_limits", {"cpu": 3}
    )
    worker._publish.assert_called_once_with(
        "task.concurrency", {"resource_key": "cpu", "limit": 3, "reason": "aimd"}
    )
    worker._wake_event.set.assert_called_once_with()


def test_media_normalizes_md5():
    assert (
        media._normalized_md5("  ABCDEF0123456789abcdef0123456789 ")
        == "abcdef0123456789abcdef0123456789"
    )


def test_media_rejects_invalid_md5():
    with pytest.raises(HTTPException) as exc_info:
        media._normalized_md5("not-an-md5")
    assert exc_info.value.status_code == 400


def test_media_backup_check_rejects_invalid_source_time():
    with pytest.raises(HTTPException) as exc_info:
        media.check_mobile_backup_assets(
            {"keys": [], "hashes": [], "source_times": {"photo": "not-a-date"}},
            db=MagicMock(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )
    assert exc_info.value.status_code == 400
    assert "source_times" in exc_info.value.detail


def test_media_mobile_metadata_commit_refreshes_only_changed_photo():
    db = MagicMock()
    photo = SimpleNamespace(photo_time=None, upload_time=None, md5=None)
    source_time = datetime(2024, 5, 1, 12, 30, tzinfo=timezone.utc)
    result = media._apply_mobile_source_metadata(
        db, photo, source_time, "abcdef0123456789abcdef0123456789"
    )
    assert result is photo
    assert photo.photo_time == source_time.replace(tzinfo=None)
    assert photo.md5 == "abcdef0123456789abcdef0123456789"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(photo)


def test_storage_update_root_cache_accepts_base_and_user_layout_paths(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(storage, "_STORAGE_ROOT_CACHE", {})
    monkeypatch.setattr(
        storage.user_storage,
        "cache_storage_base",
        lambda user_id, base: recorded.append((str(user_id), base)) or base,
    )
    monkeypatch.setattr(
        storage.user_storage,
        "ensure_user_layout",
        lambda user_id, base: str(tmp_path / "layout"),
    )

    user_id = str(uuid.uuid4())
    base = tmp_path / "storage"
    storage.update_storage_root_cache(user_id, str(base))
    storage.update_storage_root_cache(user_id, str(base / "users" / user_id))

    assert [item[1] for item in recorded] == [str(base), str(base)]
    assert storage._STORAGE_ROOT_CACHE[user_id] == str(base)


def test_storage_update_root_cache_logs_layout_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_STORAGE_ROOT_CACHE", {})
    monkeypatch.setattr(storage.user_storage, "cache_storage_base", lambda *_: None)
    monkeypatch.setattr(
        storage.user_storage,
        "ensure_user_layout",
        MagicMock(side_effect=OSError("read-only volume")),
    )
    storage.update_storage_root_cache("user", str(tmp_path))
    assert storage._STORAGE_ROOT_CACHE["user"] == str(tmp_path)


def test_storage_video_dimensions_uses_ffmpeg_probe_without_cv2(monkeypatch):
    monkeypatch.setattr(storage, "cv2", None, raising=False)
    monkeypatch.setattr(storage, "probe_video", lambda _path: (640, 480, 2.5))
    assert storage.get_image_dimensions("movie.mp4") == (640, 480, 2.5)


def test_search_planner_keeps_only_unsupported_constraints_quoted_by_user():
    model = MagicMock()
    payload = {"location": "上海", "unsupported": ["person_ids", "排除最近删除"]}
    model.bind.return_value.invoke.return_value = SimpleNamespace(
        content=json.dumps(payload, ensure_ascii=False)
    )
    history = [
        HumanMessage(content="请搜索上海照片，排除最近删除"),
        AIMessage(content="好的"),
    ]
    plan = search_planner.extract_search_plan(model, "上海照片", history=history)
    assert plan.location == "上海"
    assert plan.unsupported == ["排除最近删除"]
    history_prompt = model.bind.return_value.invoke.call_args.args[0][1].content
    assert "排除最近删除" in history_prompt


def test_search_planner_resolve_plan_rejects_unsupported_constraints():
    plan = search_planner.SearchPlan(unsupported=["排除最近删除"])
    with pytest.raises(ValueError, match="暂时无法准确执行"):
        search_planner.resolve_plan(MagicMock(), uuid.uuid4(), plan)


def test_search_planner_executor_hides_unexpected_provider_failure(monkeypatch):
    @contextmanager
    def broken_session():
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(search_planner, "SessionLocal", broken_session)
    executor = search_planner.PhotoSearchExecutor(MagicMock(), str(uuid.uuid4()), None)
    assert executor._search("上海") == {
        "error": "搜索服务暂时不可用，请稍后重试。"
    }




