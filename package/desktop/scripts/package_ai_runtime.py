"""Build versioned AI sidecar archives and a catalog from Tauri-signed ZIPs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import uuid


def package_runtime(source: Path, output: Path) -> Path:
    meta = json.loads((source / "runtime-version.json").read_text(encoding="utf-8"))
    if (meta.get("schemaVersion") != 1 or meta.get("backend") not in {"cuda", "openvino"}
            or meta.get("platform") != "windows-x86_64"
            or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", meta.get("version", ""))
            or not (source / "trailsnap-ai.exe").is_file()):
        raise ValueError("Invalid Windows x64 accelerator runtime")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"TrailSnap-{meta['version']}-ai-{meta['backend']}-windows-x64.zip"
    if archive.exists():
        raise FileExistsError(archive)
    temporary = output / f".{archive.name}.{uuid.uuid4()}.tmp"
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    raise ValueError(f"Runtime cannot contain symlinks: {path}")
                if path.is_file():
                    bundle.write(path, path.relative_to(source).as_posix())
        temporary.rename(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def catalog(directory: Path, version: str) -> dict:
    packages = {}
    for backend in ("cuda", "openvino"):
        filename = f"TrailSnap-{version}-ai-{backend}-windows-x64.zip"
        archive = directory / filename
        signature = archive.with_suffix(".zip.sig").read_text(encoding="utf-8").strip()
        if not signature:
            raise ValueError(f"Missing signature: {filename}")
        with zipfile.ZipFile(archive) as bundle:
            meta = json.loads(bundle.read("runtime-version.json"))
        if meta != {"schemaVersion": 1, "version": version, "backend": backend, "platform": "windows-x86_64"}:
            raise ValueError(f"Runtime metadata does not match release: {filename}")
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        packages[backend] = {**meta, "filename": filename, "size": archive.stat().st_size,
                             "sha256": digest, "signature": signature}
    return {"schemaVersion": 1, "packages": packages}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--source", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    manifest = sub.add_parser("catalog")
    manifest.add_argument("--directory", type=Path, required=True)
    manifest.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "pack":
        print(package_runtime(args.source, args.output))
    else:
        (args.directory / "ai-runtimes.json").write_text(
            json.dumps(catalog(args.directory, args.version), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
