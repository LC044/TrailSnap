from unittest.mock import MagicMock, patch

from app.core import runtime_limits


def test_compute_thread_budget_reserves_a_core(monkeypatch):
    monkeypatch.delenv("TASK_COMPUTE_THREADS", raising=False)
    monkeypatch.setenv("TASK_RESERVED_CPU_CORES", "1")
    assert runtime_limits.compute_thread_budget(cpu_count=4) == 3
    assert runtime_limits.compute_thread_budget(cpu_count=16) == 4


def test_configure_worker_runtime_sets_native_thread_limits(monkeypatch):
    monkeypatch.setenv("TASK_COMPUTE_THREADS", "2")
    for name in runtime_limits.THREAD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    assert runtime_limits.configure_worker_runtime() == 2
    for name in runtime_limits.THREAD_ENV_VARS:
        assert runtime_limits.os.environ[name] == "2"


def test_lower_worker_priority_uses_nice_on_unix(monkeypatch):
    monkeypatch.setattr(runtime_limits.sys, "platform", "linux")
    with patch.object(runtime_limits.os, "nice", MagicMock(), create=True) as nice:
        runtime_limits.lower_worker_priority()
    nice.assert_called_once_with(5)
