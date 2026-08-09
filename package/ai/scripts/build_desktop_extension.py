"""Assemble a versioned, checksummed TrailSnap desktop AI extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform-key", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("extension-dist"))
    parser.add_argument("--skip-model-download", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    runtime = root / "dist" / "trailsnap-ai"
    if not runtime.is_dir():
        raise SystemExit(f"PyInstaller runtime not found: {runtime}")

    model_dir = root / "extension-models" / "photo-cls"
    if not args.skip_model_download:
        from modelscope.hub.snapshot_download import snapshot_download

        snapshot_download(
            "SiYuan044/photo-cls",
            local_dir=str(model_dir),
            revision="v0.3.10.1",
        )

    args.output.mkdir(parents=True, exist_ok=True)
    staging = args.output / f"staging-{args.platform_key}"
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "runtime").mkdir(parents=True)
    shutil.copytree(runtime, staging / "runtime" / "trailsnap-ai")
    if model_dir.is_dir():
        shutil.copytree(model_dir, staging / "models" / "photo-cls")

    executable = "trailsnap-ai.exe" if args.platform_key.startswith("win32-") else "trailsnap-ai"
    manifest = {
        "schemaVersion": 1,
        "id": "core-ai",
        "name": "TrailSnap AI 基础扩展",
        "version": args.version,
        "platform": args.platform_key,
        "capabilities": ["ocr", "tickets", "classification"],
        "entrypoint": f"runtime/trailsnap-ai/{executable}",
        "modelPath": "models",
        "modelRevision": "v0.3.10.1",
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    archive = args.output / f"TrailSnap-AI-core-{args.platform_key}-{args.version}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for child in staging.iterdir():
            bundle.add(child, arcname=child.name)
    checksum = sha256(archive)
    asset = {
        "platform": args.platform_key,
        "url": f"https://github.com/LC044/TrailSnap/releases/download/v{args.version}/{archive.name}",
        "sha256": checksum,
        "size": archive.stat().st_size,
        "filename": archive.name,
    }
    (args.output / f"{args.platform_key}.asset.json").write_text(
        json.dumps(asset, indent=2), encoding="utf-8"
    )
    shutil.rmtree(staging)
    print(json.dumps(asset, indent=2))


if __name__ == "__main__":
    main()
