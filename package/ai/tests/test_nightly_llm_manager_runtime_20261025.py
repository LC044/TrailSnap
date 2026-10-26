"""Nightly coverage for ``app.services.llm_manager`` runtime branches.

The 2026-10-24 AI coverage report ranked ``services/llm_manager.py`` at
84.0% with 24 statements never executed.  The uncovered region is the
"llama.cpp is not ready yet / not installed yet" half of the manager:

* the CPU-count heuristic used to size the inference thread pool,
* the "model is still downloading" branch of ``ensure_running``,
* the "the user switched models" restart branch,
* the desktop runtime lookup for ``llama-server``,
* the readiness poll and the idle watchdog.

These branches decide what a user sees when they click "chat" on a fresh
desktop install, so the contract under test is "the right actionable
error / the right restart, never a hang".
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import llm_manager as llm_mod


pytestmark = [pytest.mark.smoke]


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """Remove every environment switch that influences the manager."""
    monkeypatch.delenv("LLAMA_ARG_THREADS", raising=False)
    monkeypatch.delenv("LLAMA_SERVER_PATH", raising=False)
    monkeypatch.delenv("TS_DESKTOP_ROOT", raising=False)


# ---------------------------------------------------------------------------
# _available_cpu_count / _llama_thread_count
# ---------------------------------------------------------------------------


def test_available_cpu_count_tolerates_affinity_failure(monkeypatch, tmp_path):
    """A denied CPU-affinity query must not break the thread heuristic."""
    def _boom(_pid):
        raise OSError("not permitted")

    monkeypatch.setattr(llm_mod.os, "sched_getaffinity", _boom, raising=False)
    monkeypatch.setattr(llm_mod.os, "cpu_count", lambda: 4)

    assert llm_mod._available_cpu_count(cgroup_root=tmp_path) == 4


def test_available_cpu_count_respects_cgroup_quota(monkeypatch, tmp_path):
    """A cgroup CPU quota caps the reported CPU count."""
    monkeypatch.setattr(llm_mod.os, "sched_getaffinity", lambda _pid: {0, 1, 2, 3}, raising=False)
    monkeypatch.setattr(llm_mod.os, "cpu_count", lambda: 8)

    (tmp_path / "cpu.max").write_text("200000 100000", encoding="utf-8")

    assert llm_mod._available_cpu_count(cgroup_root=tmp_path) == 2


def test_available_cpu_count_ignores_unreadable_cgroup(monkeypatch, tmp_path):
    """An unreadable cgroup file is ignored, not fatal."""
    monkeypatch.setattr(llm_mod.os, "sched_getaffinity", lambda _pid: {0, 1}, raising=False)
    monkeypatch.setattr(llm_mod.os, "cpu_count", lambda: 2)

    (tmp_path / "cpu.max").write_text("not-a-number", encoding="utf-8")

    assert llm_mod._available_cpu_count(cgroup_root=tmp_path) == 2


def test_llama_thread_count_rejects_non_positive_override(monkeypatch):
    """``LLAMA_ARG_THREADS=0`` is a configuration error, not a silent default."""
    monkeypatch.setenv("LLAMA_ARG_THREADS", "0")

    with pytest.raises(ValueError, match="LLAMA_ARG_THREADS"):
        llm_mod._llama_thread_count()


def test_llama_thread_count_uses_override(monkeypatch):
    """An explicit override wins over the heuristic."""
    monkeypatch.setenv("LLAMA_ARG_THREADS", "7")

    assert llm_mod._llama_thread_count() == 7


def test_llama_thread_count_scales_with_available_cpus(monkeypatch):
    """Without an override the pool uses about half of the CPUs (min. 3)."""
    monkeypatch.setattr(llm_mod, "_available_cpu_count", lambda *a, **k: 8)

    assert llm_mod._llama_thread_count() == 4


# ---------------------------------------------------------------------------
# ensure_running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_running_triggers_the_download_for_a_pending_model(monkeypatch):
    """A pending model starts downloading and reports "downloading"."""
    manager = llm_mod.LLMProcessManager()
    model_manager = MagicMock()
    model_manager.is_ready.return_value = False
    model_manager.get_download_state.return_value = {
        "status": "pending",
        "model_id": "model-1",
        "error": None,
    }
    monkeypatch.setattr(llm_mod, "ai_model_manager", model_manager)
    monkeypatch.setattr(llm_mod.settings, "LLM_MODEL_PATH", "")

    with pytest.raises(llm_mod.LLMModelNotReadyError) as excinfo:
        await manager.ensure_running()

    model_manager.trigger_download.assert_called_once_with("model-1")
    assert excinfo.value.status == "downloading"


@pytest.mark.asyncio
async def test_ensure_running_reports_a_failed_download(monkeypatch):
    """A failed download is surfaced with the original error message."""
    manager = llm_mod.LLMProcessManager()
    model_manager = MagicMock()
    model_manager.is_ready.return_value = False
    model_manager.get_download_state.return_value = {
        "status": "failed",
        "model_id": "model-1",
        "error": "checksum mismatch",
    }
    monkeypatch.setattr(llm_mod, "ai_model_manager", model_manager)
    monkeypatch.setattr(llm_mod.settings, "LLM_MODEL_PATH", "")

    with pytest.raises(llm_mod.LLMModelNotReadyError) as excinfo:
        await manager.ensure_running()

    assert excinfo.value.status == "failed"
    assert "checksum mismatch" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ensure_running_raises_when_the_model_file_is_missing(monkeypatch):
    """A ready-but-empty model directory is a configuration error."""
    manager = llm_mod.LLMProcessManager()
    model_manager = MagicMock()
    model_manager.is_ready.return_value = True
    monkeypatch.setattr(llm_mod, "ai_model_manager", model_manager)
    monkeypatch.setattr(llm_mod.settings, "LLM_MODEL_PATH", "")
    monkeypatch.setattr(manager, "_get_resolved_model_path", lambda: ("", ""))

    with pytest.raises(ValueError, match=r"\.gguf"):
        await manager.ensure_running()


@pytest.mark.asyncio
async def test_ensure_running_restarts_when_the_selected_model_changed(monkeypatch):
    """Switching models restarts the subprocess and passes the mmproj."""
    manager = llm_mod.LLMProcessManager()
    manager.process = MagicMock()
    manager.process.poll.return_value = None
    manager.active_model_id = "model-a"

    model_manager = MagicMock()
    model_manager.is_ready.return_value = True
    model_manager.get_selected_id.return_value = "model-b"
    monkeypatch.setattr(llm_mod, "ai_model_manager", model_manager)
    monkeypatch.setattr(llm_mod.settings, "LLM_MODEL_PATH", "")
    monkeypatch.setattr(
        manager,
        "_get_resolved_model_path",
        lambda: ("C:/models/llm.gguf", "C:/models/mmproj.gguf"),
    )
    monkeypatch.setattr(
        llm_mod.LLMProcessManager, "_llama_server_executable", staticmethod(lambda: "llama-server")
    )

    stopped = AsyncMock()
    monkeypatch.setattr(manager, "_stop_unlocked", stopped)
    ready = AsyncMock()
    monkeypatch.setattr(manager, "_wait_for_ready", ready)

    popen = MagicMock()
    monkeypatch.setattr(llm_mod.subprocess, "Popen", popen)

    await manager.ensure_running()

    stopped.assert_awaited_once()
    command = popen.call_args[0][0]
    assert command[0] == "llama-server"
    assert "C:/models/llm.gguf" in command
    assert "--mmproj" in command
    assert "C:/models/mmproj.gguf" in command
    ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_running_keeps_the_process_when_the_model_is_unchanged(monkeypatch):
    """An unchanged selection reuses the running subprocess."""
    manager = llm_mod.LLMProcessManager()
    manager.process = MagicMock()
    manager.process.poll.return_value = None
    manager.active_model_id = "model-a"

    model_manager = MagicMock()
    model_manager.is_ready.return_value = True
    model_manager.get_selected_id.return_value = "model-a"
    monkeypatch.setattr(llm_mod, "ai_model_manager", model_manager)
    monkeypatch.setattr(llm_mod.settings, "LLM_MODEL_PATH", "")
    monkeypatch.setattr(manager, "_get_resolved_model_path", lambda: ("C:/models/llm.gguf", ""))

    popen = MagicMock()
    monkeypatch.setattr(llm_mod.subprocess, "Popen", popen)

    await manager.ensure_running()

    popen.assert_not_called()


# ---------------------------------------------------------------------------
# _llama_server_executable
# ---------------------------------------------------------------------------


def test_llama_executable_prefers_the_desktop_runtime(monkeypatch, tmp_path):
    """The desktop runtime directory is searched for ``llama-server``."""
    executable = "llama-server.exe" if llm_mod.sys.platform == "win32" else "llama-server"
    runtime = tmp_path / "runtime" / "llama.cpp"
    (runtime / "v1.0.0" / "bin").mkdir(parents=True)
    server = runtime / "v1.0.0" / "bin" / executable
    server.write_bytes(b"binary")

    monkeypatch.setenv("TS_DESKTOP_ROOT", str(tmp_path))
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _name: None)

    assert llm_mod.LLMProcessManager._llama_server_executable() == str(server)


def test_llama_executable_falls_back_to_path(monkeypatch):
    """Without a desktop runtime the executable is taken from PATH."""
    monkeypatch.setattr(llm_mod.shutil, "which", lambda _name: "/usr/bin/llama-server")

    assert llm_mod.LLMProcessManager._llama_server_executable() == "/usr/bin/llama-server"


# ---------------------------------------------------------------------------
# _wait_for_ready / idle_checker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_ready_returns_when_the_server_answers(monkeypatch):
    """A 200 from ``/v1/models`` means the model finished loading."""
    manager = llm_mod.LLMProcessManager()

    response = MagicMock()
    response.status_code = 200

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=response)

    monkeypatch.setattr(llm_mod.httpx, "AsyncClient", lambda *a, **k: client)

    await manager._wait_for_ready()

    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_idle_checker_stops_the_server_after_the_idle_timeout(monkeypatch):
    """An idle llama.cpp subprocess is shut down by the watchdog."""
    manager = llm_mod.LLMProcessManager()
    manager.process = MagicMock()
    manager.process.poll.return_value = None
    manager.last_access_time = time.time() - 10_000

    monkeypatch.setattr(llm_mod.settings, "LLM_IDLE_TIMEOUT", 60)
    monkeypatch.setattr(llm_mod.asyncio, "sleep", AsyncMock())

    stopped = AsyncMock(side_effect=RuntimeError("stop"))
    monkeypatch.setattr(manager, "stop", stopped)

    with pytest.raises(RuntimeError, match="stop"):
        await manager.idle_checker()

    stopped.assert_awaited_once()

