from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.core import runtime_limits


pytestmark = [pytest.mark.smoke]


def test_configure_inference_runtime_applies_shared_budget(monkeypatch):
    monkeypatch.setattr(settings, "AI_INFERENCE_THREADS", 3)
    for name in runtime_limits.THREAD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    assert runtime_limits.configure_inference_runtime() == 3
    for name in runtime_limits.THREAD_ENV_VARS:
        assert runtime_limits.os.environ[name] == "3"


def test_lower_priority_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AI_LOW_PROCESS_PRIORITY", False)
    with patch.object(runtime_limits.os, "nice", MagicMock(), create=True) as nice:
        runtime_limits.lower_ai_process_priority()
    nice.assert_not_called()
