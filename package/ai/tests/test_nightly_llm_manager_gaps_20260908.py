"""Nightly gap tests for llama.cpp executable discovery (2026-09-08)."""
import pytest

pytestmark = [pytest.mark.smoke]


def test_llama_executable_prefers_configured_existing_path(monkeypatch, tmp_path):
    from app.services import llm_manager

    executable = tmp_path / "llama-server.exe"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("LLAMA_SERVER_PATH", str(executable))

    with pytest.MonkeyPatch.context() as isolated:
        isolated.setattr(llm_manager.shutil, "which", lambda _: None)
        assert llm_manager.LLMProcessManager._llama_server_executable() == str(executable)


def test_llama_executable_falls_back_to_path_discovery(monkeypatch):
    from app.services import llm_manager

    monkeypatch.delenv("LLAMA_SERVER_PATH", raising=False)
    monkeypatch.setattr(llm_manager.shutil, "which", lambda name: f"/opt/{name}")

    assert llm_manager.LLMProcessManager._llama_server_executable() == "/opt/llama-server"


def test_llama_executable_raises_actionable_error_when_missing(monkeypatch):
    from app.services import llm_manager

    monkeypatch.delenv("LLAMA_SERVER_PATH", raising=False)
    monkeypatch.setattr(llm_manager.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="llama-server 未安装"):
        llm_manager.LLMProcessManager._llama_server_executable()
