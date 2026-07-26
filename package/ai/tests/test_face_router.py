"""Unit tests for the AI face router without loading InsightFace."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import face as ai_face

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def face_client(monkeypatch):
    face = {"bbox": [1.0, 2.0, 3.0, 4.0], "kps": [[1.0, 2.0]], "det_score": 0.9, "embedding": [0.1, 0.2]}
    monkeypatch.setattr(ai_face.face_service, "process_image", lambda contents: [face])
    app = FastAPI()
    app.include_router(ai_face.router)
    return TestClient(app)

def test_face_rejects_empty_batch(face_client):
    response = face_client.post("/face-recognition", json={"images": []})
    assert response.status_code == 400

def test_face_returns_count_and_features(face_client):
    image = base64.b64encode(b"image").decode()
    response = face_client.post("/face-recognition", json={"images": [image]})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["face_count"] == 1
    assert result["faces"][0]["det_score"] == pytest.approx(0.9)
    assert result["error"] is None

def test_face_isolates_invalid_image(face_client):
    valid = base64.b64encode(b"valid").decode()
    response = face_client.post("/face-recognition", json={"images": ["a", valid]})
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["face_count"] == 0
    assert results[0]["error"]
    assert results[1]["face_count"] == 1

