"""Panorama derivatives use their own cache and never rewrite the source image."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.service.disk_budget import budgeted_open
from app.service.storage import _get_storage_root
from app.utils.image_loading import Image
from app.utils.panorama import parse_gpano, validate_geometry


def detect_file(path: str) -> dict | None:
    with budgeted_open(path) as source, Image.open(source) as image:
        return parse_gpano(image.info.get("xmp") or image.info.get("XML:com.adobe.xmp"), image.width, image.height, image.getexif().get(274, 1))


def derivative(photo, high: bool = False) -> tuple[str, int, int]:
    geometry = photo.panorama_metadata
    scale = 1 if high else min(1, 4096 / geometry["fullWidth"])
    width = max(1, round(geometry["croppedWidth"] * scale))
    height = max(1, round(geometry["croppedHeight"] * scale))
    edge = geometry["fullWidth"] if high else 4096
    stat = os.stat(photo.file_path)
    key = hashlib.sha256(json.dumps([stat.st_mtime_ns, stat.st_size, geometry, edge]).encode()).hexdigest()[:16]
    compact = photo.id.hex
    base = Path(_get_storage_root(photo.owner_id)) / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{compact}-pano-{key}.jpg"
    if not target.is_file():
        with budgeted_open(photo.file_path) as source, Image.open(source) as image:
            if image.getexif().get(274, 1) != 1:
                raise ValueError("请先将图片方向归一化后再设置全景")
            validate_geometry(geometry, image.width, image.height)
            image.draft("RGB", (width, height))
            with image.convert("RGB") as rgb:
                rgb = rgb.resize((width, height), Image.Resampling.LANCZOS)
                fd, temporary = tempfile.mkstemp(dir=base, suffix=".jpg")
                os.close(fd)
                try:
                    rgb.save(temporary, "JPEG", quality=90)
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.remove(temporary)
                rgb.close()
    return str(target), width, height
