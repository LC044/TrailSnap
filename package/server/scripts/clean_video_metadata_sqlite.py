"""Remove legacy binary video metadata from an offline SQLite database.

Dry run by default. Close TrailSnap before using --apply. A verified SQLite
backup is mandatory before any update; photos and other metadata are retained.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path


BINARY_KEYS = frozenset({"mcvr", "snal", "tnal", "covr"})


def clean_exif(raw: str) -> tuple[str, list[str]]:
    """Only remove known binary video atoms, leaving every other JSON value intact."""
    value = json.loads(raw)
    if not isinstance(value, dict):
        return raw, []
    removed = [key for key in value if key.lower() in BINARY_KEYS]
    if not removed:
        return raw, []
    return json.dumps(
        {key: val for key, val in value.items() if key not in removed},
        ensure_ascii=False,
    ), removed


def check_database(connection: sqlite3.Connection) -> None:
    results = connection.execute("PRAGMA quick_check").fetchall()
    if results != [("ok",)]:
        raise RuntimeError(f"Database check failed: {results}")


def clean_database(database: Path, backup_dir: Path, *, apply: bool = False,
                   vacuum: bool = False) -> dict:
    database = database.resolve(strict=True)
    result = {"database": str(database), "before_bytes": database.stat().st_size,
              "changed_rows": 0, "removed_json_bytes": 0, "removed_keys": {},
              "applied": apply}
    # mode=rw prevents accidentally creating a database from a mistyped path.
    connection = sqlite3.connect(database.as_uri() + "?mode=rw" if apply
                                 else database.as_uri() + "?mode=ro", uri=True,
                                 timeout=5)
    try:
        if apply:
            # Hold the writer lock while producing a consistent backup and
            # cleaning. A separate read connection backs up the WAL snapshot.
            connection.execute("BEGIN IMMEDIATE")
            backup_dir = backup_dir.resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (
                database.stem + "-before-video-cleanup-"
                + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite"
            )
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)
                    check_database(destination)
            result["backup"] = str(backup)
            print(json.dumps({"backup": str(backup), "verified": True}), flush=True)

        counts_before = {name: 0 for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for table in counts_before:
            quoted = '"' + table.replace('"', '""') + '"'
            counts_before[table] = connection.execute(
                "SELECT count(*) FROM " + quoted
            ).fetchone()[0]
        keys = Counter()
        # keyset batches avoid accumulating huge legacy JSON strings in memory.
        last_rowid = 0
        while True:
            rows = connection.execute(
                "SELECT m.rowid, m.photo_id, m.exif_info FROM photo_metadata m "
                "JOIN photos p ON p.id=m.photo_id "
                "WHERE m.rowid>? AND p.file_type='video' AND m.exif_info IS NOT NULL "
                "ORDER BY m.rowid LIMIT 16", (last_rowid,)
            ).fetchall()
            if not rows:
                break
            for rowid, photo_id, raw in rows:
                last_rowid = rowid
                # Invalid JSON aborts before commit rather than discarding data.
                cleaned, removed = clean_exif(raw)
                if not removed:
                    continue
                if apply:
                    connection.execute(
                        "UPDATE photo_metadata SET exif_info=? WHERE photo_id=?",
                        (cleaned, photo_id),
                    )
                    saved = connection.execute(
                        "SELECT exif_info FROM photo_metadata WHERE photo_id=?",
                        (photo_id,),
                    ).fetchone()[0]
                    if saved != cleaned:
                        raise RuntimeError("Metadata update verification failed")
                result["changed_rows"] += 1
                result["removed_json_bytes"] += len(raw.encode()) - len(cleaned.encode())
                keys.update(removed)
            if result["changed_rows"] and result["changed_rows"] % 100 == 0:
                print(json.dumps({"changed_rows": result["changed_rows"]}), flush=True)

        for table, count in counts_before.items():
            quoted = '"' + table.replace('"', '""') + '"'
            if connection.execute("SELECT count(*) FROM " + quoted).fetchone()[0] != count:
                raise RuntimeError(f"Row count changed in {table}")
        if apply:
            check_database(connection)
            connection.commit()
            if vacuum:
                print("Compacting database...", flush=True)
                connection.execute("VACUUM")
            check_database(connection)
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint[0]:
                raise RuntimeError("Checkpoint busy; close all database readers and retry")
        result["removed_keys"] = dict(keys)
        result["after_bytes"] = database.stat().st_size
        return result
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--vacuum", action="store_true")
    args = parser.parse_args()
    if args.apply and args.backup_dir is None:
        parser.error("--apply requires --backup-dir")
    if args.vacuum and not args.apply:
        parser.error("--vacuum requires --apply")
    result = clean_database(args.database, args.backup_dir or args.database.parent,
                            apply=args.apply, vacuum=args.vacuum)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
