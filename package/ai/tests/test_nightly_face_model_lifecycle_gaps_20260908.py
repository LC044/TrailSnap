"""Nightly gap tests for InsightFace model lifecycle (2026-09-08)."""
import gc
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


def _install_fake_insightface(monkeypatch):
    insightface = types.ModuleType("insightface")
    app_module = types.ModuleType("insightface.app")
    face_analysis = MagicMock(name="FaceAnalysis")
    app_module.FaceAnalysis = face_analysis
    insightface.app = app_module
    monkeypatch.setitem(sys.modules, "insightface", insightface)
    monkeypatch.setitem(sys.modules, "insightface.app", app_module)
    return face_analysis


def test_load_insightface_model_configures_selected_model(monkeypatch, tmp_path):
    from app.services import face_service

    face_analysis = _install_fake_insightface(monkeypatch)
    monkeypatch.setattr(face_service.ai_model_manager, "get_model_selection", lambda _: "buffalo_l")
    monkeypatch.setattr(face_service.settings, "MODEL_PATH", str(tmp_path / "models"))
    monkeypatch.setattr(
        face_service,
        "get_onnx_providers",
        lambda: (["CPUExecutionProvider"], [{" intra_op_num_threads ": 2}]),
    )

    app = face_service.load_insightface_model()

    assert app is face_analysis.return_value
    kwargs = face_analysis.call_args.kwargs
    assert kwargs["name"] == "buffalo_l"
    assert kwargs["root"] == str(tmp_path.resolve())
    assert kwargs["providers"] == ["CPUExecutionProvider"]
    assert kwargs["provider_options"] == [{" intra_op_num_threads ": 2}]
    app.prepare.assert_called_once_with(ctx_id=0, det_size=(640, 640))


def test_release_model_clears_internal_sessions_and_caches(monkeypatch):
    from app.services import face_service

    insightface = types.ModuleType("insightface")
    utils_module = types.ModuleType("insightface.utils")
    face_align = types.ModuleType("insightface.utils.face_align")
    face_align.clear_cache = MagicMock()
    utils_module.face_align = face_align
    insightface.utils = utils_module
    monkeypatch.setitem(sys.modules, "insightface", insightface)
    monkeypatch.setitem(sys.modules, "insightface.utils", utils_module)
    monkeypatch.setitem(sys.modules, "insightface.utils.face_align", face_align)

    inner = SimpleNamespace(
        session=object(),
        model=object(),
        input_names=["input"],
        output_names=["output"],
    )
    app = SimpleNamespace(
        models={"detection": inner},
        det_model=object(),
        rec_model=object(),
        cls_model=object(),
    )
    with patch.object(face_service.gc, "collect") as collect:
        face_service.release_model(app)

    face_align.clear_cache.assert_called_once()
    collect.assert_called()
    for attribute in ("models", "det_model", "rec_model", "cls_model"):
        assert not hasattr(app, attribute)
    assert not hasattr(inner, "session")
    assert not hasattr(inner, "model")
    assert not hasattr(inner, "input_names")
    assert not hasattr(inner, "output_names")


def test_process_image_rejects_invalid_image_bytes(monkeypatch):
    from app.services import face_service

    monkeypatch.setattr(face_service.ai_model_manager, "is_ready", lambda _: True)
    monkeypatch.setattr(face_service.model_manager, "get_model", lambda _: MagicMock())
    monkeypatch.setattr(face_service.cv2, "imdecode", lambda data, flags: None)

    with pytest.raises(ValueError, match="Invalid image data"):
        face_service.FaceRecognitionService().process_image(b"not-an-image")

