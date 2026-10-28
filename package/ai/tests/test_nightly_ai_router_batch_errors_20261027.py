"""Nightly coverage for the AI batch routers.

The 2026-10-27 AI coverage scan reported the batch routers as the weakest
modules of the service:

* ``app/routers/face.py`` at 90.2% -- the CUDA branch of
  ``_select_max_workers`` and the generic ``except`` that turns an
  unexpected error into HTTP 500 were never executed.
* ``app/routers/ocr.py`` at 91.4% -- the same two branches.
* ``app/routers/image_classification.py`` at 95.6% -- the CUDA branch of
  ``_select_max_workers`` was never executed.
* ``app/routers/tickets.py`` at 94.6% -- the ``ValueError`` branch that
  maps to HTTP 400 was never executed.
* ``app/routers/llm.py`` at 92.5% -- the ``httpx.RequestError`` branch that
  maps to HTTP 502 was never executed.

The branches are pure control flow: the CUDA probe is faked with a stub
``torch`` module, the inference services are replaced by small stubs and the
upstream HTTP client is faked with a stub that raises.
"""

from __future__ import annotations

import asyncio
import base64
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from app.routers import face as face_router
from app.routers import image_classification as classification_router
from app.routers import llm as llm_router
from app.routers import ocr as ocr_router
from app.routers import tickets as tickets_router


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _FakeCuda:
    def __init__(self, available: bool):
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _FakeTorch:
    def __init__(self, available: bool):
        self.cuda = _FakeCuda(available)


class _BrokenTorch:
    """``torch`` is importable but probing CUDA blows up."""

    class cuda:
        @staticmethod
        def is_available():
            raise RuntimeError("cuda probe failed")


# A payload that survives ``base64.b64decode`` so the tests reach the service call.
_VALID_B64 = base64.b64encode(b"payload").decode()


def _install_torch(monkeypatch, module):
    if module is None:
        # ``import torch`` raises ImportError when sys.modules holds None.
        monkeypatch.setitem(sys.modules, "torch", None)
    else:
        monkeypatch.setitem(sys.modules, "torch", module)


class _BoomAsyncio:
    """``asyncio`` shim whose ``gather`` raises inside the router's try block."""

    def __init__(self):
        self._real = asyncio

    def get_running_loop(self):
        return self._real.get_running_loop()

    def gather(self, *args, **kwargs):
        raise RuntimeError("gather exploded")


# ---------------------------------------------------------------------------
# app/routers/face.py
# ---------------------------------------------------------------------------


def test_face_worker_count_is_capped_on_gpu(monkeypatch):
    monkeypatch.setattr(face_router.os, "cpu_count", lambda: 32)
    _install_torch(monkeypatch, _FakeTorch(available=True))

    assert face_router._select_max_workers() == 4


def test_face_worker_count_fills_the_cpu_cores(monkeypatch):
    monkeypatch.setattr(face_router.os, "cpu_count", lambda: 6)
    _install_torch(monkeypatch, _FakeTorch(available=False))

    assert face_router._select_max_workers() == 6


def test_face_worker_count_falls_back_when_cuda_cannot_be_probed(monkeypatch):
    monkeypatch.setattr(face_router.os, "cpu_count", lambda: 3)
    _install_torch(monkeypatch, _BrokenTorch())

    assert face_router._select_max_workers() == 3


def test_face_worker_count_never_exceeds_eight_on_cpu(monkeypatch):
    monkeypatch.setattr(face_router.os, "cpu_count", lambda: 64)
    _install_torch(monkeypatch, None)

    assert face_router._select_max_workers() == 8


def test_face_process_one_strips_the_data_url_prefix(monkeypatch):
    captured = {}

    def fake_process_image(contents):
        captured["contents"] = contents
        return [{"bbox": [0, 0, 1, 1]}]

    monkeypatch.setattr(face_router.face_service, "process_image", fake_process_image)

    payload = base64.b64encode(b"image-bytes").decode()
    result = face_router._process_one(f"data:image/jpeg;base64,{payload}")

    assert captured["contents"] == b"image-bytes"
    assert result == {"face_count": 1, "faces": [{"bbox": [0, 0, 1, 1]}]}


