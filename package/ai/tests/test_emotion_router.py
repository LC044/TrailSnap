"""Unit tests for the AI emotion-color router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import emotion as ai_emotion

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def emotion_client(monkeypatch):
    async def _analyze(images):
        return [
            {
                "status": "success",
                "dominant_colors": [{"hex": "#112233", "ratio": 0.75}],
                "brightness": 0.4,
                "saturation": 0.6,
                "emotion_hint": "cool",
                "top_categories": ["night"],
                "error": None,
            }
            for _ in images
        ]
    monkeypatch.setattr(ai_emotion.emotion_service, "analyze", _analyze)
    app = FastAPI()
    app.include_router(ai_emotion.router)
    return TestClient(app)

def test_emotion_rejects_empty_batch(emotion_client):
    response = emotion_client.post("/", json={"images": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "No images provided"

def test_emotion_returns_color_analysis_per_image(emotion_client):
    response = emotion_client.post("/", json={"images": ["a", "b"]})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["dominant_colors"] == [{"hex": "#112233", "ratio": 0.75}]
    assert results[0]["emotion_hint"] == "cool"

def test_emotion_wraps_service_error(emotion_client, monkeypatch):
    async def _boom(images):
        raise RuntimeError("color model unavailable")
    monkeypatch.setattr(ai_emotion.emotion_service, "analyze", _boom)
    response = emotion_client.post("/", json={"images": ["a"]})
    assert response.status_code == 500
    assert response.json()["detail"] == "color model unavailable"
