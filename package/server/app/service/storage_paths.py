"""Resolve portable paths at the filesystem boundary without changing legacy servers.

Docker/legacy records have NULL references and retain their existing path semantics.
The ORM's hybrid photo path exposes resolved paths to existing IO and SQL callers.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import UUID
from sqlalchemy import case, func, literal, select

_roots: dict[str, dict] = {}


def portable_enabled() -> bool:
    return os.getenv("TS_DESKTOP") == "1" and os.getenv("TS_DESKTOP_PORTABLE") == "1"


def instance_root() -> Path:
    raw = os.getenv("TS_DESKTOP_ROOT")
    if not raw:
        raise ValueError("Portable library root is not configured")
    return Path(raw).resolve()


def validate_relative(value: str, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Invalid relative storage path")
    normalized = value.replace("\\", "/")
    if PureWindowsPath(value).drive or normalized.startswith("/"):
        raise ValueError("Absolute storage path is not allowed")
    if allow_dot and normalized == ".":
        return "."
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("Storage path traversal is not allowed")
    return str(PurePosixPath(normalized))


def cache_root(root) -> None:
    _roots[str(root.id)] = {"id": str(root.id), "owner_id": str(root.owner_id),
                            "kind": root.kind, "location": root.location}


def warm_roots(db) -> None:
    from app.db.models.storage_root import StorageRoot
    _roots.clear()
    for root in db.query(StorageRoot).all():
        cache_root(root)


def root_path(root: dict) -> Path:
    if root["kind"] in {"managed", "instance-relative"}:
        anchor = instance_root()
        path = anchor / validate_relative(root["location"], allow_dot=True)
        resolved = path.resolve()
        if not resolved.is_relative_to(anchor):
            raise ValueError("Storage root escapes the library")
        return resolved
    if root["kind"] != "external" or not Path(root["location"]).is_absolute():
        raise ValueError("Invalid external storage root")
    return Path(root["location"]).resolve()


def resolve_path(owner_id, root_id, relative_path: str, db=None) -> Path:
    root = _roots.get(str(root_id))
    if root is None and db is not None:
        from app.db.models.storage_root import StorageRoot
        record = db.get(StorageRoot, UUID(str(root_id)))
        if record is not None:
            cache_root(record)
            root = _roots[str(root_id)]
    if root is None or root["owner_id"] != str(owner_id):
        raise ValueError("Storage root is missing or belongs to another user")
    anchor = root_path(root)
    candidate = (anchor / validate_relative(relative_path)).resolve()
    if not candidate.is_relative_to(anchor):
        raise ValueError("Storage path escapes its root")
    return candidate


def encode_path(owner_id, path: str):
    """Select the most specific owned root; return None for legacy/unregistered paths."""
    candidate = Path(path).resolve()
    matches = []
    for root in _roots.values():
        if root["owner_id"] != str(owner_id):
            continue
        anchor = root_path(root)
        if candidate.is_relative_to(anchor) and candidate != anchor:
            matches.append((len(str(anchor)), root, candidate.relative_to(anchor).as_posix()))
    if not matches:
        return None
    _, root, relative = max(matches, key=lambda item: item[0])
    return UUID(root["id"]), validate_relative(relative)


def apply_photo_reference(photo, db=None) -> None:
    if not portable_enabled():
        return
    if db is not None and not _roots:
        warm_roots(db)
    reference = encode_path(photo.owner_id, photo._file_path)
    if reference is None and db is not None:
        register_user_roots(db, photo.owner_id)
        reference = encode_path(photo.owner_id, photo._file_path)
    if reference is None:
        raise ValueError("Photo path has no owned storage root; register the folder first")
    photo.storage_root_id, photo.storage_relative_path = reference


def register_storage_root(db, owner_id, anchor: Path, name: str = "外部图库") -> None:
    """Register an explicitly selected destination before any file is moved there."""
    import json
    import uuid
    from sqlalchemy import insert
    from app.db.models.storage_root import StorageRoot
    root = instance_root()
    namespace = uuid.UUID(json.loads((root / "library.json").read_text(encoding="utf-8"))["libraryId"])
    anchor = anchor.resolve()
    kind = "managed" if anchor.is_relative_to(root) and anchor != root else "external"
    location = anchor.relative_to(root).as_posix() if kind == "managed" else str(anchor)
    root_id = uuid.uuid5(namespace, f"{owner_id}:{kind}:{location}")
    record = db.get(StorageRoot, root_id)
    if record is None:
        # Also called from before_flush, which cannot recursively flush.
        db.execute(insert(StorageRoot).values(id=root_id, owner_id=owner_id, name=name, kind=kind, location=location))
        record = StorageRoot(id=root_id, owner_id=owner_id, name=name, kind=kind, location=location)
    cache_root(record)


def register_user_roots(db, owner_id) -> None:
    from app.db.models.user import User
    from app.service.user_storage import configured_storage_base
    user = db.get(User, UUID(str(owner_id)))
    if user is None:
        raise ValueError("Storage owner does not exist")
    settings = user.settings or {}
    anchors = [(Path(configured_storage_base(settings)) / "users" / str(owner_id), "用户文件")]
    anchors.extend((Path(path), "外部图库") for path in (settings.get("storage") or {}).get("external_directories", []) if path)
    for anchor, name in anchors:
        register_storage_root(db, owner_id, anchor, name)


def photo_path_expression(photo):
    """A scalar SQL expression also covers scans, dedup and directory searches."""
    from app.db.models.storage_root import StorageRoot
    # Servers without portable mode retain their indexed legacy column fast path.
    if not portable_enabled():
        return photo._file_path
    base = str(instance_root()) + os.sep
    location = func.replace(StorageRoot.location, "/", os.sep)
    managed_location = case(
        (StorageRoot.location == ".", literal(str(instance_root()))),
        else_=literal(base) + location,
    )
    root_location = case(
        (StorageRoot.kind.in_(["managed", "instance-relative"]), managed_location),
        else_=location,
    )
    resolved = select(root_location + os.sep + func.replace(photo.storage_relative_path, "/", os.sep)).where(
        StorageRoot.id == photo.storage_root_id,
        StorageRoot.owner_id == photo.owner_id,
    ).correlate(photo).scalar_subquery()
    return case((photo.storage_root_id.is_not(None), resolved), else_=photo._file_path)