def test_face_recognition_rejects_an_empty_batch():
    request = face_router.FaceRecognitionRequest(images=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(face_router.face_recognition(request))

    assert exc.value.status_code == 400


def test_face_recognition_isolates_a_single_broken_image(monkeypatch):
    def fake_process_one(b64):
        if b64 == "broken":
            raise ValueError("corrupt image")
        return {"face_count": 0, "faces": []}

    monkeypatch.setattr(face_router, "_process_one", fake_process_one)

    request = face_router.FaceRecognitionRequest(images=["ok", "broken"])
    result = asyncio.run(face_router.face_recognition(request))

    assert result["results"][0] == {"face_count": 0, "faces": []}
    assert result["results"][1]["error"] == "corrupt image"
    assert result["results"][1]["face_count"] == 0
    assert result["results"][1]["faces"] == []


def test_face_recognition_reports_an_unexpected_error_as_500(monkeypatch):
    monkeypatch.setattr(face_router, "asyncio", _BoomAsyncio())

    request = face_router.FaceRecognitionRequest(images=["ok"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(face_router.face_recognition(request))

    assert exc.value.status_code == 500
    assert "gather exploded" in exc.value.detail


# ---------------------------------------------------------------------------
# app/routers/ocr.py
# ---------------------------------------------------------------------------


def test_ocr_worker_count_follows_the_configured_thread_budget_on_gpu(monkeypatch):
    monkeypatch.setattr(ocr_router.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(ocr_router.settings, "AI_INFERENCE_THREADS", 2)
    _install_torch(monkeypatch, _FakeTorch(available=True))

    assert ocr_router._select_max_workers() == 2


def test_ocr_worker_count_follows_the_configured_thread_budget_on_cpu(monkeypatch):
    monkeypatch.setattr(ocr_router.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(ocr_router.settings, "AI_INFERENCE_THREADS", 3)
    _install_torch(monkeypatch, _FakeTorch(available=False))

    assert ocr_router._select_max_workers() == 3


def test_ocr_worker_count_falls_back_when_cuda_cannot_be_probed(monkeypatch):
    monkeypatch.setattr(ocr_router.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(ocr_router.settings, "AI_INFERENCE_THREADS", 3)
    _install_torch(monkeypatch, _BrokenTorch())

    assert ocr_router._select_max_workers() == 3


def test_ocr_worker_count_is_at_least_one(monkeypatch):
    monkeypatch.setattr(ocr_router.os, "cpu_count", lambda: 1)
    monkeypatch.setattr(ocr_router.settings, "AI_INFERENCE_THREADS", 0)
    _install_torch(monkeypatch, _FakeTorch(available=False))

    assert ocr_router._select_max_workers() == 1


def test_ocr_process_one_strips_the_data_url_prefix(monkeypatch):
    captured = {}

    def fake_detect_text(contents):
        captured["contents"] = contents
        return [["hello", 0.99]]

    monkeypatch.setattr(ocr_router.ocr_service, "detect_text", fake_detect_text)

    payload = base64.b64encode(b"ocr-bytes").decode()
    result = ocr_router._process_one(f"data:image/png;base64,{payload}")

    assert captured["contents"] == b"ocr-bytes"
    assert result == {"ocrResults": [["hello", 0.99]], "dataInfo": []}


def test_ocr_predict_rejects_an_empty_batch():
    request = ocr_router.OCRRequest(images=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(ocr_router.ocr_predict(request))

    assert exc.value.status_code == 400


def test_ocr_predict_isolates_a_single_broken_image(monkeypatch):
    def fake_process_one(b64):
        if b64 == "broken":
            raise ValueError("corrupt image")
        return {"ocrResults": [], "dataInfo": []}

    monkeypatch.setattr(ocr_router, "_process_one", fake_process_one)

    request = ocr_router.OCRRequest(images=["ok", "broken"])
    result = asyncio.run(ocr_router.ocr_predict(request))

    assert result.results[0] == {"ocrResults": [], "dataInfo": []}
    assert result.results[1]["error"] == "corrupt image"


def test_ocr_predict_reports_an_unexpected_error_as_500(monkeypatch):
    monkeypatch.setattr(ocr_router, "asyncio", _BoomAsyncio())

    request = ocr_router.OCRRequest(images=["ok"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ocr_router.ocr_predict(request))

    assert exc.value.status_code == 500
    assert "gather exploded" in exc.value.detail


# ---------------------------------------------------------------------------
# app/routers/image_classification.py
# ---------------------------------------------------------------------------


def test_classification_worker_count_is_capped_on_gpu(monkeypatch):
    monkeypatch.setattr(classification_router.os, "cpu_count", lambda: 32)
    _install_torch(monkeypatch, _FakeTorch(available=True))

    assert classification_router._select_max_workers() == 4


def test_classification_worker_count_is_capped_on_cpu(monkeypatch):
    monkeypatch.setattr(classification_router.os, "cpu_count", lambda: 32)
    _install_torch(monkeypatch, _FakeTorch(available=False))

    assert classification_router._select_max_workers() == 4


def test_classification_worker_count_falls_back_when_cuda_cannot_be_probed(monkeypatch):
    monkeypatch.setattr(classification_router.os, "cpu_count", lambda: 2)
    _install_torch(monkeypatch, _BrokenTorch())

    assert classification_router._select_max_workers() == 2


def test_classification_rejects_an_empty_batch():
    request = classification_router.ImageClassificationRequest(images=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(classification_router.classify_images(request))

    assert exc.value.status_code == 400


def test_classification_reports_a_service_failure_as_500(monkeypatch):
    monkeypatch.setattr(
        classification_router.image_classification_service,
        "classify_yolo",
        MagicMock(side_effect=RuntimeError("onnx exploded")),
    )

    request = classification_router.ImageClassificationRequest(images=["ok"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(classification_router.classify_images(request))

    assert exc.value.status_code == 500
    assert "onnx exploded" in exc.value.detail


# ---------------------------------------------------------------------------
# app/routers/tickets.py
# ---------------------------------------------------------------------------


def test_ticket_predict_batch_strips_the_data_url_prefix(monkeypatch):
    captured = {}

    def fake_detect(contents):
        captured["contents"] = contents
        return {"count": 1, "tickets": [{"train_code": "G1"}]}

    monkeypatch.setattr(tickets_router.ticket_service, "detect", fake_detect)

    payload = base64.b64encode(b"ticket-bytes").decode()
    results = tickets_router._predict_batch([f"data:image/jpeg;base64,{payload}"])

    assert captured["contents"] == b"ticket-bytes"
    assert results == [{"ticket_count": 1, "tickets": [{"train_code": "G1"}]}]


def test_ticket_predict_rejects_an_empty_batch():
    request = tickets_router.TicketRecognitionRequest(images=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tickets_router.predict_ticket(request))

    assert exc.value.status_code == 400


def test_ticket_predict_maps_a_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        tickets_router.ticket_service,
        "detect",
        MagicMock(side_effect=ValueError("unsupported ticket image")),
    )

    request = tickets_router.TicketRecognitionRequest(images=[_VALID_B64])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tickets_router.predict_ticket(request))

    assert exc.value.status_code == 400
    assert "unsupported ticket image" in exc.value.detail


def test_ticket_predict_maps_an_unexpected_error_to_500(monkeypatch):
    monkeypatch.setattr(
        tickets_router.ticket_service,
        "detect",
        MagicMock(side_effect=RuntimeError("detector crashed")),
    )

    request = tickets_router.TicketRecognitionRequest(images=[_VALID_B64])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tickets_router.predict_ticket(request))

    assert exc.value.status_code == 500
    assert "detector crashed" in exc.value.detail


# ---------------------------------------------------------------------------
# app/routers/llm.py
# ---------------------------------------------------------------------------


class _FakeUrl:
    query = ""


class _FakeRequest:
    method = "POST"
    url = _FakeUrl()
    headers = {"host": "localhost", "content-length": "2", "accept": "application/json"}

    async def body(self):
        return b"{}"


def test_llm_proxy_reports_an_upstream_connection_error_as_502(monkeypatch):
    async def fake_send(request, stream=False):
        raise httpx.ConnectError("upstream refused the connection")

    stub_client = SimpleNamespace(
        build_request=lambda *args, **kwargs: object(),
        send=fake_send,
    )
    monkeypatch.setattr(llm_router, "client", stub_client)
    monkeypatch.setattr(llm_router.llm_manager, "ensure_running", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(llm_router.proxy_llm(_FakeRequest(), "chat/completions"))

    assert exc.value.status_code == 502
    assert exc.value.detail == "Error communicating with the underlying LLM server"
