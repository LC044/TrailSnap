import hashlib
import json
import os
import tempfile
from pathlib import Path

import psutil

from app.core.paths import DATA_DIR
from app.service.gallery_sync import contains_key


def directory_identity(path: str) -> tuple[int, int]:
    """Fingerprint a readable directory, including the filesystem it lives on."""
    with os.scandir(path):
        stat = os.stat(path)
    return stat.st_dev, stat.st_ino


def gallery_path_key(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def mount_inventory():
    inventory = {
        os.path.normcase(os.path.abspath(mount.mountpoint)): [mount.device, mount.fstype]
        for mount in psutil.disk_partitions(all=True)
    }
    if hasattr(os, "listvolumes"):
        # A Windows volume can be mounted at an NTFS directory without a drive letter.
        for volume in os.listvolumes():
            try:
                paths = os.listmounts(volume)
            except OSError:
                continue
            for path in paths:
                key = os.path.normcase(os.path.abspath(path))
                filesystem = inventory[key][1] if key in inventory else ""
                inventory[key] = [volume, filesystem]
    return inventory


def gallery_mounts(root, inventory):
    """Capture the mount containing the root and any independently mounted children."""
    root = gallery_path_key(root)
    parent = max((path for path in inventory if contains_key(path, root)), key=len, default=None)
    return {
        path: identity for path, identity in inventory.items()
        if path == parent or contains_key(root, path)
    }


def unavailable_mounts(root, expected, current):
    root_key = gallery_path_key(root)
    return {
        root_key if contains_key(path, root_key) else path
        for path, identity in expected.items() if current.get(path) != identity
    }


def gallery_state_path(owner_id, root):
    key = hashlib.sha256(f"{owner_id}\0{os.path.normcase(os.path.abspath(root))}".encode()).hexdigest()
    return Path(DATA_DIR) / "gallery-watch" / f"{key}.json"


def load_gallery_state(path):
    try:
        with path.open(encoding="utf-8") as source:
            state = json.load(source)
    except FileNotFoundError:
        return None
    if (not isinstance(state, dict) or not isinstance(state.get("identity"), list)
            or len(state["identity"]) != 2 or not isinstance(state.get("mounts"), dict)
            or not isinstance(state.get("unverified"), list)):
        raise ValueError(f"Invalid gallery watch state: {path}")
    return state


def save_gallery_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            json.dump(state, target, ensure_ascii=False)
            target.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
