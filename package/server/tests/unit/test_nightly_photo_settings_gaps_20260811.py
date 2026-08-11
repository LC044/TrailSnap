"""Nightly API gap tests."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
import requests
from app.api import photo as photo_api
from app.api import settings as settings_api
pytestmark = pytest.mark.smoke

def test_recycle_bin_delegates_owner_and_pagination():
    db = MagicMock(); user = SimpleNamespace(id="owner-1"); expected = [{"id": "photo-1"}]
    with patch.object(photo_api.app.crud.photo, "get_recycle_bin_photos", return_value=expected) as get_bin:
        result = photo_api.get_recycle_bin(skip=4, limit=8, db=db, current_user=user)
    get_bin.assert_called_once_with(db, user_id=user.id, skip=4, limit=8); assert result.data is expected

def test_random_photos_forwards_count_and_owner():
    db = MagicMock(); user = SimpleNamespace(id="owner-2"); expected = []
    with patch.object(photo_api.app.crud.photo, "get_random_photos", return_value=expected) as get_random:
        result = photo_api.get_random_photos(limit=3, db=db, current_user=user)
    get_random.assert_called_once_with(db, user_id=user.id, limit=3); assert result.data is expected

def test_on_this_day_forwards_date_and_owner():
    db = MagicMock(); user = SimpleNamespace(id="owner-3"); expected = {"photos": []}
    with patch.object(photo_api.app.crud.photo, "get_on_this_day_photos", return_value=expected) as get_photos:
        result = photo_api.get_on_this_day_photos(month=8, day=11, year=2025, db=db, current_user=user)
    get_photos.assert_called_once_with(db, user_id=user.id, month=8, day=11, year=2025, limit=10); assert result == expected

def test_available_models_fetches_remote_models():
    db = MagicMock(); user = SimpleNamespace(id="owner-4")
    conn = SimpleNamespace(id="remote", enable=True, model_names=[], api_base="https://ai.example/", api_key="secret", provider="OpenAI")
    config = SimpleNamespace(ai=SimpleNamespace(connections=[conn], analysis_connection_id="remote", analysis_model_name="vision", chat_connection_id="", chat_model_name=""))
    response = SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "model-a"}, {"name": "ignored"}]})
    with patch.object(settings_api.config_manager, "get_user_config", return_value=config), patch.object(settings_api.requests, "get", return_value=response) as get:
        result = settings_api.get_available_models(db=db, current_user=user)
    get.assert_called_once_with("https://ai.example/models", headers={"Authorization": "Bearer secret"}, timeout=5)
    assert result["connections"][0]["models"] == ["model-a"]

def test_verify_ai_service_rejects_invalid_url():
    result = settings_api.verify_ai_service(settings_api.VerifyAIServiceRequest(api_url="localhost:8001"), current_user=SimpleNamespace(id="owner-5"))
    assert result.code == 400; assert "http" in result.msg

def test_verify_ai_service_success_returns_service_and_elapsed():
    response = SimpleNamespace(status_code=200, json=lambda: {"status": "ok", "service": "TrailSnap AI"})
    with patch.object(settings_api.requests, "get", return_value=response), patch.object(settings_api.time, "monotonic", side_effect=[1.0, 1.025]):
        result = settings_api.verify_ai_service(settings_api.VerifyAIServiceRequest(api_url=" http://localhost:8001/ "), current_user=SimpleNamespace(id="owner-6"))
    assert result.code == 0; assert result.data == {"success": True, "service": "TrailSnap AI", "elapsed_ms": 25}

def test_verify_ai_service_timeout_returns_failure():
    with patch.object(settings_api.requests, "get", side_effect=requests.Timeout()):
        result = settings_api.verify_ai_service(settings_api.VerifyAIServiceRequest(api_url="http://localhost:8001"), current_user=SimpleNamespace(id="owner-7"))
    assert result.code == 0; assert result.data["success"] is False; assert "超时" in result.data["message"]

