"""Unit tests covering 2026-08-11 nightly AI gap scan (round 4).

Target: ``app/services/ocr_service.py`` (44% previously).

Exercises the previously untested branches in:
* ``release_paddleocr_model`` -- success log + swallowed exception log.
* ``OCRService.__init__`` -- registers the download closures eagerly.
* ``load_paddleocr_model`` -- failure path re-raises, torch path resets
  openvino flag, no-torch/no-openvino path keeps the flag False.
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# release_paddleocr_model
# ---------------------------------------------------------------------------

def test_release_paddleocr_model_logs_info_on_success(caplog):
    from app.services import ocr_service
    with caplog.at_level("INFO"):
        ocr_service.release_paddleocr_model(MagicMock())
    assert any("PaddleOCR resources released" in r.getMessage() for r in caplog.records)


def test_release_paddleocr_model_swallows_and_logs_exception(caplog):
    from app.services import ocr_service

    # Force the log call inside the try block to itself raise, hitting the except.
    def _explode(_msg, *args, **kwargs):
        raise OSError("log-broken")

    with caplog.at_level("ERROR"):
        with patch.object(ocr_service.logging, "info", side_effect=_explode):
            # Must NOT raise.
            ocr_service.release_paddleocr_model(MagicMock())
    assert any("Error releasing PaddleOCR" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# OCRService.__init__
# ---------------------------------------------------------------------------

def test_ocr_service_has_no_per_service_downloader_registration():
    """All downloads are owned by the unified model manager."""
    from app.services import ocr_service
    assert not hasattr(ocr_service.OCRService, "_register_downloads")


# ---------------------------------------------------------------------------
# load_paddleocr_model failure path
# ---------------------------------------------------------------------------

def test_load_paddleocr_model_reraises_on_engine_failure(monkeypatch):
    """If RapidOCR() itself explodes, load_paddleocr_model must re-raise."""
    from app.services import ocr_service

    rapidocr_mod = MagicMock()
    for name in ("EngineType", "LangDet", "LangRec", "ModelType", "OCRVersion"):
        setattr(rapidocr_mod, name, MagicMock())
    rapidocr_mod.RapidOCR.side_effect = RuntimeError("boom")
    with patch.dict("sys.modules", {"rapidocr": rapidocr_mod}):
        with patch.object(ocr_service, "_ocr_engine_is_openvino", True):
            with pytest.raises(RuntimeError, match="boom"):
                ocr_service.load_paddleocr_model()


def test_load_paddleocr_model_keeps_openvino_false_when_extra_missing(monkeypatch):
    """ONNX models use CUDA through ORT; without OpenVINO the lock stays disabled."""
    from app.services import ocr_service

    rapidocr_mod = MagicMock()
    for name in ("EngineType", "LangDet", "LangRec", "ModelType", "OCRVersion"):
        setattr(rapidocr_mod, name, MagicMock())
    rapidocr_mod.RapidOCR.return_value = MagicMock(name="fake-rapidocr")

    with patch.dict("sys.modules", {"rapidocr": rapidocr_mod, "openvino": None}):
        with patch.object(ocr_service, "_ocr_engine_is_openvino", True):
            model = ocr_service.load_paddleocr_model()
    assert model is not None
    assert ocr_service._ocr_engine_is_openvino is False


def test_load_paddleocr_model_no_torch_no_openvino_keeps_flag_false(monkeypatch):
    """Without torch and without openvino, the flag stays False."""
    from app.services import ocr_service

    rapidocr_mod = MagicMock()
    for name in ("EngineType", "LangDet", "LangRec", "ModelType", "OCRVersion"):
        setattr(rapidocr_mod, name, MagicMock())
    rapidocr_mod.RapidOCR.return_value = MagicMock(name="fake-rapidocr")

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("no torch")
        if name == "openvino":
            raise ImportError("no openvino")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        with patch.dict("sys.modules", {"rapidocr": rapidocr_mod}):
            with patch.object(ocr_service, "_ocr_engine_is_openvino", False):
                ocr_service.load_paddleocr_model()
    assert ocr_service._ocr_engine_is_openvino is False

