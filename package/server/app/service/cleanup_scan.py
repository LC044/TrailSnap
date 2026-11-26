"""Checkpointed, bounded-memory toolbox cleanup planning."""
import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.photo import Photo, FileType
from app.db.models.image_vector import ImageVector
from app.db.models.task import Task, TaskType
from app.db.models.user import User
from app.db.models.toolbox import (ToolboxPlan, ToolboxPlanItem, CleanupScope,
    CleanupGroup, CleanupMember, CleanupHash)
from app.schemas.toolbox import PlanRequest, ToolConfig, MediaScope
from app.service.cleanup_resume import RESUMABLE_MODES, catalog_state, frozen_hash_state, request_key
from app.service.toolbox_scope import scope_query, allowed_directory, is_below, canonical

BATCH = 250


class ScanStopped(Exception):
    pass


def enqueue_scan(db, user, request):
    # Validate ownership synchronously; snapshot enumeration is performed by
    # the worker, with an upper ID boundary fixed at acceptance time.
    query = scope_query(db, user, request.scope)
    if request.scope.source == "folders":
        for path in request.scope.folders:
            allowed_directory(db, user, path)
    upper = query.order_by(Photo.id.desc()).with_entities(Photo.id).first()
    reference_upper = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False)).order_by(Photo.id.desc()).first()
    summary = {"total": 0, "processed": 0, "snapshot_upper": str(upper[0]) if upper else None,
               "reference_upper": str(reference_upper[0]) if reference_upper else None, "phase": "snapshot"}
    if request.config.cleanup_mode in RESUMABLE_MODES:
        summary["cleanup_request_key"] = request_key(request)
    plan = ToolboxPlan(id=uuid4(), owner_id=user.id, kind="cleanup", status="scan_queued", version=1,
        request=request.model_dump(mode="json"), summary=summary,
        expires_at=datetime.utcnow() + timedelta(days=7))
    db.add(plan)
    db.flush()
    queue_scan(db, plan)
    return plan


def queue_scan(db, plan):
    task = Task(id=uuid4(), owner_id=plan.owner_id, type=TaskType.SIMILAR_PHOTO_CLUSTERING.value,
        status="pending", priority=10000, total_items=0, processed_items=0,
        payload={"cleanup_scan_id": str(plan.id)})
    db.add(task)
    db.flush()
    plan.task_id = task.id
    plan.status, plan.stop_requested = "scan_queued", False
    plan.summary = {key: value for key, value in plan.summary.items() if key != "error"}
    db.commit()


def checkpoint(db, plan, **values):
    plan.summary = {**plan.summary, **values}
    db.commit()
    db.refresh(plan)
    if plan.stop_requested:
        raise ScanStopped()


def snapshot(db, plan, user, request):
    summary = plan.summary
    # A frozen scope is stored once; resumed scans continue at their last ID.
    upper = summary.get("snapshot_upper")
    cursor = summary.get("snapshot_cursor")
    roots = [allowed_directory(db, user, path) for path in request.scope.folders] if request.scope.source == "folders" else []
    if upper:
        while True:
            query = scope_query(db, user, request.scope).filter(Photo.id <= UUID(upper))
            if cursor:
                query = query.filter(Photo.id > UUID(cursor))
            rows = query.order_by(Photo.id).limit(BATCH).all()
            if not rows:
                break
            existing = {pid for (pid,) in db.query(CleanupScope.photo_id).filter(CleanupScope.plan_id == plan.id,
                CleanupScope.photo_id.in_([p.id for p in rows]))}
            for photo in rows:
                if roots:
                    path = photo.file_path
                    if not any(is_below(path, root) if request.scope.include_children else canonical(os.path.dirname(path)) == root for root in roots):
                        continue
                if photo.id not in existing:
                    db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=True))
            cursor = str(rows[-1].id)
            checkpoint(db, plan, snapshot_cursor=cursor)
    if request.config.compare_all and plan.summary.get("reference_upper"):
        # References are a separate frozen population and never become targets.
        cursor = plan.summary.get("reference_cursor")
        while True:
            query = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False), Photo.file_type == FileType.image,
                Photo.id <= UUID(plan.summary["reference_upper"]))
            if cursor:
                query = query.filter(Photo.id > UUID(cursor))
            rows = query.order_by(Photo.id).limit(BATCH).all()
            if not rows:
                break
            existing = {pid for (pid,) in db.query(CleanupScope.photo_id).filter(CleanupScope.plan_id == plan.id,
                CleanupScope.photo_id.in_([p[0] for p in rows]))}
            for (pid,) in rows:
                if pid not in existing:
                    db.add(CleanupScope(plan_id=plan.id, photo_id=pid, in_scope=False))
            cursor = str(rows[-1][0])
            checkpoint(db, plan, reference_cursor=cursor)
    total = db.query(CleanupScope).filter_by(plan_id=plan.id, in_scope=True).count()
    checkpoint(db, plan, phase="hash" if request.config.cleanup_mode == "duplicate" else "groups", total=total)


