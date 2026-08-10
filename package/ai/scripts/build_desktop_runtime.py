"""Build the optional AI sidecar with Nuitka standalone mode."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build_root = root / "dist" / "nuitka-ai"
    target = root / "dist" / "trailsnap-ai"
    shutil.rmtree(build_root, ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        f"--output-dir={build_root}",
        "--output-filename=trailsnap-ai",
        "--include-package=rapidocr",
        "--include-package=uvicorn",
        "--include-data-dir=app/data=app/data",
        "--nofollow-import-to=tkinter,pytest,insightface,torch,transformers,modelscope,matplotlib,pandas,scipy,skimage,sklearn",
        "--report=dist/nuitka-ai-report.xml",
        "desktop_entry.py",
    ]
    subprocess.run(command, cwd=root, check=True)
    produced = build_root / "desktop_entry.dist"
    if not produced.is_dir():
        raise RuntimeError(f"Nuitka output not found: {produced}")
    resolved_root = (root / "dist").resolve()
    if resolved_root not in target.resolve().parents:
        raise RuntimeError(f"refusing to replace path outside {resolved_root}: {target}")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(produced, target)
    print(target)


if __name__ == "__main__":
    main()
