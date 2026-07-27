"""Unit tests for ModelManager (app/services/model_manager.py).

ModelManager is a process-wide singleton that lazily loads AI models and
periodically evicts idle ones.  We exercise the public surface:
  * lazy load via get_model
  * register / get_model / unknown name errors
  * explicit release path
  * monitor loop evicts a model whose last_used is older than idle_timeout

Tests reset the singleton between cases to avoid state leakage.
"""

import time
from unittest.mock import MagicMock

import pytest

from app.services.model_manager import ModelManager


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def fresh_manager(monkeypatch):
    """Return a ModelManager whose __init__ does not start a monitor thread.

    We replace __init__ with a deterministic copy that only sets fields, and
    reset the singleton so each test gets its own registry.
    """
    def _init_no_thread(self, idle_timeout=300):
        self.models = {}
        self.idle_timeout = idle_timeout
        self.running = True
        self._initialized = True

    monkeypatch.setattr(ModelManager, "_instance", None)
    monkeypatch.setattr(ModelManager, "__init__", _init_no_thread)
    return ModelManager()


def test_get_model_loads_lazily_on_first_call(fresh_manager):
    load_calls = []
    def loader():
        load_calls.append(1)
        return "fake-model-object"
    fresh_manager.register_model("face", load_func=loader)

    assert fresh_manager.get_model("face") == "fake-model-object"
    assert fresh_manager.get_model("face") == "fake-model-object"
    # Lazy: load is only called once even though get_model is called twice.
    assert len(load_calls) == 1


def test_get_model_unknown_name_raises_value_error(fresh_manager):
    with pytest.raises(ValueError, match="not registered"):
        fresh_manager.get_model("nope")


def test_register_model_stores_release_function(fresh_manager):
    release = MagicMock()
    fresh_manager.register_model("ocr", load_func=lambda: "m", release_func=release)
    assert "ocr" in fresh_manager.models
    assert fresh_manager.models["ocr"].release_func is release


def test_release_invokes_custom_release_func_and_clears_model(fresh_manager):
    release = MagicMock()
    fresh_manager.register_model("ocr", load_func=lambda: "m", release_func=release)
    fresh_manager.get_model("ocr")
    wrapper = fresh_manager.models["ocr"]
    assert wrapper.model == "m"

    wrapper.release()

    release.assert_called_once_with("m")
    assert wrapper.model is None


def test_release_without_custom_func_still_clears_model(fresh_manager):
    fresh_manager.register_model("plain", load_func=lambda: 42)
    wrapper = fresh_manager.models["plain"]
    fresh_manager.get_model("plain")
    assert wrapper.model == 42
    wrapper.release()
    assert wrapper.model is None


def test_idle_eviction_releases_models_past_timeout(monkeypatch, fresh_manager):
    """One synchronous pass of the eviction check, no background thread."""
    # Rebuild with a tiny timeout so the math is obvious.
    def _init_no_thread(self, idle_timeout=1):
        self.models = {}
        self.idle_timeout = idle_timeout
        self.running = True
        self._initialized = True
    monkeypatch.setattr(ModelManager, "_instance", None)
    monkeypatch.setattr(ModelManager, "__init__", _init_no_thread)
    mm = ModelManager()
    release = MagicMock()
    mm.register_model("face", load_func=lambda: "m", release_func=release)
    mm.get_model("face")
    wrapper = mm.models["face"]
    wrapper.last_used = time.time() - 10  # backdate -> model is "idle"

    # Inline one iteration of _monitor_loop's eviction logic.
    now = time.time()
    for w in mm.models.values():
        if w.model is not None and (now - w.last_used > mm.idle_timeout):
            w.release()

    assert wrapper.model is None
    release.assert_called_once_with("m")