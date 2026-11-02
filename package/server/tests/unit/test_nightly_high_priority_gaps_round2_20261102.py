"""Nightly watch 2026-11-02 round-two tests for high-priority coverage gaps."""
import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import media
from app.crud import album as crud_album
from app.service import task_worker
from app.service import face_cluster as face_cluster_module
from app.service.tasks import visual_description as visual_description_module

pytestmark = [pytest.mark.smoke]


def test_face_cluster_int_env_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("TS_NIGHTLY_FACE_FETCH_BATCH", "not-a-number")

    assert face_cluster_module._int_env("TS_NIGHTLY_FACE_FETCH_BATCH", 321, 100) == 321


def test_face_cluster_int_env_enforces_minimum(monkeypatch):
    monkeypatch.setenv("TS_NIGHTLY_FACE_FETCH_BATCH", "3")

    assert face_cluster_module._int_env("TS_NIGHTLY_FACE_FETCH_BATCH", 1000, 100) == 100


def test_smart_album_sqlite_vector_query_ignores_zero_norm_candidate():
    db = MagicMock()
    db.bind.dialect.name = "sqlite"
    query = MagicMock()
    query.filter.return_value = query
    query.join.return_value = query
    query.with_entities.return_value = query
    matching_id, zero_norm_id = uuid4(), uuid4()
    query.all.return_value = [
        (matching_id, [1.0, 0.0]),
        (zero_norm_id, [0.0, 0.0]),
    ]
    db.query.return_value = query
    album = SimpleNamespace(
        owner_id=uuid4(),
        type="smart",
        query_embedding=[1.0, 0.0],
        threshold=0.25,
    )

    result = crud_album._build_album_query(db, album)

    assert result is query
    query.with_entities.assert_called_once()
    final_expression = query.filter.call_args_list[-1].args[0]
    assert final_expression.right.value == [matching_id]


def test_task_worker_request_drain_is_idempotent():
    worker = object.__new__(task_worker.TaskWorker)
    worker.accepting_tasks = True
    worker.wake = MagicMock()
    worker._publish = MagicMock()

    worker.request_drain()
    assert worker.accepting_tasks is False
    worker.wake.assert_called_once()
    worker._publish.assert_called_once_with("task.worker", {"status": "draining"})

    worker.request_drain()
    worker.wake.assert_called_once()
    worker._publish.assert_called_once()


def test_live_content_state_uses_thumbnail_companion_video(tmp_path):
    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4(), file_path=str(tmp_path / "image.jpg"))
    image_md5 = "image-md5"
    video_md5 = hashlib.md5(b"video").hexdigest()
    companion = tmp_path / "thumbnail.mp4"
    companion.write_bytes(b"video")

    with (
        patch.object(
            media,
            "_existing_content_photo",
            side_effect=lambda _db, _user, digest: photo if digest == image_md5 else None,
        ),
        patch.object(media.storage, "get_live_photo_vide", return_value=None),
        patch.object(media, "_get_thumbnail_path", return_value=str(tmp_path / "thumbnail.jpg")),
    ):
        image, attached, complete = media._live_content_state(
            MagicMock(), photo.owner_id, image_md5, video_md5
        )

    assert image is photo
    assert attached == str(companion)
    assert complete is True


def test_visual_response_content_joins_supported_parts():
    content = ["left", {"text": "right"}, {"image": "ignored"}, 123]

    assert visual_description_module._response_content_to_text(content) == "leftright"


def test_visual_response_content_falls_back_to_plain_text():
    assert visual_description_module._response_content_to_text(None) == ""
    assert visual_description_module._response_content_to_text(123) == "123"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"description": 1, "reason": "r", "narrative": "n", "tags": [], "memory_score": 1, "beauty_score": 1}, "必须是字符串"),
        ({"description": "d", "reason": "r", "narrative": "n", "tags": [1], "memory_score": 1, "beauty_score": 1}, "字符串数组"),
        ({"description": "d", "reason": "r", "narrative": "n", "tags": [], "memory_score": True, "beauty_score": 1}, "必须是数字"),
    ],
)
def test_visual_result_schema_rejects_wrong_field_types(payload, message):
    with pytest.raises(visual_description_module.VisualDescriptionFormatError, match=message):
        visual_description_module._validate_visual_result(payload)