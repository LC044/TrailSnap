"""Offline desktop data migration; runs before either sidecar starts."""

from __future__ import annotations

import json
import hashlib
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any
from app.utils.windows_paths import filesystem_path, publish_directory

MARKER = ".trailsnap-migration.json"


def rebase_value(value: Any, source: Path, target: Path) -> Any:
    """Rewrite only complete paths beneath the old root, including JSON values."""
    if isinstance(value, dict):
        return {key: rebase_value(item, source, target) for key, item in value.items()}
    if isinstance(value, list):
        return [rebase_value(item, source, target) for item in value]
    if not isinstance(value, str):
        return value
    normalized = value.replace("\\", "/")
    old = source.as_posix().rstrip("/")
    compare = str.casefold if os.name == "nt" else str
    if compare(normalized) == compare(old) or compare(normalized).startswith(compare(old) + "/"):
        suffix = normalized[len(old):].lstrip("/")
        return str(target / suffix) if suffix else str(target)
    return value


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _rewrite_database(database: Path, source: Path, target: Path) -> None:
    with closing(sqlite3.connect(database)) as db, db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError(f"数据库校验失败：{database.name}")
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for (table,) in tables:
            columns = db.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
            for _, column, kind, *_ in columns:
                is_json = kind.upper() == "JSON" or (table == "system_state" and column == "value")
                is_path = column.endswith(("_path", "_directory", "_root"))
                if not (is_json or is_path):
                    continue
                field = _quote(column)
                # Fetch bounded batches so large photo libraries do not fill memory.
                cursor = db.execute(f"SELECT rowid, {field} FROM {_quote(table)} WHERE typeof({field})='text'")
                while rows := cursor.fetchmany(1000):
                    updates = []
                    for rowid, raw in rows:
                        if is_json:
                            try:
                                value = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            rewritten = rebase_value(value, source, target)
                            result = json.dumps(rewritten, ensure_ascii=False) if rewritten != value else raw
                        else:
                            result = rebase_value(raw, source, target)
                        if result != raw:
                            updates.append((result, rowid))
                    db.executemany(f"UPDATE {_quote(table)} SET {field}=? WHERE rowid=?", updates)
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _wait_for_sidecars(source: Path) -> None:
    """An orphan's parent watcher may need two seconds after a shell crash."""
    import psutil

    excluded = {os.getpid(), *(process.pid for process in psutil.Process().parents())}
    deadline = time.monotonic() + 5
    while True:
        running = False
        for process in psutil.process_iter(["pid", "name", "cwd"]):
            try:
                info = process.info
                if info["pid"] in excluded or not (info["name"] or "").lower().startswith(("trailsnap-serv", "trailsnap-ai")):
                    continue
                if info["cwd"] and Path(info["cwd"]).resolve() in (source, source / "data"):
                    running = True
                    break
            except (psutil.Error, OSError):
                continue
        if not running:
            return
        if time.monotonic() >= deadline:
            raise ValueError("旧目录仍有后台服务运行，请完全退出其他行影集客户端后重试")
        time.sleep(0.2)


def migrate_data_directory(source: Path, target: Path, *, skip_browser_state: bool = False) -> None:
    logical_source = source.absolute()
    source, target = source.resolve(strict=True), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("新旧数据目录不能相同或互相包含")
    completed = {"source": str(source), "target": str(target)}
    marker = target / MARKER
    # A process may have exited after publishing the copy but before saving config.
    if marker.is_file() and json.loads(marker.read_text(encoding="utf-8")) == completed:
        return
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("请选择空文件夹，避免覆盖已有文件")
    _wait_for_sidecars(source)
    files = []
    directories = []
    def raise_walk_error(error: OSError) -> None:
        raise error

    io_source = Path(filesystem_path(source))
    for current, dirs, names in os.walk(io_source, onerror=raise_walk_error):
        current = source / Path(current).relative_to(io_source)
        if skip_browser_state and current == source:
            # The current UI still owns its WebView profile while the native
            # command copies the library. The new instance authenticates afresh.
            dirs[:] = [name for name in dirs if name != "webview" and not name.startswith("webview-backup-")]
            names[:] = [name for name in names if name != "webview-context.json"]
        for name in dirs + names:
            path = Path(filesystem_path(current / name))
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"数据目录中含有链接，请先处理后再迁移：{path}")
        directories.extend(current / name for name in dirs)
        files.extend(current / name for name in names if current != source or name not in {MARKER, ".instance.lock", ".desktop-migration-ready"})
    target.parent.mkdir(parents=True, exist_ok=True)
    required = sum(os.stat(filesystem_path(path)).st_size for path in files)
    if shutil.disk_usage(target.parent).free < required + 64 * 1024 * 1024:
        raise ValueError("目标磁盘可用空间不足（需额外保留 64 MB）")
    staging = Path(tempfile.mkdtemp(prefix=".trailsnap-migration-", dir=target.parent))
    try:
        for directory in directories:
            Path(filesystem_path(staging / directory.relative_to(source))).mkdir(parents=True, exist_ok=True)
        for path in files:
            copied = staging / path.relative_to(source)
            Path(filesystem_path(copied.parent)).mkdir(parents=True, exist_ok=True)
            shutil.copy2(filesystem_path(path), filesystem_path(copied))
            with open(filesystem_path(path), 'rb') as source_file, open(filesystem_path(copied), 'rb') as target_file:
                if hashlib.file_digest(source_file, 'sha256').digest() != hashlib.file_digest(target_file, 'sha256').digest():
                    raise ValueError(f"复制文件校验失败：{path}")
        for database in staging.glob("data/*.sqlite"):
            _rewrite_database(database, logical_source, target)
            if source != logical_source:
                _rewrite_database(database, source, target)
        # JSON configuration may contain local model paths and per-user settings.
        configs = [staging / "ai-config.json", *staging.glob("data/**/config/*.json"), *staging.glob("data/*config*.json")]
        for config in configs:
            if not config.is_file():
                continue
            value = json.loads(config.read_text(encoding="utf-8"))
            rewritten = rebase_value(rebase_value(value, logical_source, target), source, target)
            if rewritten != value:
                config.write_text(json.dumps(rewritten, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / MARKER).write_text(json.dumps(completed, ensure_ascii=False), encoding="utf-8")
        if target.exists():
            target.rmdir()  # Fails safely if another process put files here.
        publish_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(filesystem_path(staging))
