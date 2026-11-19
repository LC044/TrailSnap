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


def test_desktop_ocr_injects_selected_sessions(monkeypatch, tmp_path):
    import rapidocr
    from app.services import ocr_service
    from omegaconf import OmegaConf

    class FakeRapidOCR:
        def __init__(self, params):
            self.cfg = self._load_config(None, params)

        def _load_config(self, _path, params):
            return OmegaConf.create({stage: {"model_path": params[f"{stage}.model_path"]} for stage in ("Det", "Cls", "Rec")})

    monkeypatch.setattr(rapidocr, "RapidOCR", FakeRapidOCR)
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_selected_spec", lambda _: {"runtime": {"modelType": "MOBILE", "ocrVersion": "PPOCRV4", "clsOcrVersion": "PPOCRV4", "detFile": "det.onnx", "clsFile": "cls.onnx", "recFile": "rec.onnx"}})
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_model_dir", lambda *_, **__: tmp_path)
    monkeypatch.setattr(onnx_providers, "create_inference_session", lambda path: SimpleNamespace(path=path))
    result = ocr_service.load_paddleocr_model()
    assert result.cfg.Det.session.path.endswith("det.onnx")
    assert result.cfg.Rec.session.path.endswith("rec.onnx")
