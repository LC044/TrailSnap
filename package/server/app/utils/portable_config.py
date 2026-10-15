"""Field-aware JSON path references. Disabled for Docker and legacy installs."""
from __future__ import annotations
import os
from pathlib import Path
from app.service.storage_paths import portable_enabled, instance_root, validate_relative

PREFIX = "ts-instance:/"
PATH_FIELDS = {"path", "file_path", "photo_storage_path", "storage_root", "model_path",
               "mmproj_path", "model_dir", "model_directory", "scan_roots", "external_directories",
               "target_dir", "target_path", "target_root_path", "live_photo_video_path",
               "output_path", "source_path", "folder_path", "directory"}


def remap_path_fields(value, mappings, *, key: str = ""):
    """Apply the longest copied-root mapping only to declared path fields."""
    if isinstance(value, dict):
        return {name: remap_path_fields(item, mappings, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [remap_path_fields(item, mappings, key=key) for item in value]
    if not isinstance(value, str) or key not in PATH_FIELDS:
        return value
    from app.utils.desktop_data_migration import rebase_value
    for source, target in sorted(mappings, key=lambda pair: len(str(pair[0])), reverse=True):
        rewritten = rebase_value(value, source, target)
        if rewritten != value:
            return rewritten
    return value


def transform_paths(value, *, encode: bool, key: str = "", root: Path | None = None):
    if root is None and not portable_enabled():
        return value
    if isinstance(value, dict):
        return {name: transform_paths(item, encode=encode, key=name, root=root) for name, item in value.items()}
    if isinstance(value, list):
        return [transform_paths(item, encode=encode, key=key, root=root) for item in value]
    if not isinstance(value, str) or key not in PATH_FIELDS:
        return value
    root = root.resolve() if root is not None else instance_root()
    if value.startswith(PREFIX):
        relative = validate_relative(value[len(PREFIX):], allow_dot=True)
        return value if encode else str(root / relative)
    if encode and Path(value).is_absolute():
        path = Path(value).resolve()
        if path.is_relative_to(root):
            return PREFIX + (path.relative_to(root).as_posix() or ".")
    return value
