"""Build the desktop Server sidecar with Nuitka standalone mode."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _safe_replace(source: Path, target: Path, root: Path) -> None:
    root = root.resolve()
    target = target.resolve()
    if root not in target.parents:
        raise RuntimeError(f"refusing to replace path outside {root}: {target}")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build_root = root / "dist" / "nuitka-server"
    shutil.rmtree(build_root, ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        f"--output-dir={build_root}",
        "--output-filename=trailsnap-server",
        "--include-package=app",
        "--include-package=railway",
        "--include-package=uvicorn",
        "--include-package=passlib.handlers",
        "--include-package=sqlalchemy.dialects.postgresql",
        "--include-data-dir=resources=resources",
        "--nofollow-import-to=tkinter,pytest",
        "--report=dist/nuitka-server-report.xml",
        "desktop_entry.py",
    ]
    subprocess.run(command, cwd=root, check=True)
    produced = build_root / "desktop_entry.dist"
    if not produced.is_dir():
        raise RuntimeError(f"Nuitka output not found: {produced}")
    target = root / "dist" / "trailsnap-server"
    _safe_replace(produced, target, root / "dist")
    print(target)


if __name__ == "__main__":
    main()