def population(db, plan):
    return db.query(Photo).join(CleanupScope, CleanupScope.photo_id == Photo.id).filter(
        CleanupScope.plan_id == plan.id, Photo.owner_id == plan.owner_id,
        Photo.is_deleted.is_(False), Photo.file_type == FileType.image)


def hash_population(db, plan):
    from app.utils.hash import calculate_file_md5
    cursor = plan.summary.get("hash_cursor")
    hashed, reused, failed = (plan.summary.get(k, 0) for k in ("hashed", "hash_reused", "hash_failed"))
    while True:
        query = population(db, plan)
        if cursor:
            query = query.filter(Photo.id > UUID(cursor))
        rows = query.order_by(Photo.id).limit(BATCH).all()
        if not rows:
            break
        cached_hashes = {entry.photo_id: entry for entry in db.query(CleanupHash).filter(CleanupHash.photo_id.in_([row.id for row in rows]))}
        for photo in rows:
            try:
                before = os.stat(photo.file_path)
                path_digest = hashlib.sha256(os.path.abspath(photo.file_path).encode()).hexdigest()
                cached = cached_hashes.get(photo.id)
                valid = cached and cached.path_digest == path_digest and cached.size == str(before.st_size) and cached.mtime_ns == str(before.st_mtime_ns) and cached.md5 == photo.md5
                if valid:
                    reused += 1
                    continue
                md5 = calculate_file_md5(photo.file_path)
                after = os.stat(photo.file_path)
                if not md5 or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise OSError("文件读取失败或扫描期间变化")
                photo.md5 = md5
                db.merge(CleanupHash(photo_id=photo.id, size=str(after.st_size), mtime_ns=str(after.st_mtime_ns), md5=md5, path_digest=path_digest))
                hashed += 1
            except (OSError, ValueError):
                # Never leave a stale hash eligible for deletion.
                photo.md5 = None
                failed += 1
        cursor = str(rows[-1].id)
        checkpoint(db, plan, hash_cursor=cursor, hashed=hashed, hash_reused=reused, hash_failed=failed)
    checkpoint(db, plan, phase="groups")


def add_group(db, plan, key, representative, ids, batch_ids=None, assigned=None):
    # Delay allocating a group until at least two eligible matches exist.
    # Most library photos are singletons: they need no inserts or deletes.
    group = None
    count = 0
    pending = []
    batch = []
    def consume(values):
        nonlocal group, count, pending
        taken = exists().where(CleanupMember.plan_id == plan.id, CleanupMember.photo_id == CleanupScope.photo_id)
        rows = db.query(CleanupScope.photo_id, CleanupScope.in_scope).join(Photo, Photo.id == CleanupScope.photo_id).filter(
            CleanupScope.plan_id == plan.id, CleanupScope.photo_id.in_(values), ~taken,
            Photo.owner_id == plan.owner_id, Photo.is_deleted.is_(False)).all()
        pending.extend(rows)
        if group is None and len(pending) < 2:
            return
        if group is None:
            group = CleanupGroup(plan_id=plan.id, representative_id=representative, key=key, count=0)
            db.add(group)
            db.flush()
        db.add_all([CleanupMember(plan_id=plan.id, photo_id=pid, group_id=group.id, in_scope=inside) for pid, inside in pending])
        if assigned is not None:
            assigned.update(pid for pid, _ in pending if pid in batch_ids)
        count += len(pending)
        pending = []
        db.flush()
    for pid in ids:
        batch.append(UUID(str(pid)))
        if len(batch) == BATCH:
            consume(batch)
            batch = []
    if batch and not (group is None and len(batch) == 1 and batch[0] == representative and not pending):
        consume(batch)
    if group is not None:
        group.count = count
        db.flush()


