"""Unit tests for the error-path branches in app/routers/ai_config.py.

Why this file exists:

* The nightly gap scan flagged app/routers/ai_config.py as 76 percent
  covered (12 missed lines out of 50). The pre-existing
  test_ai_config_router.py covers the happy paths only -- the KeyError,
  ValueError, RuntimeError and generic Exception branches that translate
  into HTTPException(4xx/5xx) are untested, so a regression on the
  status code would slip through.

Each router_module.<endpoint> is exercised with a manager that raises
the targeted exception class. We then assert the HTTPException
propagates with the expected status code.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import ai_config as router_module


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai]


# ---------------------------------------------------------------------------
# POST /models/{model_id}/download -- 404 (KeyError) / 409 (ValueError)
# ---------------------------------------------------------------------------


def test_download_managed_model_404_when_model_unknown():
    """Unknown model id -> HTTPException(404) raised from KeyError."""
    with patch.object(
        router_module.ai_model_manager,
        "trigger_download",
        side_effect=KeyError("model-not-found"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.download_managed_model("model-not-found"))
    assert exc.value.status_code == 404


def test_download_managed_model_409_when_already_downloading():
    """Already-downloading model -> HTTPException(409) from ValueError."""
    with patch.object(
        router_module.ai_model_manager,
        "trigger_download",
        side_effect=ValueError("already downloading"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.download_managed_model("face-buffalo-l"))
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /models/{model_id} -- 404 (KeyError) / 409 (RuntimeError)
# ---------------------------------------------------------------------------


def test_delete_managed_model_404_when_model_unknown():
    """Unknown model id -> HTTPException(404) raised from KeyError."""
    with patch.object(
        router_module.ai_model_manager,
        "get_spec",
        return_value={"tasks": ["face"]},
    ), patch.object(
        router_module.ai_model_manager,
        "delete_model",
        side_effect=KeyError("missing"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.delete_managed_model("nope"))
    assert exc.value.status_code == 404


def test_delete_managed_model_409_when_runtime_error():
    """Active runtime -> HTTPException(409) from RuntimeError."""
    with patch.object(
        router_module.ai_model_manager,
        "get_spec",
        return_value={"tasks": ["face"]},
    ), patch.object(
        router_module.ai_model_manager,
        "delete_model",
        side_effect=RuntimeError("model in use"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.delete_managed_model("face-buffalo-l"))
    assert exc.value.status_code == 409


def test_delete_managed_model_calls_llm_stop_for_llm_task():
    """When the deleted model advertises an llm task, llm_manager.stop
    must be awaited BEFORE deletion."""
    with patch.object(
        router_module.ai_model_manager,
        "get_spec",
        return_value={"tasks": ["llm"]},
    ), patch.object(
        router_module.ai_model_manager,
        "delete_model",
        return_value={"llm": "other-llm"},
    ), patch.object(
        router_module.llm_manager,
        "stop",
        new=AsyncMock(),
    ) as stop:
        import asyncio
        result = asyncio.run(router_module.delete_managed_model("MiniCPM-V"))

    stop.assert_awaited_once()
    assert result["status"] == "deleted"
    assert result["switched"] == {"llm": "other-llm"}


# ---------------------------------------------------------------------------
# POST /config/model -- 400 (ValueError/KeyError) / 500 (generic Exception)
# ---------------------------------------------------------------------------


def test_set_model_400_on_value_error():
    """Bad task/model combo -> HTTPException(400) from ValueError."""
    request = SimpleNamespace(task="face", model="bad-model")
    with patch.object(
        router_module.ai_model_manager,
        "select_model",
        side_effect=ValueError("invalid combo"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.set_model(request))
    assert exc.value.status_code == 400


def test_set_model_400_on_key_error():
    """Unknown model id -> HTTPException(400) from KeyError."""
    request = SimpleNamespace(task="face", model="nope")
    with patch.object(
        router_module.ai_model_manager,
        "select_model",
        side_effect=KeyError("missing"),
    ):
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.set_model(request))
    assert exc.value.status_code == 400


def test_set_model_500_on_unexpected_exception():
    """Anything else -> HTTPException(500) and logger.exception is called."""
    request = SimpleNamespace(task="face", model="x")
    with patch.object(
        router_module.ai_model_manager,
        "select_model",
        side_effect=RuntimeError("disk full"),
    ), patch.object(router_module, "logger") as logger:
        with pytest.raises(HTTPException) as exc:
            import asyncio
            asyncio.run(router_module.set_model(request))
    assert exc.value.status_code == 500
    logger.exception.assert_called_once()


def test_set_model_keeps_old_llm_alive_while_replacement_downloads():
    """The current subprocess remains available until the replacement is ready."""
    request = SimpleNamespace(task="llm", model="new-llm")
    with patch.object(
        router_module.ai_model_manager,
        "select_model",
        return_value={"changed": True, "status": "downloading"},
    ), patch.object(
        router_module.llm_manager,
        "stop",
        new=AsyncMock(),
    ) as stop:
        import asyncio
        result = asyncio.run(router_module.set_model(request))

    stop.assert_not_awaited()
    assert result["changed"] is True
    assert result["status"] == "downloading"
    assert result["task"] == "llm"
    assert result["model"] == "new-llm"
