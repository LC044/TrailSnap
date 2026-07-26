"""Unit tests for the AI service config router (app/routers/ai_config.py).

Covers ``GET /config`` and the model-selection endpoint. ``ai_config_manager``
and ``model_downloader`` / ``model_manager`` are patched so no real model is
loaded or downloaded.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import ai_config as ai_config_router


pytestmark = [pytest.mark.smoke]


# ----------------------- GET /ai/config -----------------------


def test_get_config_returns_manager_dict():
    """GET /config forwards to ai_config_manager.get_config and returns the dict."""
    expected = {"ocr": "PaddleOCR", "face": "InsightFace", "classification": "CLIP"}

    with patch.object(ai_config_router.ai_config_manager, "get_config", return_value=expected) as get_call:
        # ``get_config`` is declared async in the router.
        import asyncio
        result = asyncio.run(ai_config_router.get_config())

    get_call.assert_called_once()
    assert result == expected


# ----------------------- POST /ai/config/model -----------------------


def test_set_model_returns_success_when_unchanged():
    """If the selection didn't actually change, response is still success but no download is triggered."""
    request = SimpleNamespace(task="ocr", model="PaddleOCR")
    expected = {"ocr": "PaddleOCR"}

    with patch.object(ai_config_router.ai_config_manager, "set_model_selection", return_value=False), \
         patch.object(ai_config_router.ai_config_manager, "get_config", return_value=expected), \
         patch.object(ai_config_router, "model_downloader") as dl:
        import asyncio
        result = asyncio.run(ai_config_router.set_model(request=request, background_tasks=MagicMock()))

    dl.trigger_download.assert_not_called()
    dl.reset_status.assert_not_called()
    assert result["status"] == "success"
    assert result["config"] == expected


def test_set_model_ocr_changed_triggers_download():
    """Switching the OCR model releases the old model and triggers a new download."""
    request = SimpleNamespace(task="ocr", model="RapidOCR")
    expected = {"ocr": "RapidOCR"}

    with patch.object(ai_config_router.ai_config_manager, "set_model_selection", return_value=True), \
         patch.object(ai_config_router.ai_config_manager, "get_config", return_value=expected), \
         patch.object(ai_config_router, "model_manager") as mm, \
         patch.object(ai_config_router, "model_downloader") as dl:
        mm.models = {"ocr": MagicMock()}
        import asyncio
        result = asyncio.run(ai_config_router.set_model(request=request, background_tasks=MagicMock()))

    mm.models["ocr"].release.assert_called_once()
    dl.reset_status.assert_called_once_with("ocr")
    dl.trigger_download.assert_called_once_with("ocr")
    assert result["status"] == "success"
    assert result["config"]["ocr"] == "RapidOCR"


def test_set_model_classification_changed_releases_both_clip_keys():
    """Classification task releases both clip_text and clip_image model entries."""
    request = SimpleNamespace(task="classification", model="CN-CLIP")
    expected = {"classification": "CN-CLIP"}

    clip_text = MagicMock()
    clip_image = MagicMock()

    with patch.object(ai_config_router.ai_config_manager, "set_model_selection", return_value=True), \
         patch.object(ai_config_router.ai_config_manager, "get_config", return_value=expected), \
         patch.object(ai_config_router, "model_manager") as mm, \
         patch.object(ai_config_router, "model_downloader") as dl:
        mm.models = {"clip_text": clip_text, "clip_image": clip_image}
        import asyncio
        result = asyncio.run(ai_config_router.set_model(request=request, background_tasks=MagicMock()))

    clip_text.release.assert_called_once()
    clip_image.release.assert_called_once()
    assert dl.trigger_download.call_count == 2
    assert result["status"] == "success"


def test_set_model_400_on_value_error():
    """``ValueError`` from the manager is mapped to HTTP 400."""
    request = SimpleNamespace(task="ocr", model="Bogus")

    with patch.object(
        ai_config_router.ai_config_manager,
        "set_model_selection",
        side_effect=ValueError("unknown task"),
    ):
        import asyncio
        with pytest.raises(Exception) as exc_info:
            asyncio.run(ai_config_router.set_model(request=request, background_tasks=MagicMock()))

    assert getattr(exc_info.value, "status_code", None) == 400