def duplicate_groups(db, plan):
    cursor = plan.summary.get("group_cursor")
    while True:
        query = population(db, plan).with_entities(Photo.md5).filter(Photo.md5.isnot(None), Photo.md5 != "")
        if cursor:
            query = query.filter(Photo.md5 > cursor)
        keys = query.group_by(Photo.md5).having(func.count() > 1).order_by(Photo.md5).limit(BATCH).all()
        if not keys:
            break
        for (md5,) in keys:
            ids = population(db, plan).with_entities(Photo.id).filter(Photo.md5 == md5).order_by(Photo.id)
            representative = ids.first()[0]
            add_group(db, plan, md5, representative, (row[0] for row in ids.yield_per(BATCH)))
        cursor = keys[-1][0]
        checkpoint(db, plan, group_cursor=cursor)


def similar_groups(db, plan, config):
    from app.service.cleanup_index import CleanupIndex
    models = db.query(ImageVector.model_name).join(Photo).join(CleanupScope, CleanupScope.photo_id == Photo.id).filter(
        CleanupScope.plan_id == plan.id, Photo.owner_id == plan.owner_id, Photo.is_deleted.is_(False),
        ImageVector.model_name.isnot(None)).distinct().order_by(ImageVector.model_name).all()
    previous_model = plan.summary.get("model_cursor", "")
    compared = plan.summary.get("compared", 0)
    for (model,) in models:
        if model < previous_model:
            continue
        with CleanupIndex(db, plan.owner_id, model) as index:
            index.sync(lambda: checkpoint(db, plan))
            if config.scan_mode == "fast":
                index.prepare(lambda: checkpoint(db, plan))
            cursor = plan.summary.get("vector_cursor") if model == previous_model else None
            while True:
                query = population(db, plan).join(ImageVector, ImageVector.photo_id == Photo.id).filter(ImageVector.model_name == model)
                if cursor:
                    query = query.filter(Photo.id > UUID(cursor))
                ids = query.with_entities(Photo.id).order_by(Photo.id).limit(BATCH).all()
                if not ids:
                    break
                batch_ids = {row[0] for row in ids}
                assigned = {pid for (pid,) in db.query(CleanupMember.photo_id).filter(CleanupMember.plan_id == plan.id, CleanupMember.photo_id.in_(batch_ids))}
                for (pid,) in ids:
                    if pid in assigned:
                        compared += 1
                        continue
                    add_group(db, plan, "similar", pid, index.matches(pid, config.similarity, config.scan_mode == "complete"), batch_ids, assigned)
                    compared += 1
                cursor = str(ids[-1][0])
                checkpoint(db, plan, model_cursor=model, vector_cursor=cursor, compared=compared)
            checkpoint(db, plan, cache_changed=plan.summary.get("cache_changed", 0) + index.changed,
                index_rebuilt=plan.summary.get("index_rebuilt", 0) + index.rebuilt,
                invalid_vectors=plan.summary.get("invalid_vectors", 0) + index.invalid)
    embedded = population(db, plan).join(ImageVector, ImageVector.photo_id == Photo.id).count()
    checkpoint(db, plan, missing_vectors=population(db, plan).count() - embedded)


