"""Real SQLite and opt-in PostgreSQL cleanup lifecycle and index regressions."""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models import User, Photo, ImageVector, ToolboxPlanItem, Task
from app.db.models.toolbox import CleanupGroup, CleanupMember, CleanupScope, CleanupSelection
from app.schemas.toolbox import PlanRequest, MediaScope, ToolConfig, ExecuteRequest, CleanupSelectionRequest
from app.service.cleanup_scan import enqueue_scan, run_scan, queue_scan
from app.service.cleanup_index import CleanupIndex
from app.service.toolbox_execution import start_plan, execute_plan
from app.api import toolbox_workflows as api

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture(params=["sqlite", "postgres"])
def lib(request, tmp_path, monkeypatch):
    monkeypatch.setenv("TS_CLEANUP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("TS_DESKTOP_PORTABLE", raising=False)
    schema = None
    admin = None
    if request.param == "postgres":
        if os.environ.get("TS_CLEANUP_TEST_PG") != "1":
            pytest.skip("set TS_CLEANUP_TEST_PG=1 through tests/.env.test to exercise real PostgreSQL")
        url = os.environ.get("TS_DB_URL", "")
        assert url.startswith("postgresql"), "PG tests require TS_DB_URL from shared test configuration"
        admin = create_engine(url)
        schema = "cleanup_test_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"}).execution_options(schema_translate_map={None: schema})
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'library.sqlite').as_posix()}")
        @event.listens_for(engine, "connect")
        def fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    if schema:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT current_schema()")).scalar() == schema
            assert connection.execute(text(f'SELECT count(*) FROM "{schema}".users')).scalar() == 0
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="cleanup", hashed_password="unused", settings={"storage": {"external_directories": [str(tmp_path)]}})
        other = User(id=uuid4(), username="other", hashed_password="unused")
        db.add_all([user, other])
        db.commit()
        def photo(name, content=b"same", vector=None, model="model-a", owner=None, pid=None):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            item = Photo(id=pid or uuid4(), owner_id=owner or user.id, filename=name, file_path=str(path), file_type="image")
            db.add(item)
            db.flush()
            if vector is not None:
                db.add(ImageVector(photo_id=item.id, embedding=list(vector), model_name=model))
            db.commit()
            return item
        yield SimpleNamespace(db=db, user=user, other=other, photo=photo, root=tmp_path, engine=engine)
    engine.dispose()
    if admin is not None:
        # Only the random schema created by this fixture is removed.
        assert schema.startswith("cleanup_test_") and len(schema) == 45
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def scan(lib, mode="duplicate", **config):
    scope = config.pop("scope", MediaScope(source="all"))
    plan = enqueue_scan(lib.db, lib.user, PlanRequest(scope=scope, config=ToolConfig(kind="cleanup", cleanup_mode=mode, **config)))
    assert plan.status == "scan_queued"
    run_scan(lib.db, plan.id)
    lib.db.refresh(plan)
    assert plan.status == "preview"
    return plan


def unit_vector(angle=0):
    vector = np.zeros(512)
    vector[:2] = [np.cos(angle), np.sin(angle)]
    return vector


def test_duplicate_hash_reuse_change_failure_and_pagination(lib):
    a, b = lib.photo("a.jpg"), lib.photo("b.jpg")
    missing = lib.photo("missing.jpg")
    Path(missing.file_path).unlink()
    lib.photo("other.jpg", owner=lib.other.id)
    first = scan(lib)
    assert first.summary["total"] == 3
    assert first.summary["candidate"] == 2
    assert first.summary["hash_failed"] == 1
    group = lib.db.query(CleanupGroup).filter_by(plan_id=first.id).one()
    result = api.group_members(first.id, group.id, offset=0, limit=1, db=lib.db, user=lib.user)
    assert result.code == 0 and result.data["total"] == 2 and len(result.data["items"]) == 1
    again = scan(lib)
    assert again.summary["hash_reused"] == 2
    Path(b.file_path).write_bytes(b"changed-longer")
    third = scan(lib)
    assert third.summary["candidate"] == 0
    assert third.summary["hashed"] == 1


@pytest.mark.parametrize("scan_mode", ["fast", "complete"])
def test_similar_model_owner_isolation_no_transitive_merge(lib, scan_mode):
    a = lib.photo("a.jpg", vector=unit_vector(0), pid=UUID(int=1))
    b = lib.photo("b.jpg", vector=unit_vector(.2), pid=UUID(int=2))
    c = lib.photo("c.jpg", vector=unit_vector(.4), pid=UUID(int=3))
    lib.photo("different-model.jpg", vector=unit_vector(), model="model-b")
    lib.photo("other.jpg", vector=unit_vector(), owner=lib.other.id)
    plan = scan(lib, "similar", scan_mode=scan_mode, similarity=.97)
    members = lib.db.query(CleanupMember).filter_by(plan_id=plan.id).all()
    assert {m.photo_id for m in members} == {a.id, b.id}
    assert c.id not in {m.photo_id for m in members}


