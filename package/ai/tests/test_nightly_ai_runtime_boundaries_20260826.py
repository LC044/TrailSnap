"""Boundary coverage for AI runtime paths found by the 2026-08-26 gap scan."""

import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.smoke


def test_embedding_service_decodes_data_url_images(monkeypatch):
    from app.services import embedding_service

    service = embedding_service.EmbeddingService.__new__(embedding_service.EmbeddingService)
    image = b"not-a-real-image"
    data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    wrapper = MagicMock()
    wrapper.encode_image.return_value.tolist.return_value = [[0.25, 0.5]]

    monkeypatch.setattr(embedding_service.ai_model_manager, "is_ready", lambda _name: True)
    monkeypatch.setattr(embedding_service.model_manager, "get_model", lambda _name: wrapper)
    with patch("app.services.embedding_service.Image.open") as open_image:
        open_image.return_value.convert.return_value = "decoded-image"
        result = asyncio.run(service.embed_images([data_url]))

    assert result == [[0.25, 0.5]]
    open_image.assert_called_once()
    open_image.return_value.convert.assert_called_once_with("RGB")


def test_embedding_service_rejects_invalid_image(monkeypatch):
    from app.services import embedding_service

    service = embedding_service.EmbeddingService.__new__(embedding_service.EmbeddingService)
    monkeypatch.setattr(embedding_service.ai_model_manager, "is_ready", lambda _name: True)
    monkeypatch.setattr(embedding_service.model_manager, "get_model", lambda _name: MagicMock())
    with pytest.raises(Exception, match="Incorrect padding"):
        asyncio.run(service.embed_images(["not-valid-base64"]))


def test_llm_manager_uses_configured_server_executable(monkeypatch, tmp_path):
    from app.services import llm_manager

    executable = tmp_path / "llama-server"
    executable.write_bytes(b"x")
    monkeypatch.setenv("LLAMA_SERVER_PATH", str(executable))
    assert llm_manager.LLMProcessManager._llama_server_executable() == str(executable)


def test_llm_manager_stop_releases_running_process(monkeypatch):
    from app.services import llm_manager

    manager = llm_manager.LLMProcessManager.__new__(llm_manager.LLMProcessManager)
    manager.lock = asyncio.Lock()
    process = manager.process = MagicMock()
    process.poll.side_effect = [None, 0, 0]
    process.terminate = MagicMock()
    process.kill = MagicMock()

    asyncio.run(manager.stop())

    process.terminate.assert_called_once_with()
    assert manager.process is None


def test_idle_restart_is_suppressed_while_model_download_is_active(monkeypatch):
    import main as ai_main

    sleep_calls = 0

    async def controlled_sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(ai_main.asyncio, "sleep", controlled_sleep)
    monkeypatch.setattr(ai_main.ai_model_manager, "has_active_downloads", lambda: True)
    kill = MagicMock()
    monkeypatch.setattr(ai_main.os, "kill", kill)

    asyncio.run(ai_main.check_idle_and_restart())

    kill.assert_not_called()


def test_unified_manager_rejects_duplicate_model_ids(tmp_path, monkeypatch):
    from app.services.unified_model_manager import UnifiedModelManager

    catalog = {
        "tasks": {"face": {"name": "Face", "default": "face-a"}},
        "models": [
            {
                "id": "face-a", "tasks": ["face"], "name": "Face A",
                "runtimeName": "face-a", "localDir": "face-a",
                "requiredFiles": ["face.onnx"], "repoId": "owner/face",
            },
            {
                "id": "face-a", "tasks": ["face"], "name": "Duplicate",
                "runtimeName": "duplicate", "localDir": "duplicate",
                "requiredFiles": ["face.onnx"], "repoId": "owner/dup",
            },
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(tmp_path / "catalog.json"))
    monkeypatch.setenv("AI_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr("app.services.unified_model_manager.settings.MODEL_PATH", str(tmp_path / "models"))

    with pytest.raises(ValueError, match="重复 id"):
        UnifiedModelManager()


def test_unified_manager_rejects_model_path_traversal(tmp_path, monkeypatch):
    from app.services.unified_model_manager import UnifiedModelManager

    catalog = {
        "tasks": {"face": {"name": "Face", "default": "face-a"}},
        "models": [{
            "id": "face-a", "tasks": ["face"], "name": "Face A",
            "runtimeName": "face-a", "localDir": "../escape",
            "requiredFiles": ["face.onnx"], "repoId": "owner/face",
        }],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(tmp_path / "catalog.json"))
    monkeypatch.setenv("AI_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr("app.services.unified_model_manager.settings.MODEL_PATH", str(tmp_path / "models"))

    with pytest.raises(ValueError, match="localDir 非法"):
        UnifiedModelManager()


def test_image_classification_discovers_only_category_models(tmp_path, monkeypatch):
    from app.services.image_classification_service import ImageClassificationService

    model_dir = tmp_path / "classification"
    model_dir.mkdir()
    (model_dir / "photo-cls-general.onnx").write_bytes(b"x")
    (model_dir / "photo-cls-animal.onnx").write_bytes(b"x")
    (model_dir / "notes.txt").write_text("not a model")
    monkeypatch.setattr(
        "app.services.image_classification_service.ai_model_manager.get_model_dir",
        lambda *_args, **_kwargs: model_dir,
    )

    service = ImageClassificationService.__new__(ImageClassificationService)

    assert service._discover_category_models() == {"animal": "photo-cls-animal.onnx"}


def test_ticket_parser_accepts_numeric_train_fallback():
    from app.services.ticket_parser import parse_ticket_info

    texts = ["7006", "北京南站", "天津站"]
    polys = [
        [[0, 0], [20, 0], [20, 10], [0, 10]],
        [[100, 0], [120, 0], [120, 10], [100, 10]],
        [[200, 0], [220, 0], [220, 10], [200, 10]],
    ]

    result = parse_ticket_info(texts, polys)

    assert result["train_code"] == "7006"
    assert result["departure_station"] == "北京南"
    assert result["arrival_station"] == "天津"
