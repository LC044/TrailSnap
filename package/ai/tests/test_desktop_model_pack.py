import io
import json
import tarfile

import pytest

from app.services import desktop_model_pack


pytestmark = [pytest.mark.smoke]


def test_installed_pack_requires_marker_and_every_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_model_pack.settings, "MODEL_PATH", str(tmp_path))
    for relative in desktop_model_pack.REQUIRED_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model")
    (tmp_path / desktop_model_pack.MARKER_NAME).write_text(
        json.dumps({"version": desktop_model_pack.MODEL_VERSION}), encoding="utf-8"
    )

    assert desktop_model_pack._is_installed()
    (tmp_path / desktop_model_pack.REQUIRED_FILES[0]).unlink()
    assert not desktop_model_pack._is_installed()


def test_model_archive_rejects_path_traversal(tmp_path):
    archive = tmp_path / "models.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("../escape.txt")
        payload = b"escape"
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))

    with pytest.raises(RuntimeError, match="不安全路径"):
        desktop_model_pack._safe_extract(archive, tmp_path / "extract")


def test_download_verifies_and_installs_model_pack(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    for relative in desktop_model_pack.REQUIRED_FILES:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode())

    archive = tmp_path / "models.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for child in source.iterdir():
            bundle.add(child, arcname=child.name)

    install_root = tmp_path / "installed"
    install_root.mkdir()
    monkeypatch.setattr(desktop_model_pack.settings, "MODEL_PATH", str(install_root))
    monkeypatch.setattr(
        desktop_model_pack,
        "_catalog_entry",
        lambda: {"asset": {"url": archive.as_uri(), "sha256": desktop_model_pack._sha256(archive)}},
    )

    assert desktop_model_pack._download() == str(install_root.resolve())
    assert desktop_model_pack._is_installed()
    assert not (install_root / ".downloads" / "desktop-core-models-0.9.2.tar.gz").exists()
