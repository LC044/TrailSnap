"""Unit tests for ``app/services/ticket_service.py`` ONNX model lifecycle.

The 2026-10-22 coverage scan showed ``ticket_service.py`` at 84.5%
(32 missed of 207). The misses sat in the model lifecycle helpers that
wrap the ONNX runtime:

* ``load_onnx_model`` -- refuses to load when the ticket model has not
  been downloaded, reads the ``names`` map out of the ONNX metadata, and
  falls back to the default ``{0: 'label', 1: 'label1'}`` mapping when the
  metadata is missing or unparsable.
* ``release_onnx_model`` -- drops the session.

``load_onnx_model`` is registered with ``model_manager`` at import time,
so it is reachable in tests without touching a real ONNX runtime: the
model manager and the session factory are both stubbed here.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import ticket_service


pytestmark = pytest.mark.smoke


def _session(names_metadata="{}"):
    """A stand-in for an ``onnxruntime.InferenceSession``."""
    session = MagicMock()
    meta = MagicMock()
    meta.custom_metadata_map = {"names": names_metadata} if names_metadata is not None else {}
    session.get_modelmeta.return_value = meta
    return session


def test_load_onnx_model_refuses_when_model_is_not_installed():
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=False):
        with pytest.raises(Exception, match="票据识别模型尚未安装"):
            ticket_service.load_onnx_model()


def test_load_onnx_model_uses_default_names_when_metadata_missing():
    session = _session(names_metadata=None)
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session", return_value=session):
        result = ticket_service.load_onnx_model()

    assert result is session
    assert session.names == {0: "label", 1: "label1"}


def test_load_onnx_model_uses_default_names_when_metadata_is_empty_map():
    session = _session(names_metadata="{}")
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session", return_value=session):
        result = ticket_service.load_onnx_model()

    assert result.names == {0: "label", 1: "label1"}


def test_load_onnx_model_parses_names_from_metadata():
    session = _session(names_metadata="{0: 'label', 1: 'label1', 2: 'other'}")
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session", return_value=session):
        result = ticket_service.load_onnx_model()

    assert result.names == {0: "label", 1: "label1", 2: "other"}


def test_load_onnx_model_keeps_default_names_when_metadata_is_unparsable():
    session = _session(names_metadata="not-a-python-literal")
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session", return_value=session):
        result = ticket_service.load_onnx_model()

    assert result.names == {0: "label", 1: "label1"}


def test_load_onnx_model_builds_the_expected_model_path():
    session = _session()
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session",
                      return_value=session) as factory:
        ticket_service.load_onnx_model()

    (model_path,), _ = factory.call_args
    assert model_path.replace("\\", "/").endswith("/ticket/ticket-recognition.onnx")


def test_load_onnx_model_propagates_session_creation_failure():
    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
         patch.object(ticket_service.ai_model_manager, "get_model_dir",
                      return_value="/models/ticket"), \
         patch.object(ticket_service, "create_inference_session",
                      side_effect=RuntimeError("onnx runtime missing")):
        with pytest.raises(RuntimeError, match="onnx runtime missing"):
            ticket_service.load_onnx_model()


def test_release_onnx_model_drops_the_session():
    session = SimpleNamespace(name="session")
    # Must not raise: the helper only drops the reference.
    ticket_service.release_onnx_model(session)
    assert session.name == "session"


def test_ticket_model_is_registered_with_the_runtime_manager():
    assert "tickets_yolo" in ticket_service.model_manager.models
