"""Build the optional AI sidecar with PyInstaller (one-dir mode)."""

from __future__ import annotations

import json
import os
import tomllib
import shutil
import subprocess
import sys
import platform
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = root / "desktop_ai.spec"
    build_backend = os.environ.get("TS_AI_BUILD_BACKEND", "cpu")
    if build_backend not in {"cpu", "cuda", "openvino"}:
        raise ValueError("Unsupported desktop AI backend")
    dist = root / "dist" if build_backend == "cpu" else root / "dist" / build_backend
    output = dist / "trailsnap-ai"

    # Remove any prior bundle so stale files never leak into the new build.
    shutil.rmtree(output, ignore_errors=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist),
        str(spec),
    ]
    subprocess.run(command, cwd=root, check=True)

    if not output.is_dir():
        raise RuntimeError(f"PyInstaller output not found: {output}")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    (output / "runtime-version.json").write_text(json.dumps({"schemaVersion": 1, "version": version,
        "backend": build_backend,
        "platform": "windows-x86_64" if sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64") else f"{sys.platform}-{platform.machine()}"}), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
