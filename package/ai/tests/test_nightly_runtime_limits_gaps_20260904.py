"""Nightly gap rescue 2026-09-04: runtime_limits priority-lowering branches."""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.core import runtime_limits

pytestmark = [pytest.mark.smoke]


def test_lower_priority_windows_uses_psutil(monkeypatch):
    monkeypatch.setattr(settings, "AI_LOW_PROCESS_PRIORITY", True)
    fake_psutil = MagicMock()
    fake_psutil.BELOW_NORMAL_PRIORITY_CLASS = "below-normal"
    proc = MagicMock()
    fake_psutil.Process.return_value = proc
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setattr(runtime_limits.sys, "platform", "win32")

    runtime_limits.lower_ai_process_priority()

    proc.nice.assert_called_once_with("below-normal")


def test_lower_priority_posix_uses_nice(monkeypatch):
    monkeypatch.setattr(settings, "AI_LOW_PROCESS_PRIORITY", True)
    monkeypatch.setattr(runtime_limits.sys, "platform", "linux")
    with patch.object(runtime_limits.os, "nice", MagicMock(), create=True) as nice:
        runtime_limits.lower_ai_process_priority()
    nice.assert_called_once_with(5)


def test_lower_priority_swallows_errors(monkeypatch, caplog):
    monkeypatch.setattr(settings, "AI_LOW_PROCESS_PRIORITY", True)
    fake_psutil = MagicMock()
    fake_psutil.Process.side_effect = RuntimeError("no process handle")
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setattr(runtime_limits.sys, "platform", "win32")

    with caplog.at_level(logging.WARNING, logger="app.main"):
        runtime_limits.lower_ai_process_priority()  # must not raise

    assert any("Unable to lower AI process priority" in r.message for r in caplog.records)


def test_configure_inference_runtime_clamps_to_minimum(monkeypatch):
    monkeypatch.setattr(settings, "AI_INFERENCE_THREADS", 0)
    budget = runtime_limits.configure_inference_runtime()
    assert budget == 1
    for name in runtime_limits.THREAD_ENV_VARS:
        assert runtime_limits.os.environ[name] == "1"
