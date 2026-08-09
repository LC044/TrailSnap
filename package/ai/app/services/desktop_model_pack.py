"""Downloadable model-pack support for the desktop AI runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from app.config import settings
from app.services.model_downloader import model_downloader


MODEL_ID = "desktop-core-models"
MODEL_VERSION = "0.9.2"
MARKER_NAME = ".desktop-core-models.json"
CATALOG_PATH = Path(__file__).resolve().parents[1] / "desktop_model_catalog.json"
REQUIRED_FILES = (
    "photo-cls/photo-cls-general.onnx",
    "photo-cls/ticket-recognition.onnx",
    "ocr/ch_PP-OCRv5_mobile_det.onnx",
    "ocr/ch_PP-OCRv5_rec_mobile_infer.onnx",
    "ocr/ch_ppocr_mobile_v2.0_cls_infer.onnx",
    "ocr/ppocrv5_dict.txt",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_url(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "TrailSnap-Desktop-AI/0.9.2"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _embedded_entry() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    entry = next((item for item in catalog.get("models", []) if item.get("id") == MODEL_ID), None)
    if not entry:
        raise RuntimeError("模型清单中缺少桌面 AI 基础模型")
    return entry


def _catalog_entry() -> dict:
    catalog = {"models": [_embedded_entry()]}
    catalog_url = os.environ.get("TS_AI_MODEL_CATALOG_URL", "").strip()
    if catalog_url:
        try:
            remote = _read_json_url(catalog_url)
            if isinstance(remote.get("models"), list):
                catalog = remote
        except Exception:
            # The embedded entry keeps the management UI usable offline; a
            # download attempt below reports that no published asset exists.
            pass
    entry = next((item for item in catalog.get("models", []) if item.get("id") == MODEL_ID), None)
    if not entry:
        raise RuntimeError("模型清单中缺少桌面 AI 基础模型")
    return entry


def _is_installed() -> bool:
    base = Path(settings.MODEL_PATH)
    marker = base / MARKER_NAME
    if not marker.is_file():
        return False
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return state.get("version") == MODEL_VERSION and all((base / item).is_file() for item in REQUIRED_FILES)


def _safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"模型包包含不安全路径：{member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"模型包不允许符号链接：{member.name}")
        bundle.extractall(destination, filter="data")


def _download() -> str:
    entry = _catalog_entry()
    asset = entry.get("asset") or {}
    url = asset.get("url")
    expected = str(asset.get("sha256") or "").lower()
    if not url or len(expected) != 64:
        raise RuntimeError("当前版本尚未发布可下载的模型包，请刷新模型清单后重试")

    base = Path(settings.MODEL_PATH).resolve()
    downloads = base / ".downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f"{MODEL_ID}-{MODEL_VERSION}.tar.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "TrailSnap-Desktop-AI/0.9.2"})
    with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if _sha256(archive).lower() != expected:
        archive.unlink(missing_ok=True)
        raise RuntimeError("模型包 SHA-256 校验失败")

    temp = Path(tempfile.mkdtemp(prefix=".model-install-", dir=base))
    try:
        _safe_extract(archive, temp)
        if not all((temp / item).is_file() for item in REQUIRED_FILES):
            raise RuntimeError("模型包内容不完整")
        for name in ("photo-cls", "ocr"):
            source = temp / name
            target = base / name
            if target.exists():
                shutil.rmtree(target)
            source.replace(target)
        (base / MARKER_NAME).write_text(
            json.dumps({"id": MODEL_ID, "version": MODEL_VERSION}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        archive.unlink(missing_ok=True)
    return str(base)


def _delete() -> None:
    base = Path(settings.MODEL_PATH).resolve()
    for name in ("photo-cls", "ocr"):
        shutil.rmtree(base / name, ignore_errors=True)
    (base / MARKER_NAME).unlink(missing_ok=True)


def register_desktop_model_pack() -> None:
    entry = _embedded_entry()
    asset = entry.get("asset") or {}
    model_downloader.register_model(
        MODEL_ID,
        _is_installed,
        _download,
        delete_fn=_delete,
        metadata={
            "name": entry.get("name", "桌面 AI 基础模型"),
            "version": entry.get("version", MODEL_VERSION),
            "description": entry.get("description", ""),
            "capabilities": entry.get("capabilities", []),
            "requirements": entry.get("requirements", {}),
            "downloadSize": asset.get("size"),
            "available": bool(asset.get("url") and asset.get("sha256")),
        },
        managed=True,
    )
