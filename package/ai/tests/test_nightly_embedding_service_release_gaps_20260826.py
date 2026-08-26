"""Boundary coverage for EmbeddingService helpers found by the 2026-08-26 gap scan.

Targets the missed-line pockets in app/services/embedding_service.py that the
existing test_embedding_service.py suite intentionally leaves alone:

* ``EmbeddingService._get_model_info`` (path projection)
* ``EmbeddingService._release_model`` (text/image/empty wrappers + gc path)
* the ``except`` branches inside ``embed_texts`` / ``embed_images`` which must
  log via ``logging.error`` and re-raise the original exception

The heavy modelscope + onnxruntime paths inside ONNXCLIPTextWrapper /
ONNXCLIPImageWrapper are out of scope — those need real ONNX sessions and are
covered indirectly by ``test_runtime_lifecycle`` style contracts.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def embedding_service(monkeypatch):
    """Return an EmbeddingService with all I/O collaborators stubbed.

    The constructor calls ``_register_models`` which would normally re-bind
    ``model_manager``. We monkeypatch the dependencies on the module before
    instantiating so the side-effects stay observable from the tests.
    """

    registered = []

    def fake_register(name, loader, release):
        registered.append((name, loader, release))

    fake_manager = MagicMock(register_model=MagicMock(side_effect=fake_register))
    fake_downloader = MagicMock()
    fake_downloader.is_ready = MagicMock(return_value=True)

    monkeypatch.setattr("app.services.embedding_service.model_manager", fake_manager)
    monkeypatch.setattr("app.services.embedding_service.ai_model_manager", fake_downloader)

    from app.services.embedding_service import EmbeddingService

    return EmbeddingService(), registered, fake_manager, fake_downloader


def test_get_model_info_returns_text_and_image_subpaths(embedding_service, monkeypatch, tmp_path):
    service, _, _, _ = embedding_service
    base = tmp_path / "embedding"
    text_dir = base / "text"
    image_dir = base / "image"
    text_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)

    fake_path_manager = MagicMock()
    fake_path_manager.get_model_dir = MagicMock(return_value=base)
    monkeypatch.setattr("app.services.embedding_service.ai_model_manager", fake_path_manager)

    info = service._get_model_info()

    assert info == {
        "text_path": str(text_dir),
        "image_path": str(image_dir),
    }
    fake_path_manager.get_model_dir.assert_called_once_with("embedding", task=True)


def test_release_model_clears_text_session_and_tokenizer(embedding_service):
    service, _, _, _ = embedding_service

    wrapper = MagicMock(spec=["model_dir", "text_session", "tokenizer"])
    wrapper.model_dir = "fake-text-dir"

    service._release_model(wrapper)

    # ``del wrapper.x`` on a MagicMock-backed spec surfaces as a missing attribute.
    assert "text_session" not in vars(wrapper)
    assert "tokenizer" not in vars(wrapper)


def test_release_model_clears_vision_session_and_processor(embedding_service):
    service, _, _, _ = embedding_service

    wrapper = MagicMock(spec=["model_dir", "vision_session", "processor"])
    wrapper.model_dir = "fake-image-dir"

    service._release_model(wrapper)

    assert "vision_session" not in vars(wrapper)
    assert "processor" not in vars(wrapper)


def test_release_model_handles_wrapper_without_resource_attributes(embedding_service):
    service, _, _, _ = embedding_service

    bare = MagicMock(spec=["model_dir"])
    bare.model_dir = "unknown-wrapper"

    # Each ``hasattr`` check on a MagicMock is True; ``del`` removes the
    # entry from ``__dict__`` afterwards. The path must simply not raise.
    service._release_model(bare)

    assert bare.model_dir == "unknown-wrapper"


def test_release_model_log_resource_name_for_unknown_wrapper(embedding_service, caplog):
    service, _, _, _ = embedding_service

    unknown = object()  # no .model_dir

    # The production code calls the module-level ``logging.info`` which routes
    # via the root logger, so we set the capture level there.
    with caplog.at_level(logging.INFO):
        service._release_model(unknown)

    assert any("Releasing resources for unknown" in record.getMessage() for record in caplog.records)


def test_embed_texts_logs_and_propagates_wrapper_errors(embedding_service, caplog):
    service, _, fake_manager, _ = embedding_service

    fake_wrapper = MagicMock()
    fake_wrapper.encode_text = MagicMock(side_effect=RuntimeError("tensor layout mismatch"))
    fake_manager.get_model = MagicMock(return_value=fake_wrapper)

    with caplog.at_level(logging.ERROR, logger="app.services.embedding_service"):
        with pytest.raises(RuntimeError, match="tensor layout mismatch"):
            asyncio.run(service.embed_texts(["hello"]))

    assert any(
        "Error in text embedding" in record.getMessage() for record in caplog.records
    )


def test_embed_images_logs_and_propagates_wrapper_errors(embedding_service, caplog):
    service, _, fake_manager, _ = embedding_service

    fake_wrapper = MagicMock()
    fake_wrapper.encode_image = MagicMock(side_effect=ValueError("pixel_values missing"))
    fake_manager.get_model = MagicMock(return_value=fake_wrapper)

    with caplog.at_level(logging.ERROR, logger="app.services.embedding_service"):
        with pytest.raises(ValueError, match="pixel_values missing"):
            # Tiny 1x1 PNG, decodes fine; the failure is injected via the wrapper.
            asyncio.run(
                service.embed_images(
                    ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"]
                )
            )

    assert any(
        "Error in image embedding" in record.getMessage() for record in caplog.records
    )


def test_embed_images_strips_data_url_prefix(embedding_service, monkeypatch):
    """A comma in the b64 input exercises the ``b64.split(',')[1]`` branch.

    The wrapper is replaced by a MagicMock that records its b64 decoding
    input, so the assertion verifies that the data URL prefix was stripped
    before the encoder sees the bytes.
    """
    service, _, fake_manager, _ = embedding_service

    sentinel_embedding = MagicMock()
    sentinel_embedding.tolist.return_value = [[0.7, 0.8]]
    fake_wrapper = MagicMock()
    fake_wrapper.encode_image = MagicMock(return_value=sentinel_embedding)
    fake_manager.get_model = MagicMock(return_value=fake_wrapper)

    captured = {}
    real_b64decode = __import__("base64").b64decode

    def capturing_b64decode(data, *args, **kwargs):
        captured["payload"] = data
        return real_b64decode(data, *args, **kwargs)

    monkeypatch.setattr(
        "app.services.embedding_service.base64.b64decode", capturing_b64decode
    )

    prefix = "data:image/png;base64,"
    body = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ"
        "/pLvAAAAAElFTkSuQmCC"
    )

    result = asyncio.run(service.embed_images([prefix + body]))

    assert result == [[0.7, 0.8]]
    # The data URL prefix must be stripped before reaching ``b64decode``.
    assert captured["payload"] == body
    assert "," not in captured["payload"]
