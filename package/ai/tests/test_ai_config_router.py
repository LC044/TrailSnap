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


def test_delete_model_returns_automatic_switches():
    with patch.object(router_module.ai_model_manager, "get_spec", return_value={"tasks": ["face"]}), \
         patch.object(router_module.ai_model_manager, "delete_model", return_value={"face": "face-buffalo-s"}):
        import asyncio
        result = asyncio.run(router_module.delete_managed_model("face-buffalo-l"))
    assert result["status"] == "deleted"
    assert result["switched"] == {"face": "face-buffalo-s"}


def test_set_model_returns_compact_switch_result():
    request = SimpleNamespace(task="face", model="face-buffalo-l")
    with patch.object(
        router_module.ai_model_manager,
        "select_model",
        return_value={"changed": True, "status": "active"},
    ) as select:
        import asyncio
        result = asyncio.run(router_module.set_model(request))
    select.assert_called_once_with("face", "face-buffalo-l")
    assert result["changed"] is True
    assert result["status"] == "active"
    assert result["task"] == "face"
    assert result["model"] == "face-buffalo-l"


def test_set_llm_model_keeps_current_process_until_new_model_is_ready():
    request = SimpleNamespace(task="llm", model="llm-minicpm-v-4.6")
    with patch.object(router_module.llm_manager, "stop", new=AsyncMock()) as stop, \
         patch.object(
             router_module.ai_model_manager,
             "select_model",
             return_value={"changed": True, "status": "downloading"},
         ):
        import asyncio
        asyncio.run(router_module.set_model(request))
    stop.assert_not_awaited()


def test_set_model_maps_validation_error_to_http_400():
    request = SimpleNamespace(task="face", model="unknown")
    with patch.object(router_module.ai_model_manager, "select_model", side_effect=ValueError("invalid")):
        import asyncio
        with pytest.raises(Exception) as exc_info:
            asyncio.run(router_module.set_model(request))
    assert getattr(exc_info.value, "status_code", None) == 400
