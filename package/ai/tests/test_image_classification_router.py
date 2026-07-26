"""Unit tests for the AI image-classification router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import image_classification as ai_classification

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def classification_client(monkeypatch):
    monkeypatch.setattr(
        ai_classification.image_classification_service,
        "classify_yolo",
        lambda images: [{"status": "success", "predictions": [{"label": "landscape", "confidence": 0.95}], "error": None} for _ in images],
    )
    app = FastAPI()
    app.include_router(ai_classification.router)
    return TestClient(app)

def test_classification_rejects_empty_batch(classification_client):
    response = classification_client.post("/", json={"images": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "No images provided"

def test_classification_returns_result_per_image(classification_client):
    response = classification_client.post("/", json={"images": ["a", "b"]})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["predictions"][0] == {"label": "landscape", "confidence": 0.95}

def test_classification_wraps_service_error(classification_client, monkeypatch):
    def _boom(images):
        raise RuntimeError("classifier unavailable")
    monkeypatch.setattr(ai_classification.image_classification_service, "classify_yolo", _boom)
    response = classification_client.post("/", json={"images": ["a"]})
    assert response.status_code == 500
    assert response.json()["detail"] == "classifier unavailable"
