"""Unit tests for face_service helpers (app/services/face_service.py).

We mock InsightFace (heavy native dependency) and patch model_downloader /
model_manager so the loader + service path can be exercised without GPU.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke]


def test_load_insightface_model_raises_when_insightface_init_fails(monkeypatch):
    """If FaceAnalysis(...).prepare raises, load_insightface_model must re-raise."""
    from app.services import face_service

    fake_app_module = MagicMock()
    fake_face_analysis = MagicMock(side_effect=RuntimeError("init boom"))
    fake_app_module.FaceAnalysis = fake_face_analysis
    monkeypatch.setitem(__import__("sys").modules, "insightface", MagicMock())
    monkeypatch.setitem(__import__("sys").modules, "insightface.app", fake_app_module)
    monkeypatch.setattr(
        face_service.ai_config_manager,
        "get_model_selection",
        MagicMock(return_value="buffalo_l"),
    )

    with pytest.raises(RuntimeError, match="init boom"):
        face_service.load_insightface_model()


def test_release_model_swallows_missing_torch(monkeypatch):
    """release_model must not blow up when torch isn't installed."""
    from app.services import face_service

    # Ensure torch import raises ImportError to mirror a CPU-only install.
    real_import = __import__("builtins").__import__

    def guarded_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("no torch in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)

    # Should not raise even though torch isn't importable.
    face_service.release_model(MagicMock())


def test_face_recognition_service_process_image_raises_when_not_ready(monkeypatch):
    """process_image must raise before touching cv2 if the model isn't ready."""
    from app.services import face_service

    fake_downloader = MagicMock(is_ready=MagicMock(return_value=False))
    monkeypatch.setattr(face_service, "model_downloader", fake_downloader)

    service = face_service.FaceRecognitionService()
    with pytest.raises(Exception, match="Face model is not ready"):
        service.process_image(b"\x89PNG\r\n\x1a\n")


def test_face_recognition_service_process_image_returns_empty_for_no_faces(monkeypatch):
    """If InsightFace returns zero faces, process_image should return []."""
    from app.services import face_service

    fake_downloader = MagicMock(is_ready=MagicMock(return_value=True))
    fake_app = MagicMock()
    fake_app.get = MagicMock(return_value=[])
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_app))
    monkeypatch.setattr(face_service, "model_downloader", fake_downloader)
    monkeypatch.setattr(face_service, "model_manager", fake_manager)

    service = face_service.FaceRecognitionService()
    # 1x1 PNG bytes (same fixture as embedding_service tests).
    png_bytes = _base64_decode_1x1_png()
    result = service.process_image(png_bytes)
    assert result == []


def test_face_recognition_service_process_image_returns_empty_for_invalid_bytes(monkeypatch):
    """Non-image bytes should raise ValueError, not crash."""
    from app.services import face_service

    fake_downloader = MagicMock(is_ready=MagicMock(return_value=True))
    fake_app = MagicMock()
    fake_app.get = MagicMock(return_value=[])
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_app))
    monkeypatch.setattr(face_service, "model_downloader", fake_downloader)
    monkeypatch.setattr(face_service, "model_manager", fake_manager)

    service = face_service.FaceRecognitionService()
    with pytest.raises(ValueError, match="Invalid image data"):
        service.process_image(b"not an image at all")


def _base64_decode_1x1_png() -> bytes:
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    )