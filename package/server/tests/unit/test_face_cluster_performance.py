"""Compare actual legacy DBSCAN and appearance-cluster passes on test copies.

Runs through pytest and the shared test entry. Synthetic vectors measure runtime,
not recognition accuracy. Reports are stored under tests/.cache.
"""
import contextlib
import cProfile
import io
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, insert, text, func
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.user import User
from app.db.models.photo import Photo, FileType
from app.db.models.face import Face, FaceCluster, FaceIdentity
from app.service import face_cluster, face_appearance_clusters
from test_face_cluster_upgrade import legacy_database
from alembic import command

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


@pytest.mark.parametrize("size", [1000, 5000, 10000])
def test_face_clustering_performance(tmp_path, monkeypatch, size, legacy_database):
    if os.getenv("TS_FACE_BENCHMARK") != "1":
        pytest.skip("Explicit performance run only")
    engine, migration_config, _ = legacy_database
    root = Path(__file__).resolve().parents[4]
    baseline_ref = os.getenv("TS_FACE_BASELINE_REF", "a4f375c6f1363ee4b77cae072a722bf8b4960779")
    source = subprocess.check_output(["git", "show", f"{baseline_ref}:package/server/app/service/face_cluster.py"], cwd=root, text=True, encoding="utf-8")
    namespace = dict(vars(face_cluster))
    exec(compile(source, "<legacy-clustering>", "exec"), namespace)
    crud_source = subprocess.check_output(["git", "show", f"{baseline_ref}:package/server/app/crud/face.py"], cwd=root, text=True, encoding="utf-8")
    crud_namespace = dict(vars(face_cluster.crud_face))
    exec(compile(crud_source, "<legacy-face-crud>", "exec"), crud_namespace)
    namespace["crud_face"] = SimpleNamespace(**crud_namespace)
    baseline = namespace["FaceClusterService"]
    config = SimpleNamespace(ai=SimpleNamespace(face_cluster_threshold=.4, face_recognition_min_photos=5))
    monkeypatch.setattr(face_appearance_clusters.config_manager, "get_user_config", lambda *args: config)
    rng = np.random.default_rng(42)
    centers = rng.normal(size=(size // 10, 512)).astype(np.float32)
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    features = centers[np.arange(size) // 10] + rng.normal(0, .002, size=(size, 512))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    result = {"baseline_ref": baseline_ref, "database": engine.dialect.name, "size": size, "data": "synthetic, ten photos per distinct appearance", "seconds": {}, "identities": {}}
    for label in ["baseline", "new"]:
        if label == "new":
            # Each implementation starts with a fresh index. Keeping legacy
            # tuples would otherwise make the new PG HNSW index 2-4x larger.
            engine.dispose()
            if engine.dialect.name == "sqlite":
                new_url = f"sqlite:///{(tmp_path / 'new.sqlite').as_posix()}"
                monkeypatch.setenv("TS_DB_URL", new_url)
                migration_config.set_main_option("sqlalchemy.url", new_url)
                engine = create_engine(new_url)
            else:
                assert engine.url.database.startswith("trailsnap_face_test_")
                with engine.begin() as connection:
                    connection.execute(text("DROP SCHEMA public CASCADE"))
                    connection.execute(text("CREATE SCHEMA public"))
                    connection.execute(text("CREATE EXTENSION vector"))
            command.upgrade(migration_config, "head")
        owner = uuid4()
        photos = [uuid4() for _ in range(size)]
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            db.add(User(id=owner, username=label, hashed_password="unused"))
            db.commit()
            db.execute(insert(Photo.__table__), [{"id":photo, "owner_id":owner, "filename":f"{i}.jpg", "file_path":f"/{i}.jpg", "file_type":FileType.image} for i, photo in enumerate(photos)])
            db.execute(insert(Face), [{"photo_id":photo, "face_feature":feature.tolist()} for photo, feature in zip(photos, features)])
            db.commit()
            if engine.dialect.name == "postgresql":
                db.execute(text("ANALYZE photos"))
                db.execute(text("ANALYZE faces"))
                db.commit()
            if label == "new" and engine.dialect.name == "sqlite":
                query = "EXPLAIN QUERY PLAN SELECT f.id,f.face_feature,f.face_identity_id FROM faces AS f INDEXED BY ix_faces_unclustered WHERE f.face_cluster_id IS NULL AND f.is_deleted=false AND f.face_feature IS NOT NULL AND f.id>0 AND EXISTS (SELECT 1 FROM photos p WHERE p.id=f.photo_id AND p.owner_id=:owner AND p.is_deleted=false) ORDER BY f.id LIMIT 512"
                result["candidate_plan"] = [list(row) for row in db.execute(text(query), {"owner":str(owner)}).all()]
            start = time.perf_counter()
            if label == "baseline":
                with contextlib.redirect_stdout(io.StringIO()):
                    baseline(db)._cluster_unassigned_faces(owner)
            else:
                profiler = cProfile.Profile() if os.getenv("TS_FACE_PROFILE") == "1" else None
                if profiler:
                    profiler.enable()
                face_appearance_clusters.process_faces(db, owner)
                if profiler:
                    profiler.disable()
                    destination = root / "tests" / ".cache" / "face-clusters"
                    destination.mkdir(parents=True, exist_ok=True)
                    profiler.dump_stats(str(destination / "profile.bin"))
            result["seconds"][label] = time.perf_counter() - start
            result["identities"][label] = db.query(FaceIdentity).filter(FaceIdentity.owner_id == owner, FaceIdentity.is_deleted.is_(False)).count()
            assert db.query(func.count(Face.id)).filter(Face.face_identity_id.is_(None)).scalar() == 0
        engine.dispose()
    output = root / "tests" / ".cache" / "face-clusters"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"benchmark-{engine.dialect.name}-{size}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    assert result["identities"]["new"] == result["identities"]["baseline"]
    assert result["seconds"]["new"] <= result["seconds"]["baseline"] * 1.05
