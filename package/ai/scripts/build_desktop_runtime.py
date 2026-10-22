"""Build the optional AI sidecar with PyInstaller (one-dir mode)."""

from __future__ import annotations

import json
import tomllib
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = root / "desktop_ai.spec"
    output = root / "dist" / "trailsnap-ai"

    # Remove any prior bundle so stale files never leak into the new build.
    shutil.rmtree(output, ignore_errors=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec),
    ]
    subprocess.run(command, cwd=root, check=True)

    if not output.is_dir():
        raise RuntimeError(f"PyInstaller output not found: {output}")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    (output / "runtime-version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
