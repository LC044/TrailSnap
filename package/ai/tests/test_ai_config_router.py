from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import ai_config as router_module


pytestmark = [pytest.mark.smoke]


def test_get_config_returns_unified_task_selections():
    payload = {"tasks": {"face": {"selected": "face-buffalo-l"}}, "models": []}
    with patch.object(router_module.ai_model_manager, "list_models", return_value=payload):
        import asyncio
        result = asyncio.run(router_module.get_config())
    assert result == payload["tasks"]


def test_get_models_returns_unified_catalog():
    payload = {"tasks": {}, "models": [{"id": "face-buffalo-l"}]}
    with patch.object(router_module.ai_model_manager, "list_models", return_value=payload):
        import asyncio
        result = asyncio.run(router_module.get_managed_models())
    assert result == payload


def test_download_model_delegates_to_unified_manager():
    with patch.object(router_module.ai_model_manager, "trigger_download") as trigger:
        import asyncio
        result = asyncio.run(router_module.download_managed_model("face-buffalo-l"))
    trigger.assert_called_once_with("face-buffalo-l")
    assert result["status"] == "downloading"


def test_set_model_returns_catalog_after_switch():
    request = SimpleNamespace(task="face", model="face-buffalo-l")
    payload = {"tasks": {"face": {"selected": request.model}}, "models": []}
    with patch.object(router_module.ai_model_manager, "select_model", return_value=True) as select, \
         patch.object(router_module.ai_model_manager, "list_models", return_value=payload):
        import asyncio
        result = asyncio.run(router_module.set_model(request))
    select.assert_called_once_with("face", "face-buffalo-l")
    assert result["changed"] is True
    assert result["tasks"] == payload["tasks"]


def test_set_llm_model_stops_process_before_switch():
    request = SimpleNamespace(task="llm", model="llm-minicpm-v-4.6")
    with patch.object(router_module.llm_manager, "stop", new=AsyncMock()) as stop, \
         patch.object(router_module.ai_model_manager, "select_model", return_value=False), \
         patch.object(router_module.ai_model_manager, "list_models", return_value={"tasks": {}, "models": []}):
        import asyncio
        asyncio.run(router_module.set_model(request))
    stop.assert_awaited_once()


def test_set_model_maps_validation_error_to_http_400():
    request = SimpleNamespace(task="face", model="unknown")
    with patch.object(router_module.ai_model_manager, "select_model", side_effect=ValueError("invalid")):
        import asyncio
        with pytest.raises(Exception) as exc_info:
            asyncio.run(router_module.set_model(request))
    assert getattr(exc_info.value, "status_code", None) == 400