def materialize(db, plan, user, config):
    from app.service.toolbox_plans import item_for_photo
    cursor = plan.summary.get("item_cursor")
    processed = plan.summary.get("processed", 0)
    while True:
        query = db.query(Photo, CleanupMember.group_id, CleanupGroup.key).join(CleanupScope, CleanupScope.photo_id == Photo.id).outerjoin(
            CleanupMember, (CleanupMember.plan_id == plan.id) & (CleanupMember.photo_id == Photo.id)).outerjoin(
            CleanupGroup, CleanupGroup.id == CleanupMember.group_id).filter(CleanupScope.plan_id == plan.id,
                (CleanupMember.group_id.isnot(None) if config.cleanup_mode == "similar" else CleanupScope.in_scope.is_(True)), Photo.owner_id == user.id)
        if cursor:
            query = query.filter(Photo.id > UUID(cursor))
        from app.db.models.face import Face
        rows = query.options(selectinload(Photo.metadata_info), selectinload(Photo.tags),
            selectinload(Photo.faces).selectinload(Face.identity), selectinload(Photo.image_description)).order_by(Photo.id).limit(BATCH).all()
        if not rows:
            break
        for photo, group_id, key in rows:
            candidates = {}
            if group_id and not photo.is_deleted:
                candidates[photo.id] = {"group": str(group_id), "group_id": group_id,
                    "md5": key if config.cleanup_mode == "duplicate" else None, "label": "重复照片" if config.cleanup_mode == "duplicate" else "与代表图相似"}
            elif config.cleanup_mode == "quality" and not photo.is_deleted and photo.image_description:
                score = (photo.image_description.memory_score or 0) + (photo.image_description.quality_score or 0)
                if score <= config.quality_max:
                    candidates[photo.id] = {"group": "quality", "label": f"评分 {score:g}",
                        "quality_score": photo.image_description.quality_score or 0, "memory_score": photo.image_description.memory_score or 0}
            if candidates:
                item = item_for_photo(db, user, photo, config, 0, set(), candidates, None)
                item.plan_id = plan.id
                db.add(item)
            processed += 1
        cursor = str(rows[-1][0].id)
        checkpoint(db, plan, item_cursor=cursor, processed=processed)
    counts = dict(db.query(ToolboxPlanItem.status, func.count()).filter_by(plan_id=plan.id).group_by(ToolboxPlanItem.status).all())
    plan.status = "preview"
    plan.expires_at = datetime.utcnow() + timedelta(days=7)
    if config.cleanup_mode == "similar":
        # Similar groups explicitly include all members, including comparison-only photos.
        plan.summary = {**plan.summary, "total": processed}
    plan.summary = {**plan.summary, "phase": "done", "candidate": counts.get("candidate", 0),
        "skipped": plan.summary.get("total", 0) - counts.get("candidate", 0), "groups": db.query(CleanupGroup).filter_by(plan_id=plan.id).count(), "ready": 0}
    db.commit()


def run_scan(db, plan_id):
    plan = db.get(ToolboxPlan, plan_id)
    if not plan or plan.status not in {"scan_queued", "scanning"}:
        return {"status": "completed"}
    user = db.get(User, plan.owner_id)
    request = PlanRequest.model_validate(plan.request)
    plan.status = "scanning"
    plan.summary = {key: value for key, value in plan.summary.items() if key != "error"}
    db.commit()
    try:
        checkpoint(db, plan)
        if plan.summary["phase"] == "snapshot":
            if plan.summary.get("cleanup_request_key") and not plan.summary.get("catalog_state"):
                checkpoint(db, plan, catalog_state=catalog_state(db, user, request, snapshot=plan.summary))
            snapshot(db, plan, user, request)
        if plan.summary["phase"] == "hash":
            hash_population(db, plan)
        if plan.summary["phase"] == "groups":
            if request.config.cleanup_mode == "duplicate":
                duplicate_groups(db, plan)
                if plan.summary.get("catalog_state"):
                    checkpoint(db, plan, catalog_state={**plan.summary["catalog_state"],
                        **frozen_hash_state(db, plan, request.config.compare_all)})
            elif request.config.cleanup_mode == "similar":
                similar_groups(db, plan, request.config)
            checkpoint(db, plan, phase="items")
        materialize(db, plan, user, request.config)
    except ScanStopped:
        plan.status = "scan_stopped"
        db.commit()
    except Exception as error:
        db.rollback()
        db.refresh(plan)
        plan.status = "scan_failed"
        plan.summary = {**plan.summary, "error": str(error)}
        db.commit()
        raise
    return {"status": "completed", "plan_id": str(plan.id)}


async def process_scan(task, db):
    bind = db.get_bind()
    plan_id = UUID(task.payload["cleanup_scan_id"])
    # The CPU worker must yield the event loop so stop/progress remain usable.
    def run():
        with Session(bind, expire_on_commit=False) as session:
            return run_scan(session, plan_id)
    return await asyncio.to_thread(run)
