import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.unified_model_manager import UnifiedModelManager


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def manager(tmp_path, monkeypatch):
    catalog = {
        "version": 1,
        "tasks": {
            "face": {"name": "Face", "default": "large", "runtimeKeys": ["face"]},
        },
        "models": [
            {
                "id": "large", "tasks": ["face"], "name": "Large", "runtimeName": "large",
                "repoId": "owner/large", "localDir": "large", "requiredFiles": ["model.onnx"],
                "available": True,
            },
            {
                "id": "small", "tasks": ["face"], "name": "Small", "runtimeName": "small",
                "repoId": "owner/small", "localDir": "small", "requiredFiles": ["model.onnx"],
                "available": True,
            },
            {
                "id": "draft", "tasks": ["face"], "name": "Draft", "runtimeName": "draft",
                "repoId": "owner/draft", "localDir": "draft", "requiredFiles": ["model.onnx"],
                "available": False,
            },
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("AI_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr("app.services.unified_model_manager.settings.MODEL_PATH", str(tmp_path / "models"))
    return UnifiedModelManager()


def test_catalog_drives_tasks_and_candidate_models(manager):
    result = manager.list_models()
    assert result["tasks"]["face"]["selected"] == "large"
    assert result["tasks"]["face"]["available"] == ["large", "small", "draft"]
    assert [item["id"] for item in result["models"]] == ["large", "small", "draft"]


def test_download_uses_modelscope_snapshot_and_validates_files(manager):
    def fake_snapshot(repo_id, target, source):
        assert repo_id == "owner/large"
        (target / "model.onnx").write_bytes(b"onnx")

    with patch.object(manager, "_download_snapshot", side_effect=fake_snapshot):
        manager._download("large")

    assert manager.is_ready("large") is True
    assert manager.list_models()["models"][0]["status"] == "ready"


def test_switch_releases_runtime_and_persists_selection(manager):
    wrapper = MagicMock()
    with patch("app.services.unified_model_manager.runtime_model_manager") as runtime:
        runtime.models = {"face": wrapper}
        with patch.object(manager, "trigger_download") as trigger:
            assert manager.select_model("face", "small") is True
    wrapper.release.assert_called_once()
    trigger.assert_called_once_with("small")
    saved = json.loads(manager.config_path.read_text(encoding="utf-8"))
    assert saved["selections"]["face"] == "small"


def test_unpublished_candidate_cannot_be_selected_or_downloaded(manager):
    with pytest.raises(ValueError, match="尚未发布"):
        manager.select_model("face", "draft")
    with pytest.raises(ValueError, match="尚未发布"):
        manager.trigger_download("draft")


def test_failed_download_keeps_failed_status_and_error(manager):
    with patch.object(manager, "_download_snapshot", side_effect=RuntimeError("offline")):
        manager._download("large")
    listed = manager.list_models()["models"][0]
    assert listed["status"] == "failed"
    assert listed["error"] == "offline"
