"""Coverage for unified_model_manager gaps found by the 2026-08-29 scan.

Targets four missed branches/loops that the existing test_unified_model_manager.py
suite does not exercise:

1. ``_download`` iterating over a multi-source spec (PR #140's CLIP / buffalo_m
   refactor merged textual + visual into one model id via the ``sources`` list).
2. ``_download_snapshot`` passing through ``revision`` and ``allow_patterns``
   kwargs to ModelScope.
3. ``prepare_model`` synchronous desktop-packaging prep (success + failure).
4. ``release_task`` with ``background=True`` (releases via ``release_async``)
   and the dynamic classification-task branch that iterates ``yolo_photo_cls_*`` wrappers.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.unified_model_manager import UnifiedModelManager


pytestmark = pytest.mark.smoke


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
                "id": "split", "tasks": ["face"], "name": "Split", "runtimeName": "split",
                "localDir": "split", "requiredFiles": ["text/model.onnx", "image/model.onnx"],
                "available": True,
                "sources": [
                    {"repoId": "owner/split-text", "localSubdir": "text", "revision": "r1"},
                    {
                        "repoId": "owner/split-image",
                        "localSubdir": "image",
                        "allowPatterns": ["*.onnx"],
                    },
                ],
            },
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("AI_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        "app.services.unified_model_manager.settings.MODEL_PATH",
        str(tmp_path / "models"),
    )
    return UnifiedModelManager()


def _materialize(model_dir, relative):
    target = model_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"onnx")


def test_download_iterates_sources_and_passes_revision_and_allow_patterns(manager):
    captured_kwargs = []

    def fake_snapshot(repo_id, target, source):
        captured_kwargs.append({"repo_id": repo_id, "source": dict(source)})
        relative = source.get("localSubdir", "")
        _materialize(manager.get_model_dir("split"), f"{relative}/model.onnx" if relative else "model.onnx")

    with patch.object(manager, "_download_snapshot", side_effect=fake_snapshot):
        manager._download("split")

    assert [call["repo_id"] for call in captured_kwargs] == ["owner/split-text", "owner/split-image"]
    assert manager.is_ready("split") is True
    assert manager.list_models()["models"][1]["status"] == "ready"

    text_call, image_call = captured_kwargs
    assert text_call["source"].get("revision") == "r1"
    assert image_call["source"].get("allowPatterns") == ["*.onnx"]


def test_download_raises_when_repo_id_missing(manager):
    manager._models["split"]["sources"] = [{"localSubdir": "text"}]

    # _download swallows RuntimeError into a failed status; validate that path instead.
    manager._download("split")

    listed = next(item for item in manager.list_models()["models"] if item["id"] == "split")
    assert listed["status"] == "failed"
    assert "缺少 ModelScope repoId" in listed["error"]


def test_download_raises_when_required_files_missing_after_snapshot(manager):
    def fake_snapshot(repo_id, target, source):
        target.mkdir(parents=True, exist_ok=True)

    with patch.object(manager, "_download_snapshot", side_effect=fake_snapshot):
        manager._download("large")

    listed = next(item for item in manager.list_models()["models"] if item["id"] == "large")
    assert listed["status"] == "failed"
    assert listed["error"].startswith("下载完成但缺少必要文件")


def test_prepare_model_returns_path_when_ready(manager, tmp_path):
    _materialize(manager.get_model_dir("large"), "model.onnx")
    result = manager.prepare_model("face")
    assert result == manager.get_model_dir("large")
    assert manager.is_ready("large") is True


def test_prepare_model_synchronously_downloads_then_returns(manager, tmp_path):
    def fake_snapshot(repo_id, target, source):
        _materialize(manager.get_model_dir("large"), "model.onnx")

    with patch.object(manager, "_download_snapshot", side_effect=fake_snapshot):
        result = manager.prepare_model("face")

    assert result == manager.get_model_dir("large")
    assert manager.is_ready("large") is True


def test_prepare_model_raises_with_underlying_error_when_download_fails(manager, tmp_path):
    with patch.object(manager, "_download_snapshot", side_effect=RuntimeError("offline")):
        with pytest.raises(RuntimeError, match="offline"):
            manager.prepare_model("face")


def test_release_task_background_uses_release_async_for_runtime_keys():
    from app.services import unified_model_manager

    manager = unified_model_manager.UnifiedModelManager.__new__(
        unified_model_manager.UnifiedModelManager
    )
    manager._lock = MagicMock()
    manager._catalog = {
        "tasks": {"face": {"name": "Face", "default": "large", "runtimeKeys": ["face"]}},
    }
    face_wrapper = MagicMock()
    unrelated_wrapper = MagicMock()

    with patch("app.services.unified_model_manager.runtime_model_manager") as runtime:
        runtime.models = {"face": face_wrapper, "other": unrelated_wrapper}
        manager.release_task("face", background=True)

    face_wrapper.release_async.assert_called_once()
    face_wrapper.release.assert_not_called()
    unrelated_wrapper.release_async.assert_not_called()


def test_release_task_classification_releases_dynamic_yolo_wrappers():
    from app.services import unified_model_manager

    manager = unified_model_manager.UnifiedModelManager.__new__(
        unified_model_manager.UnifiedModelManager
    )
    manager._lock = MagicMock()
    manager._catalog = {
        "tasks": {"classification": {"name": "Classification", "default": "yolo", "runtimeKeys": ["yolo"]}},
    }
    yolo_photo = MagicMock()
    yolo_unrelated = MagicMock()

    with patch("app.services.unified_model_manager.runtime_model_manager") as runtime:
        runtime.models = {
            "yolo": MagicMock(),
            "yolo_photo_cls_dog": yolo_photo,
            "yolo_photo_cls_cat": yolo_photo,
            "yolo_face_cls_x": yolo_unrelated,
        }
        manager.release_task("classification", background=False)

    yolo_photo.release.assert_any_call()
    yolo_unrelated.release.assert_not_called()


def test_release_task_unknown_task_raises():
    from app.services import unified_model_manager

    manager = unified_model_manager.UnifiedModelManager.__new__(
        unified_model_manager.UnifiedModelManager
    )
    manager._lock = MagicMock()
    manager._catalog = {"tasks": {}}

    with pytest.raises(ValueError, match="未知 AI 能力"):
        manager.release_task("unknown-task")


def test_select_model_returns_false_when_already_selected():
    from app.services import unified_model_manager

    manager = unified_model_manager.UnifiedModelManager.__new__(
        unified_model_manager.UnifiedModelManager
    )
    manager._lock = MagicMock()
    manager._catalog = {
        "tasks": {"face": {"name": "Face", "default": "large", "runtimeKeys": ["face"]}},
        "models": [],
    }
    manager._selections = {"face": "large"}

    with patch.object(manager, "get_spec", return_value={"tasks": ["face"], "available": True}):
        assert manager.select_model("face", "large") is False

