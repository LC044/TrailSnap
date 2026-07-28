"""Unit tests for EmbeddingService (app/services/embedding_service.py).

EmbeddingService registers two CLIP models (text + image) with the model_manager
and exposes async helpers that lazily load them via model_downloader / model_manager.

We mock the model manager, downloader, and wrappers to keep these tests fast and
deterministic (no actual ONNX inference).
"""

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

    def fake_register_downloader(name, check, download):
        registered["downloader"].append((name, check, download))

    fake_manager = MagicMock(register_model=MagicMock(side_effect=fake_register_manager))
    fake_downloader = MagicMock(register_model=MagicMock(side_effect=fake_register_downloader))

    monkeypatch.setattr("app.services.embedding_service.model_manager", fake_manager)
    monkeypatch.setattr("app.services.embedding_service.model_downloader", fake_downloader)
    monkeypatch.setattr(
        "app.services.embedding_service.ai_config_manager",
        MagicMock(get_model_selection=MagicMock(return_value="clip-ViT-B-32")),
    )

    from app.services.embedding_service import EmbeddingService

    return EmbeddingService(), registered, fake_manager, fake_downloader


def test_init_registers_text_and_image_models(embedding_service):
    service, registered, _, _ = embedding_service
    names = [entry[0] for entry in registered["manager"]]
    assert names == ["clip_text", "clip_image"]


def test_init_registers_downloader_for_both_models(embedding_service):
    service, registered, _, _ = embedding_service
    names = [entry[0] for entry in registered["downloader"]]
    assert names == ["clip_text", "clip_image"]


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