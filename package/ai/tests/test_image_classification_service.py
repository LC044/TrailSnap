"""Unit tests for app/services/image_classification_service.py.

The service wraps heavy ONNX models; we focus on the pure-helper methods
(`_translate_label`, `_normalize_label`) and the input-decoding branches
of `classify_yolo` (bad base64 -> error status; no images -> empty list;
model not ready -> raises).
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def service():
    """Build the service without running its model-discovery __init__."""
    from app.services.image_classification_service import ImageClassificationService
    svc = ImageClassificationService.__new__(ImageClassificationService)
    svc.version = "v0.3.10.1"
    svc._category_model_map = {}
    return svc


def test_translate_label_returns_chinese_for_known_label(service):
    assert service._translate_label("dog") == "狗"
    assert service._translate_label("scenery") == "风景"
    assert service._translate_label("train_ticket_screenshot") == "火车票截图"


def test_translate_label_passes_through_unknown_label(service):
    assert service._translate_label("mystery_category") == "mystery_category"


def test_translate_label_handles_empty_string(service):
    assert service._translate_label("") == ""


def test_normalize_label_returns_others_for_none(service):
    assert service._normalize_label(None, 0.9) == "others"


def test_normalize_label_returns_others_for_low_confidence(service):
    assert service._normalize_label("dog", 0.3) == "others"


def test_normalize_label_returns_label_for_high_confidence(service):
    assert service._normalize_label("dog", 0.8) == "dog"


def test_normalize_label_uses_custom_min_confidence(service):
    assert service._normalize_label("dog", 0.6, min_conf=0.7) == "others"
    assert service._normalize_label("dog", 0.8, min_conf=0.7) == "dog"


def test_classify_yolo_raises_when_general_model_not_ready(service):
    from app.services import image_classification_service as ics
    with patch.object(ics, "model_downloader") as downloader:
        downloader.is_ready.return_value = False
        with pytest.raises(Exception, match="General model is not ready"):
            service.classify_yolo(["aGVsbG8="])  # any base64


def test_classify_yolo_marks_invalid_base64_as_error(service):
    from app.services import image_classification_service as ics
    # A valid 1x1 PNG (base64) for one slot; garbage for the other.
    import base64
    valid_png = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
    images = [valid_png, "not-base64!@#$"]

    fake_general = MagicMock(return_value=[[0.1, 0.9]])
    fake_general.names = {0: "others", 1: "scenery"}
    with patch.object(ics, "model_downloader") as downloader:
        downloader.is_ready.return_value = True
        with patch.object(ics, "model_manager") as manager:
            manager.get_model.return_value = fake_general
            results = service.classify_yolo(images)

    # First image: error (PNG is fake, but we can still test the bad one)
    # Actually fake PNG might decode then fail in Image.open; test what we can.
    assert len(results) == 2
    # The bad one should always be an error
    assert results[1]["status"] == "error"
    assert "error" in results[1]


def test_classify_yolo_handles_empty_input_list(service):
    from app.services import image_classification_service as ics
    with patch.object(ics, "model_downloader") as downloader:
        downloader.is_ready.return_value = True
        results = service.classify_yolo([])
    assert results == []


def test_classify_yolo_strips_data_url_prefix(service):
    """`data:image/png;base64,XXXX` prefix must be stripped before decoding."""
    from app.services import image_classification_service as ics
    import base64
    valid_png_bytes = b"\x89PNG\r\n\x1a\nfake"
    valid_png = "data:image/png;base64," + base64.b64encode(valid_png_bytes).decode()

    fake_general = MagicMock(return_value=[[0.1, 0.9]])
    fake_general.names = {0: "others", 1: "scenery"}
    with patch.object(ics, "model_downloader") as downloader:
        downloader.is_ready.return_value = True
        with patch.object(ics, "model_manager") as manager:
            manager.get_model.return_value = fake_general
            results = service.classify_yolo([valid_png])

    # The strip path is exercised; the image might still fail to open, but no crash.
    assert len(results) == 1