def test_index_incremental_restart_changes_deletes_and_shards(lib, monkeypatch):
    import app.service.cleanup_index as module
    monkeypatch.setattr(module, "SHARD_SIZE", 2)
    photos = [lib.photo(f"{i}.jpg", vector=unit_vector()) for i in range(5)]
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        assert index.changed == 5 and index.rebuilt == 3
        assert set(index.matches(photos[0].id, .99)) == {str(p.id) for p in photos}
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        assert index.changed == 0 and index.rebuilt == 0 and index.decoded == 0
    vector = lib.db.get(ImageVector, photos[1].id)
    vector.embedding = unit_vector(1).tolist()
    photos[2].is_deleted = True
    lib.db.commit()
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        assert index.changed == 1 and index.rebuilt >= 1
        assert set(index.matches(photos[0].id, .99)) == {str(p.id) for p in (photos[0], photos[3], photos[4])}


def test_index_initialization_failure_releases_cache_and_lock(lib, monkeypatch):
    import contextlib
    import app.service.cleanup_index as module
    released = []
    @contextlib.contextmanager
    def lock(_):
        try:
            yield
        finally:
            released.append(True)
    monkeypatch.setattr(module, "file_lock", lock)
    index = CleanupIndex(lib.db, lib.user.id, "model-a")
    def fail():
        raise OSError("cache unavailable")
    monkeypatch.setattr(index, "_initialize_cache", fail)
    with pytest.raises(OSError, match="cache unavailable"):
        with index:
            pass
    assert released == [True]
    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        index.cache.execute("SELECT 1")


def test_scope_external_references_and_safe_execution(lib, monkeypatch):
    a, b = lib.photo("a.jpg"), lib.photo("b.jpg")
    plan = scan(lib, scope=MediaScope(source="selected", photo_ids=[a.id]), compare_all=True)
    row = lib.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).one()
    assert row.photo_id == a.id
    response = api.selection(plan.id, CleanupSelectionRequest(version=plan.version, item_ids=[row.id], selected=True), db=lib.db, user=lib.user)
    assert response.data["selected_count"] == 1
    start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True))
    from app.crud import album
    monkeypatch.setattr(album, "trigger_conditional_albums_update", lambda *args: None)
    asyncio.run(execute_plan(None, lib.db.get(Task, plan.task_id), lib.db))
    lib.db.refresh(a)
    lib.db.refresh(b)
    assert a.is_deleted and not b.is_deleted
    assert Path(a.file_path).exists() and Path(b.file_path).exists()


def test_duplicate_must_keep_copy_and_changed_keeper_blocks_delete(lib):
    a, b = lib.photo("a.jpg"), lib.photo("b.jpg")
    plan = scan(lib)
    rows = lib.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).all()
    with pytest.raises(ValueError, match="保留"):
        start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True, selected_items=[r.id for r in rows]))
    lib.db.rollback()
    target = next(row for row in rows if row.photo_id == a.id)
    start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True, selected_items=[target.id]))
    Path(b.file_path).write_bytes(b"keeper modified")
    asyncio.run(execute_plan(None, lib.db.get(Task, plan.task_id), lib.db))
    lib.db.refresh(target)
    assert target.status == "failed"
    assert not a.is_deleted and not b.is_deleted


def test_stop_resume_checkpoint_no_duplicate_members(lib, monkeypatch):
    from app.service import cleanup_scan as module
    monkeypatch.setattr(module, "BATCH", 2)
    for i in range(5):
        lib.photo(f"{i}.jpg")
    request = PlanRequest(scope=MediaScope(source="all"), config=ToolConfig(kind="cleanup"))
    plan = enqueue_scan(lib.db, lib.user, request)
    original = module.checkpoint
    def interrupt(db, plan, **values):
        if values.get("snapshot_cursor"):
            plan.stop_requested = True
        return original(db, plan, **values)
    monkeypatch.setattr(module, "checkpoint", interrupt)
    run_scan(lib.db, plan.id)
    assert plan.status == "scan_stopped"
    assert lib.db.query(CleanupScope).filter_by(plan_id=plan.id).count() == 2
    monkeypatch.setattr(module, "checkpoint", original)
    queue_scan(lib.db, plan)
    run_scan(lib.db, plan.id)
    assert plan.status == "preview"
    assert plan.summary["total"] == 5 and plan.summary["candidate"] == 5
    assert lib.db.query(CleanupMember).filter_by(plan_id=plan.id).count() == 5


def test_selection_scope_export_and_retry_keep_safe_defaults(lib):
    a, b = lib.photo("a.jpg"), lib.photo("b.jpg")
    plan = scan(lib)
    rows = lib.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).order_by(ToolboxPlanItem.id).all()
    other_plan = scan(lib)
    invalid = api.selection(other_plan.id, CleanupSelectionRequest(version=other_plan.version,
        item_ids=[rows[0].id], selected=True), db=lib.db, user=lib.user)
    assert invalid.code == 400
    selected = api.selection(plan.id, CleanupSelectionRequest(version=plan.version,
        item_ids=[rows[0].id], selected=True), db=lib.db, user=lib.user)
    assert selected.data["selected_count"] == 1
    page = api.items(plan.id, offset=0, limit=1, status="candidate", db=lib.db, user=lib.user)
    assert page.data["selected_count"] == 1 and page.data["items"][0]["selected"]
    response = api.export_plan(plan.id, db=lib.db, user=lib.user)
    async def collect():
        return ''.join([chunk async for chunk in response.body_iterator])
    csv = asyncio.run(collect())
    assert csv.startswith('\ufeff') and 'a.jpg' in csv and 'b.jpg' in csv
    from app.service.cleanup_execution import prepare_retry
    plan.status = "stopped"
    rows[0].status, rows[1].status = "failed", "success"
    lib.db.commit()
    old_version = plan.version
    prepare_retry(lib.db, plan)
    assert plan.status == "preview" and plan.version == old_version + 1
    assert rows[0].status == "candidate" and rows[1].status == "success"
    assert lib.db.query(CleanupSelection).filter_by(plan_id=plan.id).count() == 0


def test_recycle_execution_crosses_batch_boundary_and_keeps_original(lib):
    seed = lib.photo("keep.jpg")
    ids = [uuid4() for _ in range(101)]
    lib.db.execute(Photo.__table__.insert(), [{"id": pid, "owner_id": lib.user.id,
        "filename": f"{pid}.jpg", "file_path": seed.file_path, "file_type": "image"} for pid in ids])
    lib.db.commit()
    plan = scan(lib)
    selected = [iid for (iid,) in lib.db.query(ToolboxPlanItem.id).filter(
        ToolboxPlanItem.plan_id == plan.id, ToolboxPlanItem.photo_id != seed.id)]
    assert len(selected) == 101
    response = api.selection(plan.id, CleanupSelectionRequest(version=plan.version,
        item_ids=selected, selected=True), db=lib.db, user=lib.user)
    assert response.data["selected_count"] == 101
    start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True))
    result = asyncio.run(execute_plan(None, lib.db.get(Task, plan.task_id), lib.db))
    lib.db.expire_all()
    assert result["success_count"] == 101
    assert lib.db.query(Photo).filter(Photo.id.in_(ids), Photo.is_deleted.is_(True)).count() == 101
    assert not lib.db.get(Photo, seed.id).is_deleted
    assert Path(seed.file_path).read_bytes() == b"same"
    assert plan.status == "completed" and plan.summary["success"] == 101


