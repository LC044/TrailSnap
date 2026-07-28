"""Unit tests for app/services/onnx_providers.py (provider selection).

We mock onnxruntime and openvino so the function logic is exercised
without actually loading any runtime. Platform mocking is applied after
the module reload so the lru_cache gets a clean view of the environment.
"""

import importlib
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke]


class _FakePlatform:
    """Mock for the `platform` module: `system()` / `machine()` are callable."""

    def __init__(self, system, machine):
        self._system = system
        self._machine = machine

    def system(self):
        return self._system

    def machine(self):
        return self._machine


@pytest.fixture(autouse=True)
def _clean_module():
    """Reload the module + clear caches before and after each test."""
    from app.services import onnx_providers
    importlib.reload(onnx_providers)
    onnx_providers.get_onnx_providers.cache_clear()
    onnx_providers.get_session_options.cache_clear()
    onnx_providers._coreml_blacklist.clear()
    yield onnx_providers
    onnx_providers.get_onnx_providers.cache_clear()
    onnx_providers.get_session_options.cache_clear()
    onnx_providers._coreml_blacklist.clear()


def _install_ort(monkeypatch, providers, *, openvino_devices=None):
    """Install a fake onnxruntime (and optional openvino) module."""
    fake_ort = MagicMock()
    fake_ort.get_available_providers.return_value = list(providers)
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", fake_ort)

    if openvino_devices is not None:
        if openvino_devices:
            fake_ov = MagicMock()
            fake_ov.Core.return_value.available_devices = list(openvino_devices)
            monkeypatch.setitem(__import__("sys").modules, "openvino", fake_ov)
        else:
            monkeypatch.setitem(__import__("sys").modules, "openvino", None)
    return fake_ort


def _patch_platform(monkeypatch, mod, *, system, machine):
    monkeypatch.setattr(mod, "platform", _FakePlatform(system, machine))
    mod.get_onnx_providers.cache_clear()
    mod.get_session_options.cache_clear()


def test_get_onnx_providers_falls_back_to_cpu_when_ort_missing(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", None)
    from app.services import onnx_providers
    providers, options = onnx_providers.get_onnx_providers()
    assert providers == ["CPUExecutionProvider"]
    assert options == [{}]


def test_get_onnx_providers_picks_cuda_first(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(monkeypatch, [
        "CPUExecutionProvider", "CUDAExecutionProvider", "OpenVINOExecutionProvider",
    ])
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    providers, options = mod.get_onnx_providers()
    assert providers[0] == "CUDAExecutionProvider"
    assert options[0] == {"device_id": 0}
    assert "OpenVINOExecutionProvider" in providers


def test_get_onnx_providers_filters_coreml_on_non_apple(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    providers, _ = mod.get_onnx_providers()
    assert "CoreMLExecutionProvider" not in providers
    assert "CPUExecutionProvider" in providers


def test_get_onnx_providers_keeps_coreml_on_apple_silicon(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    providers, _ = mod.get_onnx_providers()
    assert "CoreMLExecutionProvider" in providers


def test_get_onnx_providers_respects_disable_coreml_env(monkeypatch, _clean_module):
    mod = _clean_module
    monkeypatch.setenv("DISABLE_COREML", "1")
    _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    providers, _ = mod.get_onnx_providers()
    assert "CoreMLExecutionProvider" not in providers


def test_get_onnx_providers_openvino_picks_npu_when_available(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(
        monkeypatch,
        ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        openvino_devices=["CPU", "NPU", "GPU"],
    )
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    providers, options = mod.get_onnx_providers()
    openvino_idx = providers.index("OpenVINOExecutionProvider")
    assert options[openvino_idx] == {"device_type": "NPU"}


def test_get_onnx_providers_openvino_env_override(monkeypatch, _clean_module):
    mod = _clean_module
    monkeypatch.setenv("OPENVINO_DEVICE", "GPU")
    _install_ort(
        monkeypatch,
        ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        openvino_devices=["CPU", "NPU", "GPU"],
    )
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    providers, options = mod.get_onnx_providers()
    openvino_idx = providers.index("OpenVINOExecutionProvider")
    assert options[openvino_idx] == {"device_type": "GPU"}


def test_get_onnx_providers_openvino_falls_back_to_cpu(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(
        monkeypatch,
        ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        openvino_devices=[],  # simulate openvino missing
    )
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    providers, options = mod.get_onnx_providers()
    openvino_idx = providers.index("OpenVINOExecutionProvider")
    assert options[openvino_idx] == {"device_type": "CPU"}


def test_get_onnx_providers_coreml_options_use_env_overrides(monkeypatch, _clean_module):
    mod = _clean_module
    monkeypatch.setenv("COREML_MODEL_FORMAT", "NeuralNetwork")
    monkeypatch.setenv("COREML_COMPUTE_UNITS", "CPUAndNeuralEngine")
    _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    providers, options = mod.get_onnx_providers()
    coreml_idx = providers.index("CoreMLExecutionProvider")
    opts = options[coreml_idx]
    assert opts["ModelFormat"] == "NeuralNetwork"
    assert opts["MLComputeUnits"] == "CPUAndNeuralEngine"
    assert opts["RequireStaticInputShapes"] == "0"
    assert opts["EnableOnSubgraphs"] == "0"


def test_get_session_options_returns_none_for_non_apple(monkeypatch, _clean_module):
    mod = _clean_module
    _install_ort(monkeypatch, ["CPUExecutionProvider"])
    _patch_platform(monkeypatch, mod, system="Linux", machine="x86_64")

    assert mod.get_session_options() is None


def test_get_session_options_returns_optimized_for_apple(monkeypatch, _clean_module):
    mod = _clean_module
    fake_ort = _install_ort(monkeypatch, ["CPUExecutionProvider"])
    fake_so = MagicMock()
    fake_ort.SessionOptions.return_value = fake_so
    fake_ort.GraphOptimizationLevel.ORT_ENABLE_ALL = "ORT_ENABLE_ALL"
    fake_ort.ExecutionMode.ORT_SEQUENTIAL = "ORT_SEQUENTIAL"
    monkeypatch.setenv("ORT_INTRA_OP_THREADS", "4")
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    so = mod.get_session_options()
    assert so is fake_so
    assert so.graph_optimization_level == "ORT_ENABLE_ALL"
    assert so.intra_op_num_threads == 4
    assert so.inter_op_num_threads == 1
    assert so.execution_mode == "ORT_SEQUENTIAL"


def test_create_inference_session_uses_blacklist_to_force_cpu(monkeypatch, _clean_module):
    mod = _clean_module
    mod._coreml_blacklist.add("/models/bad.onnx")

    fake_ort = _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    fake_session = MagicMock(name="session")
    fake_ort.InferenceSession.return_value = fake_session
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    sess = mod.create_inference_session("/models/bad.onnx")
    assert sess is fake_session
    args, kwargs = fake_ort.InferenceSession.call_args
    assert kwargs["providers"] == ["CPUExecutionProvider"]


def test_create_inference_session_falls_back_to_cpu_on_coreml_failure(monkeypatch, _clean_module):
    mod = _clean_module
    fake_ort = _install_ort(monkeypatch, ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    cpu_session = MagicMock(name="cpu_session")
    fake_ort.InferenceSession.side_effect = [RuntimeError("CoreML boom"), cpu_session]
    _patch_platform(monkeypatch, mod, system="Darwin", machine="arm64")

    sess = mod.create_inference_session("/models/x.onnx")
    assert sess is cpu_session
    assert "/models/x.onnx" in mod._coreml_blacklist
