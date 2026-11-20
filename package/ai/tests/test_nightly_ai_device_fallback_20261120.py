"""Accelerator fallback branches of the desktop AI runtime."""
import sys
import types
from types import SimpleNamespace

import pytest

from app.services import desktop_device, face_service, onnx_providers

pytestmark = [pytest.mark.smoke, pytest.mark.module_desktop]


class FakeFaceAnalysis:
    def __init__(self, name, root, providers, provider_options=None):
        self.name = name
        self.root = root
        self.providers = list(providers)
        self.models = {"detector": SimpleNamespace(model_file="det.onnx", session=None)}
        self.prepared = None
        if "CPUExecutionProvider" not in self.providers:
            raise RuntimeError("cuda unavailable")

    def prepare(self, ctx_id=0, det_size=(640, 640)):
        self.prepared = (ctx_id, det_size)


def _install_fake_insightface(monkeypatch):
    module = types.ModuleType("insightface")
    app_module = types.ModuleType("insightface.app")
    app_module.FaceAnalysis = FakeFaceAnalysis
    module.app = app_module
    monkeypatch.setitem(sys.modules, "insightface", module)
    monkeypatch.setitem(sys.modules, "insightface.app", app_module)
    monkeypatch.setattr(face_service.ai_model_manager, "get_model_selection", lambda _: "buffalo_l")
    monkeypatch.setattr(face_service, "get_onnx_providers", lambda: (["CUDAExecutionProvider"], [{}]))


def test_desktop_face_model_falls_back_to_cpu_and_replaces_sessions(monkeypatch):
    _install_fake_insightface(monkeypatch)
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    created = []

    def fake_create_session(path):
        created.append(path)
        return SimpleNamespace(path=path, providers=["CPUExecutionProvider"])

    monkeypatch.setattr(onnx_providers, "create_inference_session", fake_create_session)

    app = face_service.load_insightface_model()
    assert app.providers == ["CPUExecutionProvider"]
    assert created == ["det.onnx"]
    assert app.models["detector"].session.path == "det.onnx"
    assert app.prepared == (0, (640, 640))


def test_face_model_propagates_the_failure_outside_the_desktop_runtime(monkeypatch):
    _install_fake_insightface(monkeypatch)
    monkeypatch.delenv("TS_AI_BACKEND", raising=False)
    with pytest.raises(RuntimeError, match="cuda unavailable"):
        face_service.load_insightface_model()


def _fake_session(monkeypatch, *, report, fail_init=False, fail_run=False):
    import onnxruntime as ort

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.providers = list(report)
            if fail_init:
                raise RuntimeError("session init failed")

        def get_providers(self):
            return list(self.providers)

        def disable_fallback(self):
            pass

        def run(self, output_names, input_feed, run_options=None):
            if fail_run:
                raise RuntimeError("device inference failed")
            return ["ok"]

    monkeypatch.setattr(ort, "InferenceSession", FakeSession)


def test_session_reports_a_provider_mismatch(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    monkeypatch.setattr(desktop_device, "_sessions", {})
    _fake_session(monkeypatch, report=["CPUExecutionProvider"])
    session = onnx_providers._make_session(
        "model.onnx", None, ["CUDAExecutionProvider", "CPUExecutionProvider"], [{}, {}]
    )
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert "初始化失败" in desktop_device._sessions["model.onnx"]["error"]


def test_cpu_only_session_failure_is_raised(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    _fake_session(monkeypatch, report=["CPUExecutionProvider"], fail_init=True)
    with pytest.raises(RuntimeError, match="session init failed"):
        onnx_providers._make_session("model.onnx", None, ["CPUExecutionProvider"], [{}])


def test_cpu_only_execution_failure_is_raised(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    _fake_session(monkeypatch, report=["CPUExecutionProvider"], fail_run=True)
    session = onnx_providers._make_session("model.onnx", None, ["CPUExecutionProvider"], [{}])
    with pytest.raises(RuntimeError, match="device inference failed"):
        session.run(None, {})


def test_cuda_backend_caps_the_ocr_and_face_worker_counts(monkeypatch):
    import os

    from app.routers import face as face_router
    from app.routers import ocr as ocr_router

    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    cpu_count = os.cpu_count() or 4
    assert ocr_router._select_max_workers() == min(2, cpu_count)
    assert face_router._select_max_workers() == min(4, cpu_count)
