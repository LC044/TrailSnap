import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_embedding]


def test_explicit_text_model_is_verified_and_returned(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import embedding

    monkeypatch.setattr(
        embedding.ai_model_manager,
        "get_selected_spec",
        lambda *a: {"runtimeName": "test"},
    )
    encode = AsyncMock(return_value=[[1.0, 0.0]])
    monkeypatch.setattr(embedding.embedding_service, "embed_texts", encode)
    app = FastAPI()
    app.include_router(embedding.router)
    with TestClient(app) as client:
        wrong = client.post("/text", json={"texts": ["露营"], "model": "old"})
        assert wrong.status_code == 409 and encode.await_count == 0
        response = client.post(
            "/text", json={"texts": ["露营"], "model": "test", "cache": True}
        )
    assert response.status_code == 200
    assert response.headers["X-Embedding-Model"] == "test"
    encode.assert_awaited_once_with(["露营"], use_cache=True, reject_truncation=True)


def test_rule_descriptions_cannot_be_silently_truncated(monkeypatch):
    from app.services import embedding_service as module

    wrapper = SimpleNamespace(
        tokenizer=lambda **kwargs: {"input_ids": [[1, 2, 3, 4]]},
        max_length=3,
        encode_text_cached=MagicMock(),
    )
    monkeypatch.setattr(module.ai_model_manager, "is_ready", lambda *a: True)
    monkeypatch.setattr(module.model_manager, "get_model", lambda *a: wrapper)
    service = module.EmbeddingService.__new__(module.EmbeddingService)
    with pytest.raises(ValueError, match="token"):
        asyncio.run(
            service.embed_texts(["too long"], use_cache=True, reject_truncation=True)
        )
    wrapper.encode_text_cached.assert_not_called()
