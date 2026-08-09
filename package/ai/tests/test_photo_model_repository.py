import hashlib

import pytest

from app.services import photo_model_repository


pytestmark = [pytest.mark.smoke]


def test_ensure_models_downloads_modelscope_snapshot_once(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_model_repository.settings, "MODEL_PATH", str(tmp_path))
    calls = []
    payload = b"model"
    monkeypatch.setattr(
        photo_model_repository,
        "MODEL_ASSETS",
        {"model.onnx": hashlib.sha256(payload).hexdigest()},
    )
    monkeypatch.setattr(photo_model_repository, "REQUIRED_FILES", ("model.onnx",))

    def fake_download(filename, expected_sha256, destination):
        calls.append((filename, expected_sha256))
        destination.write_bytes(payload)

    monkeypatch.setattr(photo_model_repository, "_download_asset", fake_download)

    expected = str(tmp_path / "photo-cls")
    assert photo_model_repository.ensure_models() == expected
    assert photo_model_repository.ensure_models() == expected
    assert len(calls) == 1
    assert calls[0][0] == "model.onnx"


def test_delete_models_removes_downloaded_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_model_repository.settings, "MODEL_PATH", str(tmp_path))
    model_dir = tmp_path / "photo-cls"
    model_dir.mkdir()
    (model_dir / photo_model_repository.MARKER_NAME).write_text(
        photo_model_repository.MODEL_REVISION, encoding="utf-8"
    )
    for filename in photo_model_repository.REQUIRED_FILES:
        (model_dir / filename).write_bytes(b"model")

    assert photo_model_repository.models_ready()
    photo_model_repository.delete_models()
    assert not model_dir.exists()
    assert not photo_model_repository.models_ready()
