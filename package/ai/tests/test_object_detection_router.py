"""Unit tests for the AI service object_detection router.

The router is a thin validation-only endpoint (`POST /predict`) that
returns 400 on empty input and a stub message otherwise.  Tests use a
stripped FastAPI app + TestClient so no models are touched.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import object_detection as ai_obj_det


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_object_detection]


@pytest.fixture
def ai_object_detection_client():
    app = FastAPI(title="TrailSnap AI - object-detection tests")
    app.include_router(ai_obj_det.router)
    return TestClient(app)


def test_object_detection_predict_rejects_empty_images_list(ai_object_detection_client):
    res = ai_object_detection_client.post("/predict", json={"images": []})
    assert res.status_code == 400
    assert res.json() == {"detail": "No images provided"}


def test_object_detection_predict_missing_images_field(ai_object_detection_client):
    """Pydantic should reject payloads that omit the images field."""
    res = ai_object_detection_client.post("/predict", json={})
    assert res.status_code == 422


def test_object_detection_predict_returns_stub_message(ai_object_detection_client):
    """Non-empty input returns the explicit "not implemented" stub."""
    res = ai_object_detection_client.post("/predict", json={"images": ["ZmFrZQ=="]})
    assert res.status_code == 200
    body = res.json()
    assert "message" in body
    assert "not implemented" in body["message"].lower()
