"""Explicit Win32 extended paths for CopyFile2/copytree, including UNC shares."""
import os
import time
from pathlib import Path


def filesystem_path(path: Path) -> str:
    value = str(path.absolute())
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def publish_directory(source: Path, target: Path) -> None:
    """Publish atomically, allowing Win32 scanners to release copied binaries."""
    deadline = time.monotonic() + 15
    while True:
        try:
            source.rename(target)
            return
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(.1)
