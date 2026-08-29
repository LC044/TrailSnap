import os

"""Unit tests for the AI service LLM process manager (``app/services/llm_manager.py``).

The manager owns a single llama.cpp ``subprocess.Popen`` and gates
``ensure_running`` behind the on-disk ``LLM_MODEL_PATH`` / ``MODEL_PATH``
checks. We exercise:

* ``_get_resolved_model_path`` honours an explicit ``LLM_MODEL_PATH``.
* ``_get_resolved_model_path`` finds a ``.gguf`` inside the model dir.
* ``ensure_running`` raises ``ValueError`` when the model isn't ready.
* ``ensure_running`` is a no-op (no new ``Popen``) when the subprocess is alive.
* ``_wait_for_ready`` terminates the subprocess and raises when the HTTP probe never reaches 200.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_llm]


class _FakeDownloader:
    """Stubbed ``model_downloader`` that flips the ``llm_minicpm`` ready flag."""

    def __init__(self, ready: bool = True):
        self._ready = ready

    def register_model(self, *_a, **_kw):
        return None

    def is_ready(self, _name):
        return self._ready

    def get_download_state(self, _name, task=False):
        return {
            "model_id": "llm-minicpm-v-4.6",
            "status": "ready" if self._ready else "downloading",
            "error": None,
        }

    def trigger_download(self, _model_id):
        return None


def _make_settings(model_path, llm_model_path="", llm_idle_timeout=300, port=8002):
    return type(
        "S",
        (),
        {
            "LLM_MODEL_PATH": llm_model_path,
            "MODEL_PATH": model_path,
            "LLM_SERVER_PORT": port,
            "LLM_IDLE_TIMEOUT": llm_idle_timeout,
        },
    )()


def _make_manager(monkeypatch, settings, ready=True):
    """Build a LLMProcessManager that doesn't touch the real downloader."""
    from app.services import llm_manager as lm

    fake = _FakeDownloader(ready=ready)
    fake.get_selected_spec = lambda _task: {
        "requiredFiles": ["MiniCPM-V-4_6-Q4_K_M.gguf", "mmproj-model-f16.gguf"]
    }
    fake.get_selected_id = lambda _task: "llm-minicpm-v-4.6"
    fake.get_model_dir = lambda _task, task=False: __import__("pathlib").Path(settings.MODEL_PATH) / "MiniCPM-V-4_6-Q4_K_M"
    monkeypatch.setattr(lm, "ai_model_manager", fake)
    monkeypatch.setattr(lm, "settings", settings)

    manager = lm.LLMProcessManager.__new__(lm.LLMProcessManager)
    manager.process = None
    manager.active_model_id = None
    manager.last_access_time = 0
    manager.lock = asyncio.Lock()
    manager.port = settings.LLM_SERVER_PORT
    manager.repo_id = "fake/model"
    manager.model_dir_name = "MiniCPM-V"
    manager.model_name = "MiniCPM-V.gguf"
    return manager


def test_get_resolved_model_path_uses_explicit_env(monkeypatch, tmp_path):
    """When ``LLM_MODEL_PATH`` points at a real file, use it directly."""
    from app.services import llm_manager as lm

    (tmp_path / "explicit.gguf").write_bytes(b"GGUFplaceholder")
    settings = _make_settings(str(tmp_path), llm_model_path=str(tmp_path / "explicit.gguf"))
    manager = _make_manager(monkeypatch, settings)
    resolved, _ = manager._get_resolved_model_path()
    assert resolved.endswith("explicit.gguf")


def test_get_resolved_model_path_finds_gguf_in_model_dir(monkeypatch, tmp_path):
    """Without an explicit path, ``_get_resolved_model_path`` composes a path inside ``MODEL_PATH``."""
    from app.services import llm_manager as lm

    settings = _make_settings(str(tmp_path))
    manager = _make_manager(monkeypatch, settings)
    resolved, _ = manager._get_resolved_model_path()
    # The function returns the composed path regardless of whether the file
    # exists on disk; ``ensure_running`` is responsible for the existence check.
    assert resolved.endswith(os.path.join("MiniCPM-V-4_6-Q4_K_M", "MiniCPM-V-4_6-Q4_K_M.gguf"))


def test_ensure_running_reports_downloading_state(monkeypatch, tmp_path):
    """An unfinished download is distinguishable from a permanent failure."""
    from app.services import llm_manager as lm

    settings = _make_settings(str(tmp_path))
    manager = _make_manager(monkeypatch, settings, ready=False)
    manager._get_resolved_model_path = lambda: (str(tmp_path / "x.gguf"), "")

    with pytest.raises(lm.LLMModelNotReadyError, match="model_status=downloading"):
        asyncio.run(manager.ensure_running())


def test_ensure_running_reports_download_failure(monkeypatch, tmp_path):
    from app.services import llm_manager as lm

    settings = _make_settings(str(tmp_path))
    manager = _make_manager(monkeypatch, settings, ready=False)
    lm.ai_model_manager.get_download_state = lambda _name, task=False: {
        "model_id": "llm-minicpm-v-4.6",
        "status": "failed",
        "error": "modelscope offline",
    }

    with pytest.raises(lm.LLMModelNotReadyError, match="modelscope offline"):
        asyncio.run(manager.ensure_running())


def test_ensure_running_no_op_when_subprocess_alive(monkeypatch, tmp_path):
    """If the subprocess is already alive, we don't start a new one."""
    from app.services import llm_manager as lm

    settings = _make_settings(str(tmp_path))
    manager = _make_manager(monkeypatch, settings, ready=True)
    manager.process = MagicMock()
    manager.process.poll.return_value = None  # alive
    manager.active_model_id = "llm-minicpm-v-4.6"
    manager._get_resolved_model_path = lambda: (str(tmp_path / "x.gguf"), "")

    with patch.object(lm.subprocess, "Popen") as popen:
        asyncio.run(manager.ensure_running())

    popen.assert_not_called()


def test_wait_for_ready_terminates_and_raises(monkeypatch, tmp_path):
    """The readiness loop must kill the subprocess and surface ``RuntimeError``."""
    from app.services import llm_manager as lm

    settings = _make_settings(str(tmp_path))
    manager = _make_manager(monkeypatch, settings, ready=True)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.terminate = MagicMock()
    fake_process.kill = MagicMock()

    manager.process = fake_process

    async def _drive():
        manager.logger = MagicMock()

        async def _no_sleep(_):
            return None

        with patch.object(lm.asyncio, "sleep", side_effect=_no_sleep), \
             patch("app.services.llm_manager.httpx.AsyncClient") as client:
            instance = MagicMock()

            async def _raise(*_a, **_kw):
                import httpx as _h
                raise _h.RequestError("never ready")
            instance.get = AsyncMock(side_effect=_raise)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            client.return_value = instance

            with pytest.raises(RuntimeError, match="failed to start"):
                await manager._wait_for_ready()

    asyncio.run(_drive())
    # ``stop`` was called as part of the cleanup path.
    fake_process.terminate.assert_called_once()
