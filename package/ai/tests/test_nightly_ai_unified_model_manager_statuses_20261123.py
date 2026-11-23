"""Nightly watch 2026-11-23 - app/services/unified_model_manager.py 的选择与状态盲区。

UnifiedModelManager 负责 AI 模型目录、每个能力的当前选择与下载状态。
_load_json 读取磁盘配置，_load_selections 把磁盘上的选择归一化成合法选择，
refresh_statuses 根据文件是否齐备刷新每个模型的状态。

本文件覆盖：

- _load_json 读取 JSON（happy）
- _load_json 对损坏的 JSON 抛错（error）
- refresh_statuses 把齐备的模型标记为 ready 并清空错误（happy）
- refresh_statuses 把缺文件的模型标记为 pending（happy）
- refresh_statuses 保留 failed / downloading 状态（edge）
- _load_selections 在磁盘选择非法时回落到默认（edge）
- _load_selections 迁移旧版选择名（edge）
- _load_selections 把 embedding 的 v1 默认升级为中文 CLIP（edge）
- _load_selections 过滤掉未知的 pendingSelections（edge）
- _load_selections 忽略损坏的配置文件（error）
"""

import json
import threading
from pathlib import Path

import pytest

from app.services.unified_model_manager import UnifiedModelManager

pytestmark = [pytest.mark.smoke]


def _manager(tmp_path, models=None, tasks=None, selections=None, status=None):
    """构造一个脱离单例的 manager 实例，避免污染进程级状态。"""
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


def _spec(model_id, tasks=("ocr",), local_dir=None, required_files=("model.onnx",)):
    return {
        "id": model_id,
        "name": model_id,
        "runtimeName": model_id + "-runtime",
        "localDir": local_dir or ("models/" + model_id),
        "requiredFiles": list(required_files),
        "tasks": list(tasks),
        "repoId": "owner/" + model_id,
    }


def _write_config(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------
# _load_json
# --------------------------------------------------------------------------


def test_load_json_reads_a_json_object(tmp_path):
    path = tmp_path / "config.json"
    _write_config(path, {"a": 1})

    assert UnifiedModelManager._load_json(path) == {"a": 1}


def test_load_json_rejects_a_broken_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        UnifiedModelManager._load_json(path)


# --------------------------------------------------------------------------
# refresh_statuses
# --------------------------------------------------------------------------


def _install_files(manager, model_id, spec):
    base = manager.model_root / spec["localDir"]
    base.mkdir(parents=True, exist_ok=True)
    for relative in spec["requiredFiles"]:
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")


def test_refresh_statuses_marks_a_complete_model_ready(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    _install_files(manager, "m1", spec)
    manager._status["m1"] = "pending"
    manager._errors["m1"] = "old error"

    manager.refresh_statuses()

    assert manager._status["m1"] == "ready"
    assert manager._errors["m1"] is None


def test_refresh_statuses_marks_an_incomplete_model_pending(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    manager._status["m1"] = "ready"

    manager.refresh_statuses()

    assert manager._status["m1"] == "pending"


def test_refresh_statuses_keeps_a_failed_status(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    manager._status["m1"] = "failed"

    manager.refresh_statuses()

    assert manager._status["m1"] == "failed"


def test_refresh_statuses_skips_downloading_models(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    manager._status["m1"] = "downloading"

    manager.refresh_statuses()

    assert manager._status["m1"] == "downloading"


# --------------------------------------------------------------------------
# _load_selections
# --------------------------------------------------------------------------


def test_load_selections_falls_back_to_the_default_for_an_unknown_model(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    _write_config(manager.config_path, {"version": 2, "selections": {"ocr": "ghost"}})

    selections = manager._load_selections()

    assert selections == {"ocr": "m1"}


def test_load_selections_migrates_a_legacy_selection_name(tmp_path):
    spec = _spec("face-buffalo-l", tasks=("face",))
    manager = _manager(tmp_path, models={"face-buffalo-l": spec}, tasks={"face": {"default": "face-buffalo-l"}})
    _write_config(
        manager.config_path,
        {"version": 2, "models": {"face": {"selected": "buffalo_l"}}},
    )

    selections = manager._load_selections()

    assert selections == {"face": "face-buffalo-l"}


def test_load_selections_upgrades_the_v1_embedding_default(tmp_path):
    default_spec = _spec("embedding-clip-vit-b32", tasks=("embedding",))
    chinese_spec = _spec("embedding-chinese-clip-vit-b16", tasks=("embedding",))
    manager = _manager(
        tmp_path,
        models={"embedding-clip-vit-b32": default_spec, "embedding-chinese-clip-vit-b16": chinese_spec},
        tasks={"embedding": {"default": "embedding-clip-vit-b32"}},
    )
    _write_config(manager.config_path, {"version": 1, "selections": {"embedding": "embedding-clip-vit-b32"}})

    selections = manager._load_selections()

    assert selections == {"embedding": "embedding-chinese-clip-vit-b16"}


def test_load_selections_filters_unknown_pending_selections(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    _write_config(
        manager.config_path,
        {"version": 2, "selections": {"ocr": "m1"}, "pendingSelections": {"ocr": "ghost", "bogus": "m1"}},
    )

    manager._load_selections()

    assert manager._pending_selections == {}


def test_load_selections_ignores_a_broken_config_file(tmp_path):
    spec = _spec("m1")
    manager = _manager(tmp_path, models={"m1": spec}, tasks={"ocr": {"default": "m1"}})
    manager.config_path.write_text("{broken", encoding="utf-8")

    selections = manager._load_selections()

    assert selections == {"ocr": "m1"}
