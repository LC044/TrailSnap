"""Nightly coverage for the selection guards of
``app/services/unified_model_manager.py`` (2026-10-26).

The 2026-10-26 AI coverage scan listed ``services/unified_model_manager.py``
at 91.2% with 32 missed lines.  The missed lines sat in the guards that
decide which model serves an AI capability:

* ``get_selected_id`` never rejected an unknown capability
* ``get_model_selection`` never returned the runtime name of a selection
* ``get_model_dir`` / ``get_model_file`` never refused a path that escapes
  the model root
* ``select_model`` never rejected an unknown capability, a model that does
  not serve the capability or a candidate that is not published yet
* ``delete_model`` never refused to delete a model that is still downloading

The manager is instantiated detached (``object.__new__``) so the process wide
singleton keeps its real catalog and selections.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


def _manager(tmp_path, models=None, tasks=None, selections=None, status=None):
    from app.services.unified_model_manager import UnifiedModelManager

    manager = object.__new__(UnifiedModelManager)
    manager.model_root = (tmp_path / "models").resolve()
    manager.model_root.mkdir(parents=True, exist_ok=True)
    manager.config_path = tmp_path / "ai_config.json"
    manager.legacy_config_path = tmp_path / "legacy_ai_config.json"
    manager._lock = threading.RLock()
    manager._download_lock = threading.Lock()
    manager._active_download = None
    manager._status = dict(status or {})
    manager._errors = {}
    manager._pending_selections = {}
    manager._models = dict(models or {})
    manager._catalog = {"models": list((models or {}).values()), "tasks": dict(tasks or {})}
    manager._selections = dict(selections or {})
    return manager


def _spec(model_id, *, tasks=("ocr",), available=True, local_dir=None, required_files=("model.onnx",)):
    return {
        "id": model_id,
        "name": model_id,
        "runtimeName": f"{model_id}-runtime",
        "localDir": local_dir or f"models/{model_id}",
        "requiredFiles": list(required_files),
        "tasks": list(tasks),
        "available": available,
        "repoId": f"owner/{model_id}",
    }


# ---------------------------------------------------------------------------
# selection lookups
# ---------------------------------------------------------------------------


def test_get_selected_id_rejects_an_unknown_capability(tmp_path):
    manager = _manager(tmp_path, tasks={"ocr": {"default": "a"}})

    with pytest.raises(ValueError, match="未知 AI 能力：speech"):
        manager.get_selected_id("speech")


def test_get_spec_rejects_an_unknown_model(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(KeyError, match="未知模型：ghost"):
        manager.get_spec("ghost")


def test_get_model_selection_returns_the_runtime_name(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a")},
        tasks={"ocr": {"default": "a"}},
        selections={"ocr": "a"},
    )

    assert manager.get_model_selection("ocr") == "a-runtime"


def test_get_model_dir_refuses_to_escape_the_model_root(tmp_path):
    manager = _manager(
        tmp_path,
        models={"evil": _spec("evil", local_dir="../outside")},
        tasks={"ocr": {"default": "evil"}},
        selections={"ocr": "evil"},
    )

    with pytest.raises(ValueError, match="模型目录越界"):
        manager.get_model_dir("evil")


def test_get_model_file_refuses_to_escape_the_model_root(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a")},
        tasks={"ocr": {"default": "a"}},
        selections={"ocr": "a"},
    )

    with pytest.raises(ValueError, match="模型文件路径越界"):
        manager.get_model_file("ocr", "../../../secret.txt")


# ---------------------------------------------------------------------------
# select_model
# ---------------------------------------------------------------------------


def test_select_model_rejects_an_unknown_capability(tmp_path):
    manager = _manager(tmp_path, models={"a": _spec("a")}, tasks={"ocr": {"default": "a"}})

    with pytest.raises(ValueError, match="未知 AI 能力：speech"):
        manager.select_model("speech", "a")


def test_select_model_rejects_a_model_that_cannot_serve_the_capability(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a", tasks=("ocr",))},
        tasks={"ocr": {"default": "a"}, "embedding": {"default": "a"}},
    )

    with pytest.raises(ValueError, match="模型 a 不支持 embedding"):
        manager.select_model("embedding", "a")


def test_select_model_rejects_a_candidate_that_is_not_published(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a", available=False)},
        tasks={"ocr": {"default": "a"}},
    )

    with pytest.raises(ValueError, match="该候选模型的 ModelScope 仓库尚未发布"):
        manager.select_model("ocr", "a")


def test_select_model_reports_an_already_active_selection(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a")},
        tasks={"ocr": {"default": "a"}},
        selections={"ocr": "a"},
    )

    assert manager.select_model("ocr", "a") == {"changed": False, "status": "active"}


# ---------------------------------------------------------------------------
# delete_model
# ---------------------------------------------------------------------------


def test_delete_model_refuses_a_model_that_is_still_downloading(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a")},
        tasks={"ocr": {"default": "a"}},
        selections={"ocr": "a"},
        status={"a": "downloading"},
    )

    with pytest.raises(RuntimeError, match="模型正在下载，暂时无法删除"):
        manager.delete_model("a")


def test_delete_model_without_a_replacement_reports_the_missing_model(tmp_path):
    manager = _manager(
        tmp_path,
        models={"a": _spec("a")},
        tasks={"ocr": {"default": "a", "name": "文字识别"}},
        selections={"ocr": "a"},
    )

    with pytest.raises(RuntimeError, match="没有其他已下载模型"):
        manager.delete_model("a")
