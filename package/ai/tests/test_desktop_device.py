import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import desktop_device, onnx_providers

pytestmark = [pytest.mark.smoke, pytest.mark.module_desktop]


@pytest.fixture(autouse=True)
def clear_probe():
    desktop_device.desktop_device.cache_clear()
    onnx_providers.get_onnx_providers.cache_clear()
    yield
    desktop_device.desktop_device.cache_clear()
    onnx_providers.get_onnx_providers.cache_clear()


def test_cpu_probe_executes_real_onnx_model():
    result = desktop_device.probe_device("cpu", "CPU")
    assert result["provider"] == "CPUExecutionProvider"
    assert result["error"] is None


def test_failed_accelerator_is_reported_as_cpu(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    monkeypatch.setattr(desktop_device, "probe_device", lambda *_: (_ for _ in ()).throw(RuntimeError("driver missing")))
    result = desktop_device.desktop_device()
    assert result["backend"] == "cpu"
    assert result["error"] == "driver missing"
    assert onnx_providers.get_onnx_providers() == (["CPUExecutionProvider"], [{}])


def test_cpu_failure_does_not_claim_working_device(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cpu")
    monkeypatch.setattr(desktop_device, "probe_device", lambda *_: (_ for _ in ()).throw(RuntimeError("broken runtime")))
    with pytest.raises(RuntimeError, match="CPU 推理验证失败"):
        desktop_device.desktop_device()


def test_per_model_creation_failure_falls_back_and_records_reason(monkeypatch):
    import onnxruntime as ort
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    calls = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs["providers"])
            if kwargs["providers"][0] == "CUDAExecutionProvider":
                raise RuntimeError("unsupported model")

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def disable_fallback(self):
            pass

    monkeypatch.setattr(ort, "InferenceSession", FakeSession)
    session = onnx_providers._make_session("test-model.onnx", None, ["CUDAExecutionProvider", "CPUExecutionProvider"], [{}, {}])
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert calls[-1] == ["CPUExecutionProvider"]
    assert desktop_device.runtime_status()["models"]["test-model.onnx"]["error"] == "unsupported model"


def test_execution_failure_retries_cpu_and_retains_it_for_subsequent_images(monkeypatch):
    import onnxruntime as ort
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    calls = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.providers = kwargs["providers"]

        def get_providers(self):
            return self.providers

        def disable_fallback(self):
            pass

        def run(self, *args):
            calls.append(self.providers[0])
            if self.providers[0] == "CUDAExecutionProvider":
                raise RuntimeError("CUDA out of memory")
            return ["result"]

    monkeypatch.setattr(ort, "InferenceSession", FakeSession)
    session = onnx_providers._make_session("oom.onnx", None, ["CUDAExecutionProvider", "CPUExecutionProvider"], [{}, {}])
    assert session.run(None, {}) == ["result"]
    assert session.run(None, {}) == ["result"]
    assert calls == ["CUDAExecutionProvider", "CPUExecutionProvider", "CPUExecutionProvider"]
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert desktop_device.runtime_status()["models"]["oom.onnx"]["error"] == "CUDA out of memory"


def test_openvino_choice_is_passed_to_onnx_provider(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setattr(desktop_device, "desktop_device", lambda: {"backend": "openvino", "device": "GPU.0", "provider": "OpenVINOExecutionProvider"})
    assert onnx_providers.get_onnx_providers() == (["OpenVINOExecutionProvider", "CPUExecutionProvider"], [{"device_type": "GPU.0"}, {}])


def test_runtime_endpoint_uses_response_envelope(monkeypatch):
    import desktop_app
    monkeypatch.setattr(desktop_device, "runtime_status", lambda: {"backend": "cpu"})
    response = desktop_app.runtime_device()
    assert response.code == 0 and response.data == {"backend": "cpu"}


def test_accelerator_packaging_and_catalog_validate_versions(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "desktop/scripts/package_ai_runtime.py"
    spec = importlib.util.spec_from_file_location("package_ai_runtime", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    (source / "trailsnap-ai.exe").write_bytes(b"test sidecar")
    for backend in ("cuda", "openvino"):
        (source / "runtime-version.json").write_text(json.dumps({"schemaVersion": 1, "version": "1.2.3", "backend": backend, "platform": "windows-x86_64"}))
        archive = module.package_runtime(source, output)
        archive.with_suffix(".zip.sig").write_text("test-signature")
    catalog = module.catalog(output, "1.2.3")
    assert set(catalog["packages"]) == {"cuda", "openvino"}
    assert len(catalog["packages"]["cuda"]["sha256"]) == 64
    archive.with_suffix(".zip.sig").write_text("")
    with pytest.raises(ValueError, match="signature"):
        module.catalog(output, "1.2.3")
    failed_output = tmp_path / "failed-output"
    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(module.zipfile.ZipFile, "write", disk_full)
    with pytest.raises(OSError, match="disk full"):
        module.package_runtime(source, failed_output)
    assert not list(failed_output.iterdir())


@pytest.mark.parametrize("device", ["GPU", "NPU.0"])
@pytest.mark.parametrize("model_type", ["TINY", "SMALL", "MEDIUM"])
def test_desktop_ocr_uses_rapidocr_openvino_engine(monkeypatch, tmp_path, device, model_type):
    import sys

    import rapidocr
    from app.services import ocr_service

    class FakeRapidOCR:
        def __init__(self, params):
            self.params = params

    monkeypatch.setattr(rapidocr, "RapidOCR", FakeRapidOCR)
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setenv("OPENVINO_DEVICE", device)
    monkeypatch.setitem(sys.modules, "openvino", SimpleNamespace(Core=object))
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", False)
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_selected_spec", lambda _: {"runtime": {"modelType": model_type, "ocrVersion": "PPOCRV6", "clsOcrVersion": "PPOCRV4", "detFile": "det.onnx", "clsFile": "cls.onnx", "recFile": "rec.onnx"}})
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_model_dir", lambda *_, **__: tmp_path)

    def reject_session(*args, **kwargs):
        pytest.fail("OCR sessions should be created by RapidOCR")

    monkeypatch.setattr(onnx_providers, "create_inference_session", reject_session)
    result = ocr_service.load_paddleocr_model()
    assert type(result) is FakeRapidOCR
    assert ocr_service._ocr_engine_is_openvino
    for stage in ("Det", "Cls", "Rec"):
        assert result.params[f"{stage}.engine_type"] is rapidocr.EngineType.OPENVINO
        assert result.params[f"{stage}.model_path"] == tmp_path / f"{stage.lower()}.onnx"


@pytest.mark.parametrize(("stage", "shape", "canvas", "output_shape", "cropped"), [
    ("Det", (1, 3, 510, 3000), (1, 3, 768, 3840), (1, 1, 768, 3840), (1, 1, 510, 3000)),
    ("Cls", (2, 3, 48, 192), (6, 3, 48, 192), (6, 2), (2, 2)),
    ("Rec", (3, 3, 48, 325), (6, 3, 48, 480), (6, 60, 4), (3, 41, 4)),
])
def test_npu_ocr_pads_and_crops(stage, shape, canvas, output_shape, cropped):
    import numpy as np
    from app.services.openvino_npu import OpenVINONPUSession

    session = OpenVINONPUSession.__new__(OpenVINONPUSession)
    session._stage = stage

    def infer(shapes, feeds, indices):
        padded, = feeds
        assert shapes == (canvas,)
        assert padded.shape == canvas
        np.testing.assert_array_equal(padded[:shape[0], :, :shape[2], :shape[3]], 1)
        assert np.count_nonzero(padded) == np.prod(shape)
        assert indices == [0]
        return [np.ones(output_shape)]

    session._infer = infer
    assert session._run_ocr(np.ones(shape, dtype=np.float32), [0])[0].shape == cropped


def test_npu_ocr_fits_panorama_outside_canvases():
    import numpy as np
    from app.services.openvino_npu import OpenVINONPUSession

    session = OpenVINONPUSession.__new__(OpenVINONPUSession)
    session._stage = "Det"

    def infer(shapes, feeds, indices):
        assert shapes == ((1, 3, 768, 3840),)
        assert feeds[0].shape == shapes[0]
        return [np.ones((1, 1, 768, 3840), dtype=np.float32)]

    session._infer = infer
    output, = session._run_ocr(np.ones((1, 3, 512, 4256), dtype=np.float32), [0])
    np.testing.assert_array_equal(output, np.ones((1, 1, 512, 4256), dtype=np.float32))


def test_npu_image_batch_uses_one_static_shape_and_keeps_order():
    import numpy as np
    from app.services.openvino_npu import OpenVINONPUSession

    session = OpenVINONPUSession.__new__(OpenVINONPUSession)
    session._stage = None
    session._inputs = [SimpleNamespace(name="input", shape=[None, 2])]
    session._outputs = [SimpleNamespace(name="output")]
    session._shapes = ((1, 2),)

    def infer(shapes, feeds, indices):
        assert shapes == session._shapes
        assert feeds[0].shape == (1, 2)
        assert list(indices) == [0]
        return feeds

    session._infer = infer
    inputs = np.arange(6).reshape(3, 2)
    np.testing.assert_array_equal(session.run(["output"], {"input": inputs})[0], inputs)


def test_npu_rejects_non_npu_execution_and_remembers_failed_shape(monkeypatch):
    import threading

    from app.services import openvino_npu

    attempts = []
    graph = SimpleNamespace(reshape=lambda _: None)

    def compile_model(graph, device, config):
        attempts.append(device)
        return SimpleNamespace(get_property=lambda _: ["CPU"])

    monkeypatch.setattr(openvino_npu, "_core", lambda: SimpleNamespace(compile_model=compile_model))
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: None)
    session = openvino_npu.OpenVINONPUSession.__new__(openvino_npu.OpenVINONPUSession)
    session._path = "model.onnx"
    session._device = "NPU"
    session._graph = SimpleNamespace(clone=lambda: graph)
    session._requests, session._failures = {}, {}
    session._lock = threading.Lock()
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Expected NPU execution"):
            session._infer(((1, 3),), [], [0])
    assert attempts == ["NPU"]


def test_llama_uses_the_selected_openvino_npu_backend(monkeypatch):
    from app.services import llm_manager

    listing = """Available devices:
  OPENVINO0: GGML_OPENVINO_DEVICE=CPU - CPU
  OPENVINO1: GGML_OPENVINO_DEVICE=GPU - Intel Graphics
  OPENVINO2: GGML_OPENVINO_DEVICE=NPU (selected) - Intel AI Boost
"""
    def probe(command, **kwargs):
        assert command == ["llama-server", "--list-devices"]
        assert kwargs["env"]["GGML_OPENVINO_DEVICE"] == "NPU"
        return SimpleNamespace(returncode=0, stdout=listing, stderr="")

    monkeypatch.setattr(llm_manager.subprocess, "run", probe)
    env = {"GGML_OPENVINO_DEVICE": "NPU"}
    assert llm_manager.LLMProcessManager._llama_npu_backend("llama-server", env) == "OPENVINO2"
    listing = listing.replace("NPU (selected)", "NPU")
    with pytest.raises(RuntimeError, match="未检测到所选 NPU"):
        llm_manager.LLMProcessManager._llama_npu_backend("llama-server", env)
