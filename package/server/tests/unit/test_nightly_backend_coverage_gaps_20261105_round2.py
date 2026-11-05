"""Round-two guards for the 2026-11-05 nightly backend coverage scan.

The first round already covered small API/service edges.  These tests target
the remaining lowest-coverage modules with pure helpers and mocked queries so
they add deterministic coverage without starting services.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import HTTPException

from app.api import media
from app.service import chapter
from app.service import face_cluster as face_cluster_module
from app.service import storage
from app.service import task_worker


pytestmark = pytest.mark.smoke


# ------------------------------- api/media.py -------------------------------


@pytest.mark.parametrize(
    "chunks,expected",
    [
        ([], "missing or out of sequence"),
        ([0, 2], "missing or out of sequence"),
        ([0, 1, 2, 3], "count does not match"),
    ],
)
def test_media_chunk_sequence_rejects_invalid_batches(chunks, expected):
    with pytest.raises(ValueError, match=expected):
        media._validate_chunk_sequence(chunks, expected_chunks=3)


def test_media_live_photo_companion_path_normalizes_heic_mov_case():
    path = media._live_photo_video_path(
        r"C:/photos/2026/IMG_0001.HEIC", "companion.MOV"
    )

    assert path.endswith("IMG_0001.MOV")


@pytest.mark.parametrize(
    "image_name,video_name,message",
    [
        ("photo.png", "video.mp4", "Unsupported live photo image type"),
        ("photo.jpg", "video.webm", "Unsupported live photo video type"),
    ],
)
def test_media_live_photo_companion_path_validates_extensions(
    image_name, video_name, message
):
    with pytest.raises(ValueError, match=message):
        media._live_photo_video_path(f"C:/photos/{image_name}", video_name)


def test_media_normalizes_valid_sha256_and_accepts_missing_value():
    digest = "A" * 64
    assert media._normalized_sha256(digest) == digest.lower()
    assert media._normalized_sha256(None) is None


def test_media_rejects_invalid_sha256():
    with pytest.raises(HTTPException) as exc_info:
        media._normalized_sha256("not-a-sha")

    assert exc_info.value.status_code == 400


# --------------------------- service/face_cluster.py ---------------------------


def _face_service():
    service = face_cluster_module.FaceClusterService.__new__(
        face_cluster_module.FaceClusterService
    )
    service.MANUAL_ASSIGNMENT_CONFIDENCE = 0.95
    return service


@pytest.mark.parametrize(
    "confidence,expected", [(0.96, True), (0.94, False), (None, False)]
)
def test_face_cluster_manual_confirmation_requires_high_confidence(
    confidence, expected
):
    face = SimpleNamespace(recognize_confidence=confidence)

    assert _face_service()._is_manually_confirmed(face) is expected


def test_face_cluster_cosine_distance_is_clipped_for_opposite_vectors():
    distance = face_cluster_module.FaceClusterService._cosine_distance(
        np.array([1.0]), np.array([-1.0])
    )

    assert distance == 2.0


# ---------------------------- service/task_worker.py ----------------------------


def _worker_like():
    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker.system_pressure = {"cpu": 0.0, "memory": 0.0}
    worker._get_resource_limits = MagicMock(return_value={"cpu": 7})
    return worker


def test_task_worker_import_floor_is_one_under_memory_pressure(monkeypatch):
    worker = _worker_like()
    worker.system_pressure["memory"] = 99.0
    monkeypatch.setattr(
        task_worker.system_config,
        "config",
        SimpleNamespace(task=SimpleNamespace(memory_high_watermark=90.0)),
    )

    assert worker._import_cpu_floor() == 1


def test_task_worker_import_floor_is_capped_at_four(monkeypatch):
    worker = _worker_like()
    worker.system_pressure["memory"] = 50.0
    monkeypatch.setattr(
        task_worker.system_config,
        "config",
        SimpleNamespace(task=SimpleNamespace(memory_high_watermark=90.0)),
    )

    assert worker._import_cpu_floor() == 4


def test_task_worker_reports_overload_for_either_pressure_axis(monkeypatch):
    worker = _worker_like()
    worker.system_pressure["cpu"] = 95.0
    monkeypatch.setattr(
        task_worker.system_config,
        "config",
        SimpleNamespace(task=SimpleNamespace(cpu_high_watermark=90.0)),
    )

    assert worker._is_system_overloaded() is True


# ----------------------------- service/chapter.py -----------------------------


def test_chapter_version_conflict_returns_refresh_hint():
    row = SimpleNamespace(version=3)

    with pytest.raises(HTTPException) as exc_info:
        chapter._check_version(row, 2)

    assert exc_info.value.status_code == 409
    assert "刷新后重试" in exc_info.value.detail


@pytest.mark.parametrize("manage,expected_status", [(False, 404), (True, 200)])
def test_chapter_owned_visibility_is_only_relaxed_for_manage(manage, expected_status):
    query = MagicMock()
    query.filter.return_value = query
    query.filter.return_value.first.return_value = SimpleNamespace(is_hidden=True)
    db = MagicMock()
    db.query.return_value = query
    owner_id = "owner"
    chapter_id = "chapter"

    if expected_status == 200:
        assert (
            chapter._owned(db, owner_id, chapter_id, manage=manage).is_hidden is True
        )
    else:
        with pytest.raises(HTTPException) as exc_info:
            chapter._owned(db, owner_id, chapter_id, manage=manage)
        assert exc_info.value.status_code == expected_status


# ----------------------------- service/storage.py -----------------------------


@pytest.mark.parametrize(
    "folder,expected",
    [
        (None, None),
        ("  ", None),
    ],
)
def test_storage_upload_folder_blank_values_normalize_to_none(folder, expected):
    assert storage._validate_upload_folder(folder) is expected


@pytest.mark.parametrize(
    "folder",
    ["/etc/passwd", "travel/../outside"],
)
def test_storage_upload_folder_rejects_escape_paths(folder):
    with pytest.raises(ValueError, match="Invalid upload folder"):
        storage._validate_upload_folder(folder)


def test_storage_upload_folder_normalizes_windows_separators():
    assert storage._validate_upload_folder("Travel\\2026") == "Travel/2026"


def test_storage_unique_path_appends_numeric_suffix(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"first")

    unique = storage._ensure_unique_path(str(tmp_path), "photo.jpg")

    assert unique.endswith("photo(1).jpg")
    assert not __import__("os").path.exists(unique)


def test_storage_external_roots_expand_absolute_configured_paths(monkeypatch, tmp_path):
    configured = str(tmp_path / "gallery")
    config = SimpleNamespace(
        storage=SimpleNamespace(external_directories=["", configured])
    )
    monkeypatch.setattr(
        storage.config_manager, "get_user_config", lambda *_args, **_kwargs: config
    )

    assert storage.get_external_upload_roots("user", MagicMock()) == [configured]
    assert storage.get_external_upload_roots("user", None) == []

