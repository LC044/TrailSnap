import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.unified_model_manager import UnifiedModelManager


pytestmark = [pytest.mark.smoke]


def test_builtin_catalog_exposes_only_three_ppocrv6_models():
    catalog_path = Path(__file__).resolve().parents[1] / "app" / "model_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    ocr_models = [item for item in catalog["models"] if "ocr" in item["tasks"]]

    assert catalog["tasks"]["ocr"]["default"] == "ocr-ppocrv6-small"
    assert [item["id"] for item in ocr_models] == [
        "ocr-ppocrv6-tiny",
        "ocr-ppocrv6-small",
        "ocr-ppocrv6-medium",
    ]
    assert {item["runtime"]["ocrVersion"] for item in ocr_models} == {"PPOCRV6"}


def test_builtin_catalog_contains_complete_buffalo_m_package():
    catalog_path = Path(__file__).resolve().parents[1] / "app" / "model_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    buffalo_m = next(item for item in catalog["models"] if item["id"] == "face-buffalo-m")

    assert buffalo_m["repoId"] == "SiYuan044/buffalo_m"
    assert buffalo_m["runtimeName"] == "buffalo_m"
    assert buffalo_m["requiredFiles"] == [
        "1k3d68.onnx",
        "2d106det.onnx",
        "det_2.5g.onnx",
        "genderage.onnx",
        "w600k_r50.onnx",
    ]


def test_builtin_visual_llm_is_downloaded_on_first_start():
    catalog_path = Path(__file__).resolve().parents[1] / "app" / "model_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    visual_llm = next(item for item in catalog["models"] if item["id"] == "llm-minicpm-v-4.6")

    assert visual_llm["autoDownload"] is True


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
    wrapper.release_async.assert_called_once()
    trigger.assert_called_once_with("small")
    saved = json.loads(manager.config_path.read_text(encoding="utf-8"))
    assert saved["selections"]["face"] == "small"


def test_delete_selected_model_switches_to_another_ready_model(manager):
    for model_id in ("large", "small"):
        model_dir = manager.get_model_dir(model_id)
        model_dir.mkdir(parents=True)
        (model_dir / "model.onnx").write_bytes(b"onnx")

    wrapper = MagicMock()
    with patch("app.services.unified_model_manager.runtime_model_manager") as runtime:
        runtime.models = {"face": wrapper}
        switched = manager.delete_model("large")

    assert switched == {"face": "small"}
    assert manager.get_selected_id("face") == "small"
    assert not manager.get_model_dir("large").exists()
    wrapper.release.assert_called_once()


def test_delete_selected_model_requires_another_ready_model(manager):
    model_dir = manager.get_model_dir("large")
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"onnx")

    with pytest.raises(RuntimeError, match="请先下载其他模型"):
        manager.delete_model("large")

    assert manager.get_selected_id("face") == "large"
    assert model_dir.exists()


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


def test_selected_download_is_marked_active_before_background_thread_runs(manager):
    with patch("app.services.unified_model_manager.threading.Thread") as thread:
        manager.start_selected_downloads()

    state = manager.get_download_state("face", task=True)
    assert state == {"model_id": "large", "status": "downloading", "error": None}
    assert manager.has_active_downloads() is True

    def fake_snapshot(_repo_id, target, _source):
        (target / "model.onnx").write_bytes(b"onnx")

    with patch.object(manager, "_download_snapshot", side_effect=fake_snapshot):
        thread.call_args.kwargs["target"]()

    assert manager.get_download_state("face", task=True)["status"] == "ready"
    assert manager.has_active_downloads() is False