def test_cleanup_migration_matches_models_and_roundtrips(lib):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from app.db.models.toolbox import CleanupHash
    models = [CleanupSelection, CleanupMember, CleanupScope, CleanupGroup, CleanupHash]
    dialect = lib.engine.dialect.name
    folder, prefix = ("alembic", "cleanup_pg_0027") if dialect == "postgresql" else ("alembic_sqlite", "cleanup_sqlite_0027")
    path = next((Path(__file__).resolve().parents[2] / folder / "versions").glob(prefix + "*.py"))
    spec = importlib.util.spec_from_file_location("cleanup_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    lib.db.commit()
    with lib.engine.begin() as connection:
        for model in models:
            model.__table__.drop(connection)
        index = next(i for i in Photo.__table__.indexes if i.name == "ix_photos_owner_deleted_md5")
        index.drop(connection)
        next(i for i in Photo.__table__.indexes if i.name == "ix_photos_owner_deleted_id").drop(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.op.drop_column("image_vectors", "content_revision")
        migration.upgrade()
        for model in models:
            assert {c["name"] for c in inspect(connection).get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
        migration.downgrade()
        assert not inspect(connection).has_table("cleanup_scope")
        migration.upgrade()


@pytest.mark.module_cleanup_scale
def test_full_scope_100k_and_selection_over_10k(lib):
    count = int(os.environ.get("TS_CLEANUP_SCALE", "0"))
    if count < 50001:
        pytest.skip("set TS_CLEANUP_SCALE=100000 in shared test configuration")
    import time
    import json
    import hashlib
    import psutil
    from app.service.cleanup_scan import materialize
    process = psutil.Process()
    baseline = process.memory_info().rss
    started = time.perf_counter()
    seed = lib.photo("seed.jpg")
    path = seed.file_path
    md5 = hashlib.md5(b"same").hexdigest()
    # A large group with existing valid hashes, plus many non-duplicate
    # photos: full traversal and selection scale without wasting disk space.
    for start in range(1, count, 1000):
        photos = [{"id": UUID(int=i + 100), "owner_id": lib.user.id,
            "filename": f"{i}.jpg", "file_path": path, "file_type": "image", "md5": md5 if i <= 10002 else None}
            for i in range(start, min(start + 1000, count))]
        lib.db.execute(Photo.__table__.insert(), [{**p, "file_path": p["file_path"]} for p in photos])
        lib.db.commit()
    plan = scan(lib, "quality")
    assert plan.summary["total"] == count and plan.summary["processed"] == count
    assert lib.db.query(CleanupScope).filter_by(plan_id=plan.id, in_scope=True).count() == count
    # Exercise database grouping and candidate generation without rehashing
    # one shared fixture file a hundred thousand times.
    from app.service.cleanup_scan import duplicate_groups
    config = ToolConfig(kind="cleanup", cleanup_mode="duplicate")
    plan.request = {**plan.request, "config": config.model_dump(mode="json")}
    plan.summary = {**plan.summary, "phase": "groups", "processed": 0, "item_cursor": None}
    duplicate_groups(lib.db, plan)
    materialize(lib.db, plan, lib.user, config)
    assert plan.summary["candidate"] == 10002
    item_ids = [pid for (pid,) in lib.db.query(ToolboxPlanItem.id).filter_by(plan_id=plan.id).order_by(ToolboxPlanItem.id)]
    for start in range(0, 10000, 500):
        result = api.selection(plan.id, CleanupSelectionRequest(version=plan.version, item_ids=item_ids[start:start+500], selected=True), db=lib.db, user=lib.user)
        assert result.code == 0
    result = api.selection(plan.id, CleanupSelectionRequest(version=plan.version, item_ids=item_ids[10000:], selected=True), db=lib.db, user=lib.user)
    assert result.data["selected_count"] == 10002
    # All selected must be rejected; deselect one keeper and confirm >10000
    # server-side selections without a giant execute request body.
    with pytest.raises(ValueError, match="保留"):
        start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True))
    lib.db.rollback()
    api.selection(plan.id, CleanupSelectionRequest(version=plan.version, item_ids=[item_ids[-1]], selected=False), db=lib.db, user=lib.user)
    start_plan(lib.db, lib.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True))
    result = {"dialect": lib.engine.dialect.name, "total": count, "candidates": 10002,
        "selected": 10001, "seconds": round(time.perf_counter()-started, 2),
        "rss_delta_mb": round((process.memory_info().rss-baseline)/1024**2, 1)}
    report = Path(__file__).resolve().parents[4] / "tests" / "artifacts" / f"cleanup-scale-{lib.engine.dialect.name}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"CLEANUP_SCALE {result}")


@pytest.mark.module_cleanup_scale
@pytest.mark.module_cleanup_index_scale
def test_similar_over_3000_and_large_group_recall(lib):
    if int(os.environ.get("TS_CLEANUP_SCALE", "0")) < 3001:
        pytest.skip("enable TS_CLEANUP_SCALE in shared configuration")
    seed = lib.photo("seed.jpg")
    vector = unit_vector().tolist()
    for start in range(0, 3001, 250):
        ids = [uuid4() for _ in range(start, min(start + 250, 3001))]
        lib.db.execute(Photo.__table__.insert(), [{"id": pid, "owner_id": lib.user.id, "filename": f"{pid}.jpg", "file_path": seed.file_path, "file_type": "image"} for pid in ids])
        lib.db.execute(ImageVector.__table__.insert(), [{"photo_id": pid, "embedding": vector, "model_name": "model-a"} for pid in ids])
        lib.db.commit()
    plan = scan(lib, "similar")
    assert plan.summary["total"] == 3002
    assert plan.summary["candidate"] == 3001
    assert plan.summary["missing_vectors"] == 1
    assert lib.db.query(CleanupGroup).filter_by(plan_id=plan.id).one().count == 3001
    again = scan(lib, "similar")
    assert again.summary["candidate"] == 3001
    assert again.summary["cache_changed"] == 0 and again.summary["index_rebuilt"] == 0
