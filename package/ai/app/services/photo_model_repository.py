"""Shared ModelScope download lifecycle for desktop photo/ticket models."""

from __future__ import annotations

import shutil
import threading
import hashlib
import urllib.request
from pathlib import Path

from app.config import settings


MODEL_ID = "yolo_photo_cls_general"
MODEL_REVISION = "v0.3.10.1"
MODEL_BASE_URL = f"https://www.modelscope.cn/models/SiYuan044/photo-cls/resolve/{MODEL_REVISION}"
MODEL_ASSETS = {
    "photo-cls-animal.onnx": "439e40c0a3bfd85025212345b857a46c365818e736691d3c0184666abec2f0bf",
    "photo-cls-document.onnx": "de29149605b131dabd8b34d6983cb6279e9d636b69cbe8f8dead52051cbec9ee",
    "photo-cls-general.onnx": "555850f91dc8334ad628b1d866387609d5849665858bae37a81ca61bf0ce07db",
    "photo-cls-person.onnx": "385c4513243e68ae749cf18214464d4140ef005d185f69e46bfd88ccb95ed38a",
    "photo-cls-scenery.onnx": "28c5ef9ec9ceddd8434bee58fa7f6accf5a241ed2c6570197a89bf69d291e049",
    "ticket-recognition.onnx": "54c98d45e21206a235abb540a130eabf914c71be4256e51906ca79226c88053a",
}
REQUIRED_FILES = tuple(MODEL_ASSETS)
MARKER_NAME = ".trailsnap-model-revision"
_download_lock = threading.Lock()


def model_directory() -> Path:
    return Path(settings.MODEL_PATH) / "photo-cls"


def models_ready() -> bool:
    base = model_directory()
    marker = base / MARKER_NAME
    return (
        marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == MODEL_REVISION
        and all((base / filename).is_file() for filename in REQUIRED_FILES)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_asset(filename: str, expected_sha256: str, destination: Path) -> None:
    partial = destination.with_suffix(f"{destination.suffix}.part")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(
        f"{MODEL_BASE_URL}/{filename}",
        headers={"User-Agent": "TrailSnap-Desktop-AI/0.10.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual = _sha256(partial)
        if actual != expected_sha256:
            raise RuntimeError(f"ModelScope 模型 SHA-256 校验失败：{filename}")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def ensure_models() -> str:
    """Download the shared snapshot once, even when several services start together."""
    with _download_lock:
        if models_ready():
            return str(model_directory())
        base = model_directory()
        base.mkdir(parents=True, exist_ok=True)
        for filename, expected_sha256 in MODEL_ASSETS.items():
            destination = base / filename
            if destination.is_file() and _sha256(destination) == expected_sha256:
                continue
            _download_asset(filename, expected_sha256, destination)
        (base / MARKER_NAME).write_text(MODEL_REVISION, encoding="utf-8")
        if not models_ready():
            raise RuntimeError("ModelScope 模型下载完成，但必要的模型文件不完整")
        return str(base)


def delete_models() -> None:
    shutil.rmtree(model_directory(), ignore_errors=True)


MANAGED_METADATA = {
    "name": "图片分类与票据识别模型",
    "version": MODEL_REVISION,
    "description": "运行时从 ModelScope 下载，用于图片分类、火车票和机票识别。",
    "capabilities": ["tickets", "classification"],
    "task": "classification",
    "requirements": {"diskMB": 130},
    "downloadSize": 110 * 1024 * 1024,
    "source": "ModelScope",
    "available": True,
}
