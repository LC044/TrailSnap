"""Same-version Server/AI publication is validated before packaging."""
import copy
import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]
root = Path(__file__).resolve().parents[4]


def load(name):
    spec = importlib.util.spec_from_file_location(name, root / f"package/ai/scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load("merge_extension_catalog")
validator = load("validate_extension_release")


def assets(version):
    return {platform: {
        "url": f"https://github.com/LC044/TrailSnap/releases/download/v{version}/TrailSnap-AI-core-{platform}-{version}.tar.gz",
        "filename": f"TrailSnap-AI-core-{platform}-{version}.tar.gz", "sha256": "a" * 64, "size": 100,
    } for platform in module.PLATFORMS}


def test_publication_retains_legacy_format_with_exact_server_assets():
    metadata = {"extensions": [{"id": "core-ai", "version": "0.17.3", "name": "AI"}]}
    content = assets("0.17.4")
    result = module.merge_catalog(metadata, content, "0.17.4")
    assert result["schemaVersion"] == 1
    assert result["extensions"][0]["version"] == "0.17.4"
    assert result["extensions"][0]["assets"] == content
    assert metadata["extensions"][0]["version"] == "0.17.3"
    content["win32-x64"]["sha256"] = "b" * 64
    assert result["extensions"][0]["assets"]["win32-x64"]["sha256"] == "a" * 64


def test_publication_rejects_missing_platform_bad_hash_and_wrong_server_version():
    metadata = {"extensions": [{"id": "core-ai"}]}
    with pytest.raises(ValueError, match="Windows, Linux and macOS"):
        module.merge_catalog(metadata, {}, "0.17.3")
    invalid = assets("0.17.3")
    invalid["win32-x64"]["sha256"] = "bad"
    with pytest.raises(ValueError, match="SHA-256"):
        module.merge_catalog(metadata, invalid, "0.17.3")
    with pytest.raises(ValueError, match="match the Server"):
        module.merge_catalog(metadata, assets("0.17.2"), "0.17.3")


def test_release_validation_checks_actual_ai_and_server_versions():
    server, minimum = validator.validate_versions(root)
    assert tuple(map(int, minimum.split("."))) <= tuple(map(int, server.split(".")))
    with pytest.raises(ValueError, match="Release tag"):
        validator.validate_versions(root, "v999.0.0")


def test_release_validation_rejects_stale_ai_and_impossible_minimum(tmp_path):
    import shutil
    files = ["package/server/pyproject.toml", "package/ai/pyproject.toml", "package/server/app/core/config_manager.py",
             "package/desktop/src-tauri/Cargo.toml", "package/desktop/src-tauri/resources/ai-extensions.json",
             "package/ai/desktop_app.py", "package/server/app/service/ai_extension_state.py"]
    for relative in files:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    ai = tmp_path / "package/ai/pyproject.toml"
    server, _ = validator.validate_versions(tmp_path)
    original = ai.read_text(encoding="utf-8")
    ai.write_text(original.replace(f'version = "{server}"', 'version = "0.0.1"', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="AI project"):
        validator.validate_versions(tmp_path)
    ai.write_text(original, encoding="utf-8")
    state = tmp_path / "package/server/app/service/ai_extension_state.py"
    state.write_text('MINIMUM_AI_EXTENSION_VERSION = "999.0.0"', encoding="utf-8")
    with pytest.raises(ValueError, match="minimum version"):
        validator.validate_versions(tmp_path)
