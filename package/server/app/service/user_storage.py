"""Per-user on-disk layout and legacy storage migration helpers."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from app.core.paths import DATA_DIR


logger = logging.getLogger(__name__)
DEFAULT_STORAGE_BASE = os.path.join(DATA_DIR, "uploads")
_STORAGE_BASE_CACHE: dict[str, str] = {}


def _user_key(user_id: UUID | str) -> str:
    return str(user_id)


def configured_storage_base(settings: Optional[dict[str, Any]]) -> str:
    value = ((settings or {}).get("storage") or {}).get("photo_storage_path")
    if not isinstance(value, str):
        value = None
    elif value.replace("\\", "/").rstrip("/") in ("./data/uploads", "data/uploads"):
        # The historic default was relative to the server working directory.
        # Anchor it to DATA_DIR so desktop and container launches migrate alike.
        value = DEFAULT_STORAGE_BASE
    return os.path.abspath(os.path.expanduser(value or DEFAULT_STORAGE_BASE))


def cache_storage_base(user_id: UUID | str, storage_base: str) -> str:
    base = os.path.abspath(os.path.expanduser(storage_base or DEFAULT_STORAGE_BASE))
    _STORAGE_BASE_CACHE[_user_key(user_id)] = base
    return base


def get_cached_storage_base(user_id: UUID | str) -> Optional[str]:
    return _STORAGE_BASE_CACHE.get(_user_key(user_id))


def get_user_root(user_id: UUID | str, storage_base: str) -> str:
    return os.path.join(os.path.abspath(storage_base), "users", _user_key(user_id))


def ensure_user_layout(user_id: UUID | str, storage_base: str) -> str:
    root = get_user_root(user_id, storage_base)
    for name in ("uploads", "thumbnails", "chunks", "config"):
        Path(root, name).mkdir(parents=True, exist_ok=True)
    return root


def write_user_config(user_id: UUID | str, settings: dict[str, Any]) -> str:
    """Mirror the DB-backed settings into the user's own data directory."""
    base = cache_storage_base(user_id, configured_storage_base(settings))
    root = ensure_user_layout(user_id, base)
    target = os.path.join(root, "config", "settings.json")
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, ensure_ascii=False, indent=2, default=str)
    os.replace(temporary, target)
    return target


def delete_user_layout(user_id: UUID | str, settings: Optional[dict[str, Any]]) -> None:
    base = configured_storage_base(settings)
    root = get_user_root(user_id, base)
    if os.path.isdir(root):
        shutil.rmtree(root)
    _STORAGE_BASE_CACHE.pop(_user_key(user_id), None)


def _is_below(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(path), os.path.abspath(parent))) == os.path.abspath(parent)
    except (OSError, ValueError):
        return False


def _move_file(source: str, target: str, preserve_conflict: bool = False) -> Optional[str]:
    if os.path.abspath(source) == os.path.abspath(target):
        return target if os.path.exists(target) else None
    if not os.path.exists(source):
        return target if os.path.exists(target) else None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        if os.path.getsize(source) == os.path.getsize(target):
            os.remove(source)
        elif preserve_conflict:
            stem, extension = os.path.splitext(target)
            index = 1
            migrated_target = f"{stem}-migrated-{index}{extension}"
            while os.path.exists(migrated_target):
                index += 1
                migrated_target = f"{stem}-migrated-{index}{extension}"
            shutil.move(source, migrated_target)
            return migrated_target
        else:
            logger.warning("Storage migration discarded an obsolete thumbnail because its target already exists: %s", source)
            os.remove(source)
    else:
        shutil.move(source, target)
    return target


def _move_live_photo_companions(source: str, target: str) -> None:
    source_stem, source_ext = os.path.splitext(source)
    target_stem, _ = os.path.splitext(target)
    candidates = (".mov", ".MOV") if source_ext.lower() in (".heic", ".heif") else (".mp4", ".mov", ".MOV")
    for extension in candidates:
        companion = source_stem + extension
        if os.path.exists(companion):
            _move_file(companion, target_stem + extension)


def migrate_legacy_user_storage(db) -> dict[str, int]:
    """Move the legacy mixed layout into isolated user directories.

    This is idempotent and only moves originals below the configured legacy
    ``uploads`` directory. External scan directories are never touched.
    """
    from app.db.models.photo import Photo
    from app.db.models.user import User
    from app.core.config_manager import config_manager

    migrated_photos = 0
    migrated_thumbnails = 0
    users = db.query(User).all()
    for user in users:
        settings = dict(user.settings or {})
        base = cache_storage_base(user.id, configured_storage_base(settings))
        user_root = ensure_user_layout(user.id, base)
        legacy_uploads = os.path.join(base, "uploads")
        new_uploads = os.path.join(user_root, "uploads")
        legacy_thumbnails = os.path.join(base, "thumbnails")
        new_thumbnails = os.path.join(user_root, "thumbnails")

        photos = db.query(Photo).filter(Photo.owner_id == user.id).all()
        for photo in photos:
            source = photo.file_path
            if source and _is_below(source, legacy_uploads) and not _is_below(source, new_uploads):
                relative = os.path.relpath(os.path.abspath(source), os.path.abspath(legacy_uploads))
                target = os.path.join(new_uploads, relative)
                migrated_path = _move_file(source, target, preserve_conflict=True)
                if migrated_path:
                    _move_live_photo_companions(source, migrated_path)
                    photo.file_path = migrated_path
                    migrated_photos += 1

            compact = str(photo.id).replace("-", "")
            p1, p2 = compact[:2], compact[2:4]
            old_dir = os.path.join(legacy_thumbnails, p1, p2)
            new_dir = os.path.join(new_thumbnails, p1, p2)
            for suffix in (".webp", "-thumb.webp", ".jpg", "-thumb.jpg", ".mp4"):
                if _move_file(os.path.join(old_dir, compact + suffix), os.path.join(new_dir, compact + suffix)):
                    migrated_thumbnails += 1

        write_user_config(user.id, config_manager.merge_user_settings(settings).model_dump())

    # Transaction ownership belongs to the caller.  In particular, the
    # Alembic data migration must only advance its revision after both the
    # filesystem work and these path updates complete successfully.
    return {"photos": migrated_photos, "thumbnails": migrated_thumbnails, "users": len(users)}
