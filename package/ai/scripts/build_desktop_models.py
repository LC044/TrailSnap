"""Build the platform-neutral model pack downloaded after runtime install."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tarfile
import tempfile
from pathlib import Path


MODEL_REVISION = "v0.3.10.1"
OCR_FILES = (
    "ch_PP-OCRv5_mobile_det.onnx",
    "ch_PP-OCRv5_rec_mobile_infer.onnx",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx",
    "ppocrv5_dict.txt",
)
PHOTO_FILES = (
    "photo-cls-general.onnx",
    "ticket-recognition.onnx",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("extension-dist"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    staging = args.output / "staging-models"
    shutil.rmtree(staging, ignore_errors=True)
    photo_models = staging / "photo-cls"
    ocr_models = staging / "ocr"
    photo_models.mkdir(parents=True)
    ocr_models.mkdir(parents=True)

    from modelscope.hub.snapshot_download import snapshot_download

    with tempfile.TemporaryDirectory(prefix="trailsnap-photo-models-") as source_dir:
        snapshot_download(
            "SiYuan044/photo-cls",
            local_dir=source_dir,
            revision=MODEL_REVISION,
            # ModelScope's parallel local-dir mover can race with virus scanners
            # on Windows and leave an ONNX file locked in ._____temp.
            max_workers=1,
            enable_file_lock=False,
        )
        for filename in PHOTO_FILES:
            source = Path(source_dir) / filename
            if not source.is_file():
                raise SystemExit(f"Photo classification model not found: {source}")
            shutil.copy2(source, photo_models / filename)

    rapidocr_spec = importlib.util.find_spec("rapidocr")
    if not rapidocr_spec or not rapidocr_spec.submodule_search_locations:
        raise SystemExit("rapidocr package not found")
    rapidocr_models = Path(next(iter(rapidocr_spec.submodule_search_locations))) / "models"
    for filename in OCR_FILES:
        source = rapidocr_models / filename
        if not source.is_file():
            raise SystemExit(f"RapidOCR model not found: {source}")
        shutil.copy2(source, ocr_models / filename)

    (staging / ".desktop-core-models.json").write_text(
        json.dumps({"id": "desktop-core-models", "version": args.version}, indent=2),
        encoding="utf-8",
    )
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f"TrailSnap-AI-models-core-{args.version}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for child in staging.iterdir():
            bundle.add(child, arcname=child.name)

    asset = {
        "id": "desktop-core-models",
        "version": args.version,
        "url": f"https://github.com/LC044/TrailSnap/releases/download/v{args.version}/{archive.name}",
        "sha256": sha256(archive),
        "size": archive.stat().st_size,
        "filename": archive.name,
    }
    (args.output / "models.asset.json").write_text(json.dumps(asset, indent=2), encoding="utf-8")
    shutil.rmtree(staging)
    print(json.dumps(asset, indent=2))


if __name__ == "__main__":
    main()
