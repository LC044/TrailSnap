"""Unit tests for EmbeddingService (app/services/embedding_service.py).

EmbeddingService registers two CLIP models (text + image) with the model_manager
and exposes async helpers that lazily load them via model_downloader / model_manager.

We mock the model manager, downloader, and wrappers to keep these tests fast and
deterministic (no actual ONNX inference).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def embedding_service(monkeypatch):
    """Return an EmbeddingService whose heavy dependencies are stubbed out.

    - model_manager.register_model is a no-op (records calls)
    - model_downloader.register_model is a no-op
    - ai_config_manager.get_model_selection returns the canonical ViT-B-32 entry
    """
    registered = {"manager": [], "downloader": []}

    def fake_register_manager(name, loader, release):
        registered["manager"].append((name, loader, release))

    def fake_register_downloader(name, check, download, **_metadata):
        registered["downloader"].append((name, check, download))

    fake_manager = MagicMock(register_model=MagicMock(side_effect=fake_register_manager))
    fake_downloader = MagicMock(register_model=MagicMock(side_effect=fake_register_downloader))
    fake_downloader.get_model_dir.return_value = __import__("pathlib").Path("/catalog/clip")

    monkeypatch.setattr("app.services.embedding_service.model_manager", fake_manager)
    monkeypatch.setattr("app.services.embedding_service.ai_model_manager", fake_downloader)

    from app.services.embedding_service import EmbeddingService

    return EmbeddingService(), registered, fake_manager, fake_downloader


def test_init_registers_text_and_image_models(embedding_service):
    service, registered, _, _ = embedding_service
    names = [entry[0] for entry in registered["manager"]]
    assert names == ["clip_text", "clip_image"]


def test_init_does_not_create_per_service_download_registrations(embedding_service):
    service, registered, _, _ = embedding_service
    names = [entry[0] for entry in registered["downloader"]]
    assert names == []


def test_embed_texts_raises_when_text_model_not_ready(embedding_service):
    service, _, _, fake_downloader = embedding_service
    fake_downloader.is_ready = MagicMock(return_value=False)

    with pytest.raises(Exception, match="Models are not ready"):
        import asyncio
        asyncio.run(service.embed_texts(["hello"]))


def test_embed_texts_returns_list_of_floats(embedding_service):
    service, _, _, fake_downloader = embedding_service
    fake_downloader.is_ready = MagicMock(return_value=True)
    fake_wrapper = MagicMock()
    import numpy as np
    fake_wrapper.encode_text = MagicMock(return_value=np.array([[0.1, 0.2, 0.3]]))
    with patch("app.services.embedding_service.model_manager") as fake_manager:
        fake_manager.get_model = MagicMock(return_value=fake_wrapper)
        import asyncio
        result = asyncio.run(service.embed_texts(["hello"]))
    assert result == [[0.1, 0.2, 0.3]]


def test_embed_images_raises_when_image_model_not_ready(embedding_service):
    service, _, _, fake_downloader = embedding_service
    fake_downloader.is_ready = MagicMock(return_value=False)

    with pytest.raises(Exception, match="Models are not ready"):
        import asyncio
        asyncio.run(service.embed_images(["data:image/png;base64,AAAA"]))


def test_embed_images_returns_list_of_floats(embedding_service):
    service, _, _, fake_downloader = embedding_service
    fake_downloader.is_ready = MagicMock(return_value=True)
    fake_wrapper = MagicMock()
    import numpy as np
    fake_wrapper.encode_image = MagicMock(return_value=np.array([[0.4, 0.5, 0.6]]))
    with patch("app.services.embedding_service.model_manager") as fake_manager:
        fake_manager.get_model = MagicMock(return_value=fake_wrapper)
        import asyncio
        result = asyncio.run(service.embed_images(["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"]))
    assert result == [[0.4, 0.5, 0.6]]

# ---------------------------------------------------------------------------
# _get_model_info: covers both the selected and default branches.
# ---------------------------------------------------------------------------


def test_get_model_info_returns_canonical_clip_vit_b_32_entry(embedding_service):
    service, _, _, _ = embedding_service
    info = service._get_model_info()
    assert info["text_path"].endswith("text")
    assert info["image_path"].endswith("image")


def test_get_model_info_is_resolved_by_unified_manager(embedding_service):
    service, _, _, _ = embedding_service
    with patch("app.services.embedding_service.ai_model_manager.get_model_dir", return_value=__import__("pathlib").Path("/catalog/clip")):
        info = service._get_model_info()
    assert info["text_path"].endswith("clip/text") or info["text_path"].endswith("clip\\text")
    assert info["image_path"].endswith("clip/image") or info["image_path"].endswith("clip\\image")


# ---------------------------------------------------------------------------
# _load_text_model + _load_image_model: cover the ``os.path.exists`` branch.
# ---------------------------------------------------------------------------


def test_load_text_model_returns_wrapper_for_known_text_dir(monkeypatch, embedding_service):
    service, _, _, _ = embedding_service
    fake_wrapper = MagicMock(name="text_wrapper")
    monkeypatch.setattr(
        "app.services.embedding_service.ONNXCLIPTextWrapper", lambda model_dir: fake_wrapper
    )
    # Tokenizer / processor calls inside the wrapper would touch disk in production;
    # since we replace the wrapper itself, they are never invoked.
    result = service._load_text_model()
    assert result is fake_wrapper


def test_load_text_model_never_bypasses_catalog_with_remote_repo(monkeypatch, embedding_service):
    service, _, _, _ = embedding_service
    captured = {}

    def fake_ctor(model_name):
        captured["model_name"] = model_name
        return MagicMock(name="text_wrapper")

    monkeypatch.setattr(
        "app.services.embedding_service.ONNXCLIPTextWrapper", fake_ctor
    )
    service._load_text_model()
    assert captured["model_name"].endswith("text")
    assert not captured["model_name"].startswith("SiYuan044/")


def test_load_image_model_returns_wrapper_for_known_image_dir(monkeypatch, embedding_service):
    service, _, _, _ = embedding_service
    fake_wrapper = MagicMock(name="image_wrapper")
    monkeypatch.setattr(
        "app.services.embedding_service.ONNXCLIPImageWrapper", lambda model_dir: fake_wrapper
    )
    result = service._load_image_model()
    assert result is fake_wrapper


# ---------------------------------------------------------------------------
# _release_model: cover the session / tokenizer / processor cleanup paths.
# ---------------------------------------------------------------------------


def test_release_model_drops_text_session_attributes(embedding_service):
    service, _, _, _ = embedding_service
    wrapper = SimpleNamespace(
        model_dir="fake-text",
        text_session=object(),
        tokenizer=object(),
        processor=None,
        vision_session=None,
    )
    service._release_model(wrapper)
    assert not hasattr(wrapper, "text_session")
    assert not hasattr(wrapper, "tokenizer")


def test_release_model_drops_image_session_attributes(embedding_service):
    service, _, _, _ = embedding_service
    wrapper = SimpleNamespace(
        model_dir="fake-image",
        vision_session=object(),
        processor=object(),
        tokenizer=None,
        text_session=None,
    )
    service._release_model(wrapper)
    assert not hasattr(wrapper, "vision_session")
    assert not hasattr(wrapper, "processor")


def test_release_model_handles_wrapper_without_attrs(embedding_service):
    service, _, _, _ = embedding_service
    wrapper = SimpleNamespace(model_dir="empty")
    # Should not raise; only the log + gc.collect() side-effects happen.
    service._release_model(wrapper)


# ---------------------------------------------------------------------------
# embed_texts error path: wrapper.encode_text raises → propagates after logging.
# ---------------------------------------------------------------------------


def test_embed_texts_propagates_wrapper_exception(embedding_service):
    from app.services import embedding_service as svc

    service, _, _, fake_downloader = embedding_service
    fake_downloader.is_ready = MagicMock(return_value=True)
    fake_wrapper = MagicMock()
    fake_wrapper.encode_text = MagicMock(side_effect=RuntimeError("onnx error"))
    with patch.object(svc.model_manager, "get_model", return_value=fake_wrapper):
        with pytest.raises(RuntimeError, match="onnx error"):
            import asyncio
            asyncio.run(service.embed_texts(["boom"]))



