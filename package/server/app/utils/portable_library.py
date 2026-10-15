"""Offline portable-library metadata, conversion and recoverable snapshots.

This module intentionally uses only the standard library until schema preparation;
it can run from the frozen sidecar without loading the API or starting any writer.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid
from app.utils.windows_paths import filesystem_path


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def configuration_files(root: Path):
    return sorted({root / "library.json", root / "ai-config.json",
                   *root.glob("data/*config*.json"), *root.glob("data/data/*config*.json"),
                   *root.glob("data/users/*/config/*.json")})


def _library_id(root: Path):
    path = root / "library.json"
    return json.loads(path.read_text(encoding="utf-8")).get("libraryId") if path.is_file() else None


def _snapshot_matches(root: Path, manifest: dict) -> bool:
    if manifest["source"] == str(root):
        return True
    # A snapshot moves with its portable library. Never accept one belonging
    # to a different library merely because the directory layout is identical.
    return bool(manifest.get("libraryId") and manifest["libraryId"] == _library_id(root))


def snapshot_library(root: Path, destination: Path) -> None:
    root = root.resolve(strict=True)
    destination = destination.resolve()
    if destination == root or root.is_relative_to(destination):
        raise ValueError("Invalid snapshot destination")
    complete = destination / "snapshot.json"
    if complete.exists():
        if not _snapshot_matches(root, json.loads(complete.read_text(encoding="utf-8"))):
            raise ValueError("Snapshot belongs to another library")
        return
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for source in sorted({root / "data/trailsnap.sqlite", root / "data/railway.sqlite", *root.glob("data/*.sqlite"), *configuration_files(root)}):
        relative = source.relative_to(root).as_posix()
        target = destination / relative
        exists = source.is_file()
        if exists:
            if source.is_symlink():
                raise ValueError("Linked configuration cannot be snapshotted")
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".sqlite":
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
                    with closing(sqlite3.connect(target)) as backup:
                        db.backup(backup)
                        if backup.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                            raise ValueError(f"Invalid database: {source.name}")
            else:
                shutil.copy2(filesystem_path(source), filesystem_path(target))
            with target.open("r+b") as stream:
                os.fsync(stream.fileno())
        records.append({"path": relative, "existed": exists,
                        "sha256": file_hash(target) if exists else None})
    from app.utils.desktop_verification import media_baseline
    write_json(complete, {"schemaVersion": 1, "source": str(root), "libraryId": _library_id(root), "files": records,
                          "media": media_baseline(root)})


def file_hash(path: Path) -> str:
    with open(filesystem_path(path), "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restore_library(root: Path, snapshot: Path) -> None:
    root = root.resolve(strict=True)
    snapshot = snapshot.resolve(strict=True)
    manifest = json.loads((snapshot / "snapshot.json").read_text(encoding="utf-8"))
    if not _snapshot_matches(root, manifest):
        raise ValueError("Snapshot belongs to another library")
    # Verify the entire snapshot before restoring the first file.
    targets = []
    for record in manifest["files"]:
        relative = Path(record["path"])
        target, source = (root / relative).resolve(), (snapshot / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(root) or not source.is_relative_to(snapshot):
            raise ValueError("Snapshot path escapes its root")
        if record["existed"] and file_hash(source) != record["sha256"]:
            raise ValueError("Snapshot checksum mismatch")
        targets.append((record, source, target))
    for record, source, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix == ".sqlite":
            # No writer may be alive when calling this helper.
            for suffix in ("-wal", "-shm"):
                target.with_name(target.name + suffix).unlink(missing_ok=True)
        if record["existed"]:
            temporary = target.with_name(target.name + ".restore")
            shutil.copy2(filesystem_path(source), filesystem_path(temporary))
            os.replace(temporary, target)
        else:
            target.unlink(missing_ok=True)


def _matches(path: str, parent: Path):
    normalized = path.replace("\\", "/")
    prefix = parent.as_posix().rstrip("/")
    compare = str.casefold if os.name == "nt" else str
    if compare(normalized).startswith(compare(prefix) + "/"):
        return normalized[len(prefix) + 1:]
    return None


def prepare_portable_library(root: Path) -> dict:
    """Register owned roots and encode paths after the additive schema upgrade."""
    root = root.resolve(strict=True)
    metadata_path = root / "library.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {
        "schemaVersion": 1, "libraryId": str(uuid.uuid4()), "pathFormat": 1,
        "minimumReader": "portable-v1", "lastRoot": str(root)}
    if metadata.get("schemaVersion") != 1 or metadata.get("pathFormat") != 1:
        raise ValueError("Unsupported portable library format")
    namespace = uuid.UUID(metadata["libraryId"])
    old_root = Path(metadata["lastRoot"])
    os.environ["TS_DESKTOP_ROOT"] = str(root)
    from app.utils.desktop_data_migration import rebase_value
    from app.utils.portable_config import transform_paths
    database = root / "data/trailsnap.sqlite"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        if metadata_path.exists() and old_root == root and metadata.get("initialized"):
            return metadata
        users = db.execute("SELECT id,settings FROM users").fetchall()
        for owner, raw in users:
            settings = json.loads(raw or "{}")
            # Legacy values are rebased once then persisted as explicit references.
            settings = rebase_value(settings, old_root, root)
            from app.utils.portable_config import PREFIX
            decoded = transform_paths(settings, encode=False)
            storage = decoded.get("storage") or {}
            base = storage.get("photo_storage_path") or str(root / "data")
            if base in {"./data/uploads", "data/uploads"}:
                base = str(root / "data")
            anchors = [(Path(base) / "users" / owner, "用户文件")]
            anchors.extend((Path(item), "外部图库") for item in storage.get("external_directories", []) if item)
            owned_roots = []
            for anchor, name in anchors:
                anchor = anchor.resolve()
                relative = _matches(str(anchor), root)
                kind = "managed" if relative is not None else "external"
                location = relative if relative is not None else str(anchor)
                root_id = str(uuid.uuid5(namespace, f"{owner}:{kind}:{location}"))
                db.execute("INSERT OR IGNORE INTO storage_roots(id,owner_id,name,kind,location) VALUES (?,?,?,?,?)",
                           (root_id, owner, name, kind, location))
                owned_roots.append((anchor, root_id))
            # Fetch bounded batches; no ORM imports and no 20k-photo in-memory graph.
            cursor = db.execute("SELECT id,file_path FROM photos WHERE owner_id=? AND storage_root_id IS NULL", (owner,))
            while rows := cursor.fetchmany(1000):
                updates = []
                for photo_id, path in rows:
                    path = rebase_value(path, old_root, root)
                    for anchor, root_id in sorted(owned_roots, key=lambda item: len(str(item[0])), reverse=True):
                        relative = _matches(path, anchor)
                        if relative is not None:
                            updates.append((root_id, relative, path, photo_id))
                            break
                db.executemany("UPDATE photos SET storage_root_id=?,storage_relative_path=?,file_path=? WHERE id=?", updates)
            encoded = transform_paths(settings, encode=True)
            db.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(encoded, ensure_ascii=False), owner))
        for task_id, payload in db.execute("SELECT id,payload FROM tasks WHERE payload IS NOT NULL").fetchall():
            value = json.loads(payload)
            value = transform_paths(rebase_value(value, old_root, root), encode=True)
            db.execute("UPDATE tasks SET payload=? WHERE id=?", (json.dumps(value, ensure_ascii=False), task_id))
        # Rendered films and their sibling posters move with userdata too.
        # Keep external outputs unchanged, including records from older schemas.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_frame_works'").fetchone():
            for work_id, output in db.execute("SELECT rowid,output_path FROM daily_frame_works WHERE output_path IS NOT NULL").fetchall():
                rewritten = rebase_value(output, old_root, root)
                if rewritten != output:
                    db.execute("UPDATE daily_frame_works SET output_path=? WHERE rowid=?", (rewritten, work_id))
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Portable database check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Portable database foreign-key check failed")
    # Native/AI consumers currently require absolute model paths. Rebase only
    # configuration files; these are included in snapshots and never user photos.
    for config in configuration_files(root):
        if config == metadata_path or not config.is_file():
            continue
        original = json.loads(config.read_text(encoding="utf-8"))
        rewritten = rebase_value(original, old_root, root)
        if rewritten != original:
            write_json(config, rewritten)
    metadata["lastRoot"] = str(root)
    metadata["initialized"] = True
    write_json(metadata_path, metadata)
    return metadata
