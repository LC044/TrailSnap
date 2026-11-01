"""Nightly guards for AI embedding model race handling."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_embedding]


def _client():
    from app.routers import embedding as ai_embedding

    app = FastAPI()
    app.include_router(ai_embedding.router)
    return TestClient(app)


def test_embed_image_rejects_model_mismatch(monkeypatch):
    from app.routers import embedding as ai_embedding

    monkeypatch.setattr(
        ai_embedding.ai_model_manager,
        "get_selected_spec",
        lambda _kind: {"runtimeName": "clip-current"},
    )
    response = _client().post("/image", json={"images": ["abc"], "model": "clip-requested"})

    assert response.status_code == 409
    assert "clip-requested" in response.json()["detail"]
    assert "clip-current" in response.json()["detail"]


def test_embed_image_rejects_model_switched_during_encoding(monkeypatch):
    from app.routers import embedding as ai_embedding

    specs = iter(
        [{"runtimeName": "clip-before"}, {"runtimeName": "clip-after"}]
    )

    async def embed_images(_images):
        return [[1.0, 2.0]]

    monkeypatch.setattr(
        ai_embedding.ai_model_manager,
        "get_selected_spec",
        lambda _kind: next(specs),
    )
    monkeypatch.setattr(
        ai_embedding.embedding_service, "embed_images", embed_images
    )
    response = _client().post("/image", json={"images": ["abc"]})

    assert response.status_code == 409
    assert "模型已切换" in response.json()["detail"]
