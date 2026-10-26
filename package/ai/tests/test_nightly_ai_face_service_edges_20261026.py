"""Nightly coverage for the remaining branches of
``app/services/face_service.py`` (2026-10-26).

The 2026-10-26 AI coverage scan listed ``services/face_service.py`` at 88.4%
with 15 missed lines.  The missed lines sat in three places:

* ``_valid_embedding`` never swallowed the ``TypeError``/``ValueError`` of a
  non numeric embedding
* ``_ensure_embedding`` never reported a missing recognition model
* ``process_image`` never walked a detected face, so the normalised bbox and
  the JSON serialisable payload were never built

InsightFace is a heavy native dependency, so the detection result is faked
exactly like the existing ``tests/test_face_service.py`` does.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke]


def _one_pixel_png() -> bytes:
    import base64 as _base64

    return _base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


# ---------------------------------------------------------------------------
# _valid_embedding
# ---------------------------------------------------------------------------


def test_valid_embedding_rejects_a_non_numeric_value():
    from app.services.face_service import FaceRecognitionService

    assert FaceRecognitionService._valid_embedding(object()) is False


def test_valid_embedding_rejects_a_wrong_shaped_vector():
    from app.services.face_service import FaceRecognitionService

    assert FaceRecognitionService._valid_embedding(np.ones(256)) is False


def test_valid_embedding_accepts_a_finite_vector():
    from app.services.face_service import FaceRecognitionService

    # The helper returns the numpy result of ``np.any(...)``, so compare the
    # truth value instead of the identity with ``True``.
    assert bool(FaceRecognitionService._valid_embedding(np.ones(512))) is True


# ---------------------------------------------------------------------------
# _ensure_embedding
# ---------------------------------------------------------------------------


def test_ensure_embedding_requires_the_recognition_model():
    from app.services.face_service import FaceRecognitionService

    app = SimpleNamespace(models={})

    # The recognition model is only looked up when the accelerated provider
    # returned unusable features, so the embedding has to be invalid here.
    with pytest.raises(ValueError, match="Face recognition model is missing"):
        FaceRecognitionService()._ensure_embedding(app, object(), SimpleNamespace(embedding=np.zeros(512)))


# ---------------------------------------------------------------------------
# process_image
# ---------------------------------------------------------------------------


def test_process_image_builds_the_normalised_face_payload(monkeypatch):
    from app.services import face_service

    face = SimpleNamespace(
        embedding=np.ones(512),
        bbox=np.array([10.0, 20.0, 110.0, 220.0]),
        kps=np.zeros((5, 2)),
        det_score=0.87,
    )
    fake_app = MagicMock()
    fake_app.get = MagicMock(return_value=[face])
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_app))
    monkeypatch.setattr(face_service, "ai_model_manager", MagicMock(is_ready=MagicMock(return_value=True)))
    monkeypatch.setattr(face_service, "model_manager", fake_manager)

    result = face_service.FaceRecognitionService().process_image(_one_pixel_png())

    assert len(result) == 1
    payload = result[0]
    assert payload["det_score"] == pytest.approx(0.87)
    assert len(payload["embedding"]) == 512
    assert len(payload["bbox"]) == 4
    assert len(payload["kps"]) == 5


def test_process_image_scales_the_bbox_to_the_image_size(monkeypatch):
    from app.services import face_service

    face = SimpleNamespace(
        embedding=np.ones(512),
        bbox=np.array([0.0, 0.0, 1.0, 1.0]),
        kps=np.zeros((5, 2)),
        det_score=0.5,
    )
    fake_app = MagicMock()
    fake_app.get = MagicMock(return_value=[face])
    monkeypatch.setattr(face_service, "ai_model_manager", MagicMock(is_ready=MagicMock(return_value=True)))
    monkeypatch.setattr(face_service, "model_manager", MagicMock(get_model=MagicMock(return_value=fake_app)))

    result = face_service.FaceRecognitionService().process_image(_one_pixel_png())

    bbox = result[0]["bbox"]
    # The 1x1 fixture keeps every normalised coordinate inside [0, 1].
    assert all(0.0 <= value <= 1.0 for value in bbox)
