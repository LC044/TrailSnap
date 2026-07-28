"""Tests for the synchronous AI embedding client wrapper."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.utils import embedding

pytestmark = [pytest.mark.smoke, pytest.mark.module_search]

def _config():
    return SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local"))

def test_get_embedding_returns_first_vector_and_sets_timeouts():
    response = SimpleNamespace(status_code=200, json=lambda: [[0.1, 0.2]], text="")
    with patch.object(embedding.config_manager, "get_user_config", return_value=_config()), patch.object(embedding.requests, "post", return_value=response) as post:
        result = embedding.get_embedding("trail", 7, object())
    assert result == [0.1, 0.2]
    post.assert_called_once_with("http://ai.local/embedding/text", json={"texts": ["trail"]}, timeout=(5, 30))

def test_get_embedding_wraps_non_200_response():
    response = SimpleNamespace(status_code=503, json=lambda: [], text="unavailable")
    with patch.object(embedding.config_manager, "get_user_config", return_value=_config()), patch.object(embedding.requests, "post", return_value=response):
        with pytest.raises(HTTPException) as exc_info:
            embedding.get_embedding("trail", 7, object())
    assert exc_info.value.status_code == 500
    assert "AI Service error: 503" in exc_info.value.detail

def test_get_embedding_wraps_connection_errors():
    with patch.object(embedding.config_manager, "get_user_config", return_value=_config()), patch.object(embedding.requests, "post", side_effect=OSError("offline")):
        with pytest.raises(HTTPException) as exc_info:
            embedding.get_embedding("trail", 7, object())
    assert "offline" in exc_info.value.detail
