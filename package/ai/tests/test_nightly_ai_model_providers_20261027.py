"""Nightly coverage for the ONNX provider selection and the unified model
catalog facade.

The 2026-10-27 AI coverage scan reported:

* ``services/onnx_providers.py`` at 92.8% -- the "no provider available at
  all" fallback to the CPU, the successful ``sysctl`` probe of the Apple
  performance cores, the session construction without explicit options and
  the "CoreML is not selected" shortcut were never executed.
* ``services/unified_model_manager.py`` at 92.3% -- the runtime-key lookup of
  the model catalog, the path-escape guard of ``get_model_file``, the
  ``revision`` / ``allowPatterns`` forwarding of the ModelScope download and
  the availability guard of ``trigger_download`` were never executed.

Neither needs a model file or a network: the provider probe is mocked and the
catalog facade is exercised on a hand-built instance.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import onnx_providers
from app.services.unified_model_manager import UnifiedModelManager


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# services/onnx_providers.py
# ---------------------------------------------------------------------------


def test_get_onnx_providers_falls_back_to_cpu_when_nothing_is_available(monkeypatch):
    """An installation without any execution provider must still start."""
    monkeypatch.delenv("DISABLE_COREML", raising=False)
    onnx_providers.get_onnx_providers.cache_clear()
    try:
        with patch("onnxruntime.get_available_providers", return_value=[]):
            providers, options = onnx_providers.get_onnx_providers()
    finally:
        onnx_providers.get_onnx_providers.cache_clear()

    assert providers == ["CPUExecutionProvider"]
    assert options == [{}]


def test_detect_apple_perf_cores_uses_the_sysctl_answer():
    with patch.object(
        onnx_providers.subprocess,
        "run",
        return_value=SimpleNamespace(stdout="8\n", stderr="", returncode=0),
    ):
        assert onnx_providers._detect_apple_perf_cores() == 8


def test_detect_apple_perf_cores_falls_back_to_the_cpu_count():
    with patch.object(onnx_providers.subprocess, "run", side_effect=OSError("no sysctl")):
        detected = onnx_providers._detect_apple_perf_cores()

    assert detected == max(1, os.cpu_count() or 1)


def test_make_session_without_options_lets_onnxruntime_decide():
    """Without session options the runtime must use its own defaults."""
    created = {}

    def _factory(model_path, **kwargs):
        created["model_path"] = model_path
        created["kwargs"] = kwargs
        return "session"

    with patch("onnxruntime.InferenceSession", side_effect=_factory):
        result = onnx_providers._make_session("model.onnx", None, ["CPUExecutionProvider"], [{}])

    assert result == "session"
    assert created["model_path"] == "model.onnx"
    assert "sess_options" not in created["kwargs"]
    assert created["kwargs"]["providers"] == ["CPUExecutionProvider"]


def test_create_inference_session_without_coreml_skips_the_fallback():
    """Without CoreML there is nothing to retry, so the session is built once."""
    with (
        patch.object(
            onnx_providers,
            "get_onnx_providers",
            return_value=(["CUDAExecutionProvider", "CPUExecutionProvider"], [{"device_id": 0}, {}]),
        ),
        patch.object(onnx_providers, "_make_session", return_value="session") as make_session,
    ):
        result = onnx_providers.create_inference_session("model.onnx", "options")

    assert result == "session"
    make_session.assert_called_once_with(
        "model.onnx", "options", ["CUDAExecutionProvider", "CPUExecutionProvider"], [{"device_id": 0}, {}]
    )


# ---------------------------------------------------------------------------
# services/unified_model_manager.py
# ---------------------------------------------------------------------------


def _manager(models=None, selections=None, tasks=None, model_root=None):
    """A catalog facade with the minimum state the tested helpers need."""
    manager = object.__new__(UnifiedModelManager)
    manager._lock = threading.RLock()
    manager._download_lock = threading.Lock()
    manager._active_download = None
    manager._status = {}
    manager._errors = {}
    manager._pending_selections = {}
    manager._models = models if models is not None else {}
    manager._selections = selections if selections is not None else {}
    manager._catalog = {"tasks": tasks if tasks is not None else {}}
    manager.model_root = Path(model_root) if model_root else Path(os.getcwd())
    return manager


def test_resolve_model_id_finds_a_runtime_key():
    """A runtime key resolves to whatever model the task selected."""
    manager = _manager(
        models={"qwen-vl": {"id": "qwen-vl"}},
        selections={"ocr": "qwen-vl"},
        tasks={"ocr": {"runtimeKeys": ["qwen-vl-runtime"]}},
    )

    assert manager._resolve_model_id("qwen-vl") == "qwen-vl"
    assert manager._resolve_model_id("ocr") == "qwen-vl"
    assert manager._resolve_model_id("qwen-vl-runtime") == "qwen-vl"


def test_resolve_model_id_raises_for_an_unknown_key():
    manager = _manager(models={"qwen-vl": {"id": "qwen-vl"}}, tasks={})

    with pytest.raises(KeyError):
        manager._resolve_model_id("does-not-exist")


def test_get_model_file_rejects_a_path_outside_the_model_root(tmp_path):
    manager = _manager(model_root=tmp_path)
    with patch.object(manager, "get_model_dir", return_value=tmp_path / "model"):
        with pytest.raises(ValueError):
            manager.get_model_file("ocr", "../../escaped.bin")


def test_download_snapshot_forwards_revision_and_patterns(tmp_path):
    """A pinned revision and a file filter must reach ModelScope untouched."""
    manager = _manager()
    target = tmp_path / "model"

    with patch(
        "modelscope.hub.snapshot_download.snapshot_download"
    ) as snapshot_download:
        manager._download_snapshot(
            "owner/repo",
            target,
            {"revision": "v1.2.3", "allowPatterns": ["*.onnx", "*.json"]},
        )

    snapshot_download.assert_called_once()
    kwargs = snapshot_download.call_args.kwargs
    assert kwargs["revision"] == "v1.2.3"
    assert kwargs["allow_patterns"] == ["*.onnx", "*.json"]
    assert kwargs["local_dir"] == str(target)
    assert target.is_dir()


def test_trigger_download_refuses_an_unavailable_model():
    manager = _manager(models={"m1": {"id": "m1", "available": False}})

    with pytest.raises(ValueError):
        manager.trigger_download("m1")

    assert manager._status.get("m1") is None


def test_trigger_download_does_not_start_a_second_download():
    manager = _manager(models={"m1": {"id": "m1", "available": True}})
    manager._status["m1"] = "downloading"

    with patch("threading.Thread") as thread:
        manager.trigger_download("m1")

    thread.assert_not_called()
    assert manager._status["m1"] == "downloading"


