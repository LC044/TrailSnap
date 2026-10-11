"""Compare SQLite face matching on an isolated backup of a photo library.

Run with the server Python environment. The source is opened read-only; all
scenario changes happen in a temporary backup. Outputs contain timings only.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.batch_size < 1 or args.rounds < 1:
        parser.error("batch-size and rounds must be positive")
    source_path = args.database.resolve(strict=True)
    server_root = Path(__file__).resolve().parents[1]
    repo_root = server_root.parents[1]
    sys.path.insert(0, str(server_root))
    # Importing server models must not connect to the user's configured DB.
    os.environ["TS_DB_URL"] = "sqlite:///:memory:"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import numpy as np
    from app.service import face_cluster as module

    # Execute only the two original lookup methods, not the old module's imports
    # or startup code. Both implementations use today's identical vector cache.
    baseline_sha = subprocess.check_output(
        ["git", "rev-parse", args.baseline_ref], cwd=repo_root, text=True,
    ).strip()
    source = subprocess.check_output(
        ["git", "show", f"{baseline_sha}:package/server/app/service/face_cluster.py"],
        cwd=repo_root, text=True, encoding="utf8",
    )
    original_class = next(node for node in ast.parse(source).body
                          if isinstance(node, ast.ClassDef) and node.name == "FaceClusterService")
    names = {"_resolve_assigned_candidates", "_sqlite_nearest_assigned_face"}
    methods = [node for node in original_class.body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(methods) != len(names):
        raise RuntimeError("Baseline does not contain the expected lookup methods")
    namespace = dict(vars(module))
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<baseline-face-matching>", "exec"), namespace)
    baseline_class = type("BaselineMatcher", (module.FaceClusterService,),
                          {name: namespace[name] for name in names})

    report = {"measured_at": datetime.now().astimezone().isoformat(),
              "baseline_sha": baseline_sha, "rounds": args.rounds,
              "scope": "SQLite nearest assigned face lookup; excludes image IO, AI, writes and scheduler",
              "source_opened_read_only": True, "scenarios": []}
    with tempfile.TemporaryDirectory(prefix="trailsnap-face-benchmark-") as temp:
        snapshot = Path(temp) / "snapshot.sqlite"
        with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(snapshot)) as destination:
                original.backup(destination)
        with closing(sqlite3.connect(snapshot)) as db, db:
            report["photos"] = db.execute("SELECT count(*) FROM photos").fetchone()[0]
            report["faces"] = db.execute("SELECT count(*) FROM faces").fetchone()[0]
            owner = db.execute("SELECT p.owner_id FROM faces f JOIN photos p ON p.id=f.photo_id "
                               "WHERE f.is_deleted=0 AND f.face_feature IS NOT NULL LIMIT 1").fetchone()
            if not owner:
                raise RuntimeError("The library has no live face embeddings")
            owner_id = uuid.UUID(owner[0])
            rows = db.execute(
                "SELECT f.id,f.face_feature FROM faces f JOIN photos p ON p.id=f.photo_id "
                "WHERE p.owner_id=? AND f.is_deleted=0 AND f.face_feature IS NOT NULL ORDER BY f.id",
                (str(owner_id),),
            ).fetchall()
            targets = [(face_id, module.FaceClusterService.normalize_embedding(json.loads(vector)))
                       for face_id, vector in rows[:args.batch_size]]
            if len(rows) <= len(targets):
                raise RuntimeError("Need reference faces in addition to batch targets")
        engine = create_engine(f"sqlite:///{snapshot.as_posix()}")
        try:
            for scenario in ("no_assigned_references", "assigned_references"):
                with closing(sqlite3.connect(snapshot)) as db, db:
                    db.execute("UPDATE faces SET face_identity_id=NULL")
                    if scenario == "assigned_references":
                        identity_id = str(uuid.uuid4())
                        db.execute("INSERT INTO face_identities(id,identity_name,owner_id,is_deleted,is_hidden) "
                                   "VALUES(?,?,?,0,0)", (identity_id, "Benchmark", str(owner_id)))
                        reference_ids = [row[0] for row in rows[len(targets)::16]]
                        db.executemany("UPDATE faces SET face_identity_id=? WHERE id=?",
                                       [(identity_id, face_id) for face_id in reference_ids])
                    else:
                        reference_ids = []
                record = {"name": scenario, "batch_size": len(targets),
                          "assigned_references": len(reference_ids), "implementations": {}}
                expected = None
                for label, cls in (("before", baseline_class), ("after", module.FaceClusterService)):
                    module.face_vector_cache.invalidate()
                    times = []
                    with Session(engine, autoflush=False) as session:
                        matcher = cls(session)
                        for index in range(args.rounds):
                            started = time.perf_counter()
                            results = [matcher._sqlite_nearest_assigned_face(vector, face_id, owner_id)
                                       for face_id, vector in targets]
                            elapsed = (time.perf_counter() - started) * 1000
                            times.append(elapsed)
                            if expected is None:
                                expected = results
                            for old, new in zip(expected, results):
                                if old is None or new is None:
                                    assert old is new, "Matching eligibility changed"
                                else:
                                    assert old[:2] == new[:2] and np.isclose(old[2], new[2]), "Match changed"
                            print(f"{scenario} {label} round={index + 1} batch_ms={elapsed:.3f}", flush=True)
                    record["implementations"][label] = {"batch_ms": times,
                        "median_batch_ms": statistics.median(times),
                        "vector_cache_rows": module.face_vector_cache.stats()["rows"]}
                record["results_equal"] = True
                record["speedup"] = (record["implementations"]["before"]["median_batch_ms"] /
                                     record["implementations"]["after"]["median_batch_ms"])
                report["scenarios"].append(record)
        finally:
            engine.dispose()
            module.face_vector_cache.invalidate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
