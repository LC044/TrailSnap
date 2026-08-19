"""Single catalog, selection, ModelScope download and runtime lifecycle facade.

Every AI capability resolves its model through this service.  Business services
only ask for the selected specification/path; repository ids and local layouts
live in ``app/model_catalog.json``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.model_manager import model_manager as runtime_model_manager


logger = logging.getLogger(__name__)


class UnifiedModelManager:
    def __init__(self) -> None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        self.catalog_path = Path(os.getenv("AI_MODEL_CATALOG_PATH", data_dir.parent / "model_catalog.json"))
        self.model_root = Path(settings.MODEL_PATH).expanduser().resolve()
        self.config_path = Path(os.getenv("AI_CONFIG_PATH", self.model_root.parent / "ai_config.json"))
        self.legacy_config_path = data_dir / "ai_config.json"
        self.model_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._download_lock = threading.Lock()
        self._status: dict[str, str] = {}
        self._errors: dict[str, str | None] = {}
        self._catalog = self._load_json(self.catalog_path)
        self._models = {item["id"]: item for item in self._catalog.get("models", [])}
        self._validate_catalog()
        self._selections = self._load_selections()
        self.refresh_statuses()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def _validate_catalog(self) -> None:
        model_list = self._catalog.get("models", [])
        if len(self._models) != len(model_list):
            raise ValueError("AI 模型目录包含重复 id")
        tasks = self._catalog.get("tasks", {})
        for model_id, spec in self._models.items():
            local_dir = Path(spec.get("localDir", ""))
            if not spec.get("name") or not spec.get("runtimeName"):
                raise ValueError(f"模型 {model_id} 缺少 name 或 runtimeName")
            if not spec.get("requiredFiles"):
                raise ValueError(f"模型 {model_id} 必须声明 requiredFiles")
            if local_dir.is_absolute() or ".." in local_dir.parts or str(local_dir) in ("", "."):
                raise ValueError(f"模型 {model_id} 的 localDir 非法")
            if not spec.get("repoId") and not spec.get("sources"):
                raise ValueError(f"模型 {model_id} 缺少 ModelScope repoId")
            for relative in spec.get("requiredFiles", []):
                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError(f"模型 {model_id} 的 requiredFiles 路径非法")
            for source in spec.get("sources", []):
                subdir = Path(source.get("localSubdir", ""))
                if not source.get("repoId") or subdir.is_absolute() or ".." in subdir.parts:
                    raise ValueError(f"模型 {model_id} 的 sources 配置非法")
            for task in spec.get("tasks", []):
                if task not in tasks:
                    raise ValueError(f"模型 {model_id} 引用了未知能力 {task}")
        for task, meta in tasks.items():
            default_id = meta.get("default")
            if default_id not in self._models or task not in self._models[default_id].get("tasks", []):
                raise ValueError(f"能力 {task} 的默认模型无效：{default_id}")

    def _load_selections(self) -> dict[str, str]:
        legacy_map = {
            "face": {"buffalo_l": "face-buffalo-l", "buffalo_s": "face-buffalo-s"},
            "ocr": {"mobile": "ocr-ppocrv5-mobile", "server": "ocr-ppocrv5-server"},
            "embedding": {"clip-ViT-B-32": "embedding-clip-vit-b32"},
            # Older versions incorrectly used classification for CLIP.
            "classification": {"clip-ViT-B-32": "photo-classification-v1"},
            "llm": {"MiniCPM-V-4_6-Q4_K_M": "llm-minicpm-v-4.6"},
        }
        disk: dict[str, Any] = {}
        try:
            source = self.config_path if self.config_path.exists() else self.legacy_config_path
            if source.exists():
                disk = self._load_json(source)
        except Exception as error:
            logger.warning("Ignoring invalid AI model config %s: %s", self.config_path, error)

        stored = disk.get("selections", {})
        legacy = disk.get("models", {})
        selections: dict[str, str] = {}
        for task, task_meta in self._catalog.get("tasks", {}).items():
            value = stored.get(task)
            if not value and task in legacy:
                value = legacy[task].get("selected")
                value = legacy_map.get(task, {}).get(value, value)
            if value not in self._models or task not in self._models[value].get("tasks", []):
                value = task_meta["default"]
            selections[task] = value
        self._save_selections(selections)
        return selections

    def _save_selections(self, selections: dict[str, str] | None = None) -> None:
        selections = selections or self._selections
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(f"{self.config_path.suffix}.tmp")
        payload = {"version": 1, "selections": selections}
        with temp_path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
        temp_path.replace(self.config_path)

    def get_spec(self, model_id: str) -> dict[str, Any]:
        try:
            return self._models[model_id]
        except KeyError as error:
            raise KeyError(f"未知模型：{model_id}") from error

    def get_selected_id(self, task: str) -> str:
        try:
            return self._selections[task]
        except KeyError as error:
            raise ValueError(f"未知 AI 能力：{task}") from error

    def get_selected_spec(self, task: str) -> dict[str, Any]:
        return self.get_spec(self.get_selected_id(task))

    def get_model_selection(self, task: str) -> str:
        """Compatibility-friendly runtime name for loaders; ids stay API-facing."""
        return self.get_selected_spec(task)["runtimeName"]

    def _resolve_model_id(self, value: str) -> str:
        if value in self._models:
            return value
        if value in self._selections:
            return self.get_selected_id(value)
        for task, meta in self._catalog.get("tasks", {}).items():
            if value in meta.get("runtimeKeys", []):
                return self.get_selected_id(task)
        raise KeyError(f"未知模型或能力：{value}")

    def get_model_dir(self, model_or_task: str, *, task: bool = False) -> Path:
        spec = self.get_selected_spec(model_or_task) if task else self.get_spec(model_or_task)
        path = (self.model_root / spec["localDir"]).resolve()
        if path != self.model_root and self.model_root not in path.parents:
            raise ValueError(f"模型目录越界：{spec['localDir']}")
        return path

    def get_model_file(self, task: str, relative_path: str) -> Path:
        path = (self.get_model_dir(task, task=True) / relative_path).resolve()
        if self.model_root not in path.parents:
            raise ValueError(f"模型文件路径越界：{relative_path}")
        return path

    def is_ready(self, model_or_task: str, *, task: bool = False) -> bool:
        model_id = self.get_selected_id(model_or_task) if task else self._resolve_model_id(model_or_task)
        spec = self.get_spec(model_id)
        base = self.get_model_dir(model_id)
        required = spec.get("requiredFiles", [])
        return base.is_dir() and bool(required) and all((base / item).is_file() for item in required)

    def require_ready(self, task: str) -> dict[str, Any]:
        model_id = self.get_selected_id(task)
        if not self.is_ready(model_id):
            status = self._status.get(model_id, "pending")
            raise RuntimeError(f"{self.get_spec(model_id)['name']} 尚未就绪（{status}），请在 AI 模型管理中下载")
        return self.get_selected_spec(task)

    def refresh_statuses(self) -> None:
        with self._lock:
            for model_id in self._models:
                if self._status.get(model_id) == "downloading":
                    continue
                ready = self.is_ready(model_id)
                if ready:
                    self._status[model_id] = "ready"
                    self._errors[model_id] = None
                elif self._status.get(model_id) != "failed":
                    self._status[model_id] = "pending"

    def list_models(self) -> dict[str, Any]:
        self.refresh_statuses()
        with self._lock:
            selections = dict(self._selections)
            items = []
            for model_id, spec in self._models.items():
                item = copy.deepcopy(spec)
                item.update(
                    status=self._status.get(model_id, "pending"),
                    error=self._errors.get(model_id),
                    selectedTasks=[task for task, selected in selections.items() if selected == model_id],
                    source="ModelScope",
                    canDelete=self.is_ready(model_id),
                )
                items.append(item)
            task_items = {}
            for task, meta in self._catalog.get("tasks", {}).items():
                task_items[task] = {
                    "name": meta["name"],
                    "selected": selections[task],
                    "available": [
                        model_id for model_id, spec in self._models.items()
                        if task in spec.get("tasks", [])
                    ],
                }
            return {"models": items, "tasks": task_items, "catalogVersion": self._catalog.get("version", 1)}

    def _download_snapshot(self, repo_id: str, target: Path, source: dict[str, Any]) -> None:
        from modelscope.hub.snapshot_download import snapshot_download

        target.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {"local_dir": str(target)}
        revision = source.get("revision")
        patterns = source.get("allowPatterns")
        if revision:
            kwargs["revision"] = revision
        if patterns:
            kwargs["allow_patterns"] = patterns
        snapshot_download(repo_id, **kwargs)

    def _download(self, model_id: str) -> None:
        spec = self.get_spec(model_id)
        base = self.get_model_dir(model_id)
        with self._download_lock:
            try:
                if self.is_ready(model_id):
                    with self._lock:
                        self._status[model_id] = "ready"
                        self._errors[model_id] = None
                    return
                with self._lock:
                    self._status[model_id] = "downloading"
                    self._errors[model_id] = None
                sources = spec.get("sources") or [spec]
                for source in sources:
                    repo_id = source.get("repoId")
                    if not repo_id:
                        raise RuntimeError("模型目录缺少 ModelScope repoId")
                    target = base / source.get("localSubdir", "")
                    target.mkdir(parents=True, exist_ok=True)
                    merged = {**spec, **source}
                    logger.info("Downloading ModelScope model %s to %s", repo_id, target)
                    self._download_snapshot(repo_id, target, merged)
                if not self.is_ready(model_id):
                    missing = [item for item in spec.get("requiredFiles", []) if not (base / item).is_file()]
                    raise RuntimeError(f"下载完成但缺少必要文件：{', '.join(missing)}")
                with self._lock:
                    self._status[model_id] = "ready"
                    self._errors[model_id] = None
            except Exception as error:
                logger.exception("Model download failed: %s", model_id)
                with self._lock:
                    self._status[model_id] = "failed"
                    self._errors[model_id] = str(error)

    def trigger_download(self, model_id: str) -> None:
        spec = self.get_spec(model_id)
        if not spec.get("available", True):
            raise ValueError("该候选模型的 ModelScope 仓库尚未发布")
        with self._lock:
            if self._status.get(model_id) == "downloading":
                return
            self._status[model_id] = "downloading"
            self._errors[model_id] = None
        threading.Thread(target=self._download, args=(model_id,), daemon=True).start()

    def prepare_model(self, task: str) -> Path:
        """Synchronously make the selected model available for a build/runtime.

        The service normally downloads models in the background so the API can
        start immediately.  Desktop packaging needs the selected assets before
        it freezes the sidecar, therefore it uses this explicit synchronous
        preparation hook while retaining the same catalog and ModelScope path.
        """
        model_id = self.get_selected_id(task)
        spec = self.get_spec(model_id)
        if not spec.get("available", True):
            raise ValueError("该候选模型的 ModelScope 仓库尚未发布")
        if not self.is_ready(model_id):
            self._download(model_id)
        if not self.is_ready(model_id):
            error = self._errors.get(model_id) or "模型下载失败"
            raise RuntimeError(error)
        return self.get_model_dir(model_id)

    def start_selected_downloads(self) -> None:
        """Download only selected models, sequentially, instead of every candidate."""
        model_ids = list(dict.fromkeys(self._selections.values()))

        def worker() -> None:
            for model_id in model_ids:
                spec = self.get_spec(model_id)
                if spec.get("available", True) and spec.get("autoDownload", True) and not self.is_ready(model_id):
                    self._download(model_id)

        threading.Thread(target=worker, daemon=True).start()

    def release_task(self, task: str) -> None:
        task_meta = self._catalog.get("tasks", {}).get(task)
        if not task_meta:
            raise ValueError(f"未知 AI 能力：{task}")
        for key in task_meta.get("runtimeKeys", []):
            wrapper = runtime_model_manager.models.get(key)
            if wrapper:
                wrapper.release()
        # Category classifiers are registered dynamically.
        if task == "classification":
            for key, wrapper in list(runtime_model_manager.models.items()):
                if key.startswith("yolo_photo_cls_"):
                    wrapper.release()

    def select_model(self, task: str, model_id: str) -> bool:
        spec = self.get_spec(model_id)
        if task not in self._catalog.get("tasks", {}):
            raise ValueError(f"未知 AI 能力：{task}")
        if task not in spec.get("tasks", []):
            raise ValueError(f"模型 {model_id} 不支持 {task}")
        if not spec.get("available", True):
            raise ValueError("该候选模型的 ModelScope 仓库尚未发布")
        with self._lock:
            if self._selections.get(task) == model_id:
                return False
            self.release_task(task)
            self._selections[task] = model_id
            self._save_selections()
        if not self.is_ready(model_id):
            self.trigger_download(model_id)
        return True

    def delete_model(self, model_id: str) -> None:
        self.get_spec(model_id)
        with self._lock:
            if self._status.get(model_id) == "downloading":
                raise RuntimeError("模型正在下载，暂时无法删除")
        for task, selected in self._selections.items():
            if selected == model_id:
                self.release_task(task)
        shutil.rmtree(self.get_model_dir(model_id), ignore_errors=True)
        with self._lock:
            self._status[model_id] = "pending"
            self._errors[model_id] = None


ai_model_manager = UnifiedModelManager()
