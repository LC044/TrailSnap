"""Desktop Sidecar must expose the same capability routes as the full AI service."""

import pytest

import desktop_app


pytestmark = [pytest.mark.smoke]


def test_desktop_sidecar_exposes_complete_ai_routes():
    paths = set(desktop_app.app.openapi()["paths"])
    assert {
        "/face/face-recognition",
        "/ocr/predict",
        "/object-detection/predict",
        "/tickets/predict",
        "/classification/",
        "/embedding/text",
        "/embedding/image",
        "/v1/{path}",
        "/ai/models",
        "/emotion/",
    }.issubset(paths)


def test_desktop_health_reports_complete_capabilities():
    payload = desktop_app.health_check()
    assert {"face", "embedding", "llm", "emotion"}.issubset(payload["capabilities"])
