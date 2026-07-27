"""Smoke tests for LLMProcessManager error and happy paths.

LLMProcessManager.ensure_running() has two distinct branches worth pinning
down with deterministic tests:

1. Model not yet ready in ModelDownloader -> raise "still downloading"
2. Model ready -> start llama-server subprocess and wait for it to come up

We never want to actually launch llama-server in unit tests, so we replace
``subprocess.Popen`` with a fake that records the argv and reports a
running process.  ``_wait_for_ready`` is patched to return immediately so
we can assert the call contract without the 60 s poll loop.
"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from app.services.llm_manager import LLMProcessManager
from app.services.model_downloader import ModelDownloader


pytestmark = [pytest.mark.smoke]


def _fresh_manager():
    """Build an LLMProcessManager without running __init__.

    __init__ calls _register_download which would touch the global
    model_downloader singleton and the real settings.MODEL_PATH.  For a
    pure unit test we want neither.
    """
    mgr = LLMProcessManager.__new__(LLMProcessManager)
    mgr.process = None
    mgr.last_access_time = time.time()
    mgr.port = 8123
    mgr.lock = asyncio.Lock()
    mgr.repo_id = "test/repo"
    mgr.model_dir_name = "test-model"
    mgr.model_name = "test-model.gguf"
    return mgr


def test_one(monkeypatch):
    """First guard: refuse to start until the model is fully downloaded."""
    monkeypatch.setattr(ModelDownloader, "is_ready", lambda self, key: False)
    mgr = _fresh_manager()

    with pytest.raises(ValueError, match="still downloading"):
        asyncio.run(mgr.ensure_running())

    assert mgr.process is None


def test_two(monkeypatch):
    """Happy path: build the llama-server command from the resolved model path.

    We patch subprocess.Popen so no real llama-server is launched and assert
    the call contract (argv shape, port flag, resolved -m path).
    """
    monkeypatch.setattr(ModelDownloader, "is_ready", lambda self, key: True)
    # Force the "no LLM_MODEL_PATH override" branch.
    monkeypatch.setattr("app.services.llm_manager.settings.LLM_MODEL_PATH", "")

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None  # process is running

    popen_calls = []

    def fake_popen(argv, *args, **kwargs):
        popen_calls.append(argv)
        return fake_proc

    monkeypatch.setattr("app.services.llm_manager.subprocess.Popen", fake_popen)

    async def _noop_wait(self):
        return None

    monkeypatch.setattr(LLMProcessManager, "_wait_for_ready", _noop_wait)

    mgr = _fresh_manager()
    asyncio.run(mgr.ensure_running())

    assert len(popen_calls) == 1
    argv = popen_calls[0]
    assert argv[0] == "llama-server"
    assert "--port" in argv
    assert str(mgr.port) in argv
    # -m should point at the resolved model file (under MODEL_PATH/model_dir_name).
    m_index = argv.index("-m")
    resolved = argv[m_index + 1]
    assert resolved.endswith(mgr.model_name)
    assert mgr.model_dir_name in resolved
    # The running process is recorded on the manager.
    assert mgr.process is fake_proc