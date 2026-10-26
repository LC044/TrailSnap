"""Unit tests for ``app/services/unified_model_manager.py`` catalog validation.

The 2026-10-22 coverage scan showed the module at 83.1% (61 missed of 362).
Almost every miss is a *catalog guard* in ``_validate_catalog`` plus the
lookup helpers that consume the validated catalog:

* ``_validate_catalog`` rejects models with missing name/runtimeName,
  missing ``requiredFiles``, missing ``repoId``/``sources``, escaping
  ``requiredFiles`` paths, malformed ``sources`` entries, references to
  unknown capabilities, incomplete OCR runtime blocks and a default model
  that does not actually serve the capability.
* ``get_spec`` / ``get_selected_id`` / ``_resolve_model_id`` translate
  unknown ids into the documented ``KeyError`` / ``ValueError``.
* ``get_model_dir`` / ``get_model_file`` refuse to escape the model root.
* ``require_ready`` refuses to hand out a model that is not downloaded.

None of these had direct tests, because the existing suites always build
a *valid* catalog and then exercise the happy paths.

Each test builds a deliberately broken catalog and asserts the exact
guard that must fire, so a future relaxation of the catalog format shows
up as a failing test instead of a silently accepted unsafe catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.unified_model_manager import UnifiedModelManager


pytestmark = pytest.mark.smoke


def _model(**overrides):
    spec = {
        "id": "demo",
        "tasks": ["face"],
        "name": "Demo",
        "runtimeName": "demo",
        "repoId": "owner/demo",
        "localDir": "demo",
        "requiredFiles": ["model.onnx"],
        "available": True,
    }
    spec.update(overrides)
    return spec


def _catalog(models=None, tasks=None):
    return {
        "version": 1,
        "tasks": tasks if tasks is not None else {
            "face": {"name": "Face", "default": "demo", "runtimeKeys": ["face"]},
        },
        "models": models if models is not None else [_model()],
    }


@pytest.fixture
def build_manager(tmp_path, monkeypatch):
    """Return a factory that instantiates a manager against a given catalog."""

    def _build(catalog, *, config_text=None, model_root=None):
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(catalog_path))
        config_path = tmp_path / "config.json"
        if config_text is not None:
            config_path.write_text(config_text, encoding="utf-8")
        monkeypatch.setenv("AI_CONFIG_PATH", str(config_path))
        monkeypatch.setattr(
            "app.services.unified_model_manager.settings.MODEL_PATH",
            str(model_root or (tmp_path / "models")),
        )
        return UnifiedModelManager()

    return _build


# ---------------------------------------------------------------------------
# _validate_catalog guards
# ---------------------------------------------------------------------------


def test_catalog_rejects_model_without_name(build_manager):
    catalog = _catalog(models=[_model(name="")])
    with pytest.raises(ValueError, match="缺少 name 或 runtimeName"):
        build_manager(catalog)


def test_catalog_rejects_model_without_runtime_name(build_manager):
    catalog = _catalog(models=[_model(runtimeName="")])
    with pytest.raises(ValueError, match="缺少 name 或 runtimeName"):
        build_manager(catalog)


def test_catalog_rejects_model_without_required_files(build_manager):
    catalog = _catalog(models=[_model(requiredFiles=[])])
    with pytest.raises(ValueError, match="必须声明 requiredFiles"):
        build_manager(catalog)


def test_catalog_rejects_model_without_repo_or_sources(build_manager):
    catalog = _catalog(models=[_model(repoId=None)])
    with pytest.raises(ValueError, match="缺少 ModelScope repoId"):
        build_manager(catalog)


def test_catalog_rejects_escaping_required_file_path(build_manager):
    catalog = _catalog(models=[_model(requiredFiles=["../outside/model.onnx"])])
    with pytest.raises(ValueError, match="requiredFiles 路径非法"):
        build_manager(catalog)


def test_catalog_rejects_absolute_required_file_path(build_manager):
    # ``Path.is_absolute`` is platform dependent (a POSIX-style "/etc/passwd"
    # is *not* absolute on Windows), so build the absolute path from the
    # current drive to keep the guard meaningful on every platform.
    absolute = str(Path.cwd() / "etc" / "passwd")
    catalog = _catalog(models=[_model(requiredFiles=[absolute])])
    with pytest.raises(ValueError, match="requiredFiles 路径非法"):
        build_manager(catalog)


def test_catalog_rejects_source_without_repo_id(build_manager):
    catalog = _catalog(models=[_model(repoId=None, sources=[{"localSubdir": "text"}])])
    with pytest.raises(ValueError, match="sources 配置非法"):
        build_manager(catalog)


def test_catalog_rejects_source_with_escaping_subdir(build_manager):
    catalog = _catalog(models=[_model(
        repoId=None,
        sources=[{"repoId": "owner/demo", "localSubdir": "../escape"}],
    )])
    with pytest.raises(ValueError, match="sources 配置非法"):
        build_manager(catalog)


def test_catalog_rejects_unknown_capability_reference(build_manager):
    catalog = _catalog(models=[_model(tasks=["face", "ghost"])])
    with pytest.raises(ValueError, match="引用了未知能力"):
        build_manager(catalog)


def test_catalog_rejects_ocr_model_without_runtime_block(build_manager):
    catalog = _catalog(
        models=[_model(tasks=["ocr"], runtime={})],
        tasks={"ocr": {"name": "OCR", "default": "demo", "runtimeKeys": ["ocr"]}},
    )
    with pytest.raises(ValueError, match="缺少 runtime 配置"):
        build_manager(catalog)


def test_catalog_rejects_ocr_model_whose_runtime_files_are_not_required(build_manager):
    runtime = {
        "ocrVersion": "PPOCRV6",
        "modelType": "TINY",
        "detFile": "det.onnx",
        "recFile": "rec.onnx",
        "clsFile": "cls.onnx",
        "clsOcrVersion": "PPOCRV4",
    }
    catalog = _catalog(
        models=[_model(
            tasks=["ocr"],
            requiredFiles=["model.onnx"],
            runtime=runtime,
        )],
        tasks={"ocr": {"name": "OCR", "default": "demo", "runtimeKeys": ["ocr"]}},
    )
    with pytest.raises(ValueError, match="运行文件未加入 requiredFiles"):
        build_manager(catalog)


def test_catalog_rejects_default_model_that_does_not_serve_the_capability(build_manager):
    # "face" defaults to a model that only serves "embedding".
    catalog = _catalog(
        models=[
            _model(id="demo", tasks=["face"]),
            _model(id="other", tasks=["embedding"], localDir="other"),
        ],
        tasks={
            "face": {"name": "Face", "default": "other", "runtimeKeys": ["face"]},
            "embedding": {"name": "Embedding", "default": "other", "runtimeKeys": ["emb"]},
        },
    )
    with pytest.raises(ValueError, match="默认模型无效"):
        build_manager(catalog)


# ---------------------------------------------------------------------------
# lookup helpers
# ---------------------------------------------------------------------------


def test_get_spec_reports_unknown_model(build_manager):
    manager = build_manager(_catalog())
    with pytest.raises(KeyError, match="未知模型"):
        manager.get_spec("nope")


def test_get_selected_id_reports_unknown_capability(build_manager):
    manager = build_manager(_catalog())
    with pytest.raises(ValueError, match="未知 AI 能力"):
        manager.get_selected_id("nope")


def test_resolve_model_id_accepts_runtime_key(build_manager):
    manager = build_manager(_catalog())
    # "face" is a runtimeKey of the only capability, so it resolves to the
    # model currently selected for that capability.
    assert manager._resolve_model_id("face") == "demo"


def test_resolve_model_id_reports_unknown_value(build_manager):
    manager = build_manager(_catalog())
    with pytest.raises(KeyError, match="未知模型或能力"):
        manager._resolve_model_id("not-a-model")


def test_get_model_dir_rejects_escaping_local_dir(build_manager, tmp_path):
    manager = build_manager(_catalog())
    manager._models["demo"]["localDir"] = "../outside"
    with pytest.raises(ValueError, match="模型目录越界"):
        manager.get_model_dir("demo")


def test_get_model_file_rejects_escaping_relative_path(build_manager):
    manager = build_manager(_catalog())
    with pytest.raises(ValueError, match="模型文件路径越界"):
        manager.get_model_file("face", "../../secret.txt")


def test_require_ready_refuses_when_model_is_missing(build_manager):
    manager = build_manager(_catalog())
    with pytest.raises(RuntimeError, match="尚未就绪"):
        manager.require_ready("face")


def test_require_ready_returns_spec_once_files_exist(build_manager):
    manager = build_manager(_catalog())
    model_dir = manager.get_model_dir("demo")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.onnx").write_bytes(b"onnx")

    spec = manager.require_ready("face")

    assert spec["id"] == "demo"


def test_broken_selection_file_is_ignored_and_defaults_reused(build_manager):
    """A corrupt on-disk selection file must not break startup."""
    manager = build_manager(_catalog(), config_text="{not json")
    assert manager.get_selected_id("face") == "demo"
