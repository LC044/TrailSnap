"""Reuse a saved cleanup preview when its catalog inputs still match."""
import hashlib
import json
import os
from datetime import datetime
from uuid import UUID

from sqlalchemy import false

from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, Photo
from app.db.models.toolbox import CleanupScope, ToolboxPlan
from app.schemas.toolbox import PlanRequest
from app.service.toolbox_scope import allowed_directory, canonical, is_below, scope_query


RESUMABLE_MODES = ("duplicate", "similar")


def request_key(request):
    scope = request.scope.model_dump(mode="json")
    for field, source in (("album_ids", "albums"), ("photo_ids", "selected"), ("folders", "folders")):
        scope[field] = sorted(set(scope[field])) if scope["source"] == source else []
    scope["excluded_ids"] = sorted(set(scope["excluded_ids"]))
    scope["include_children"] = scope["source"] == "folders" and scope["include_children"]
    filters = {key: sorted(set(values)) for key, values in (scope.pop("filters", None) or {}).items() if values}
    if filters:
        scope["filters"] = filters
    config = request.config
    comparison = {"mode": config.cleanup_mode, "compare_all": config.compare_all}
    if config.cleanup_mode == "similar":
        comparison.update(similarity=config.similarity, scan_mode=config.scan_mode)
    return hashlib.sha256(json.dumps([scope, comparison], sort_keys=True).encode()).hexdigest()


def digest_rows(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(tuple(row), default=str).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def boundary(query, snapshot, key):
    if snapshot is None:
        return query
    upper = snapshot.get(key)
    return query.filter(Photo.id <= UUID(upper) if upper else false())


def current_scope(db, user, scope, snapshot):
    query = scope_query(db, user, scope).filter(Photo.file_type == FileType.image)
    query = boundary(query, snapshot, "snapshot_upper")
    roots = [allowed_directory(db, user, path) for path in scope.folders] if scope.source == "folders" else []
    if roots:
        # Keep exactly the same canonical folder rules as the scan snapshot.
        for photo in query.order_by(Photo.id).yield_per(250):
            path = photo.file_path
            if any(is_below(path, root) if scope.include_children else canonical(os.path.dirname(path)) == root for root in roots):
                yield photo.id, path, photo.size, photo.md5
    else:
        yield from query.with_entities(Photo.id, Photo.file_path, Photo.size, Photo.md5).order_by(Photo.id).yield_per(250)


def catalog_state(db, user, request, *, snapshot=None, include_hashes=False):
    scope = request.scope
    config = request.config
    scope_digest = hashlib.sha256()
    hash_digest = hashlib.sha256()
    for photo_id, path, size, md5 in current_scope(db, user, scope, snapshot):
        scope_digest.update(json.dumps([str(photo_id), path, size]).encode() + b"\n")
        if include_hashes:
            hash_digest.update(json.dumps([str(photo_id), md5]).encode() + b"\n")
    state = {"scope": scope_digest.hexdigest()}
    if config.cleanup_mode == "similar":
        rows = db.query(ImageVector.photo_id, ImageVector.model_name, ImageVector.content_revision).join(Photo).filter(
            Photo.owner_id == user.id, Photo.is_deleted.is_(False), Photo.file_type == FileType.image,
            ImageVector.model_name.isnot(None),
        ).order_by(ImageVector.photo_id).yield_per(250)
        state["vectors"] = digest_rows(rows)
    elif include_hashes:
        state["hashes"] = hash_digest.hexdigest()
    if config.compare_all:
        references = db.query(Photo.id, Photo.file_path, Photo.size).filter(
            Photo.owner_id == user.id, Photo.is_deleted.is_(False), Photo.file_type == FileType.image,
        )
        references = boundary(references, snapshot, "reference_upper").order_by(Photo.id)
        state["references"] = digest_rows(references.yield_per(250))
        if include_hashes:
            state["reference_hashes"] = digest_rows(references.with_entities(Photo.id, Photo.md5).yield_per(250))
    return state


def frozen_hash_state(db, plan, compare_all):
    hashes = db.query(Photo.id, Photo.md5).join(CleanupScope, CleanupScope.photo_id == Photo.id).filter(
        CleanupScope.plan_id == plan.id, Photo.owner_id == plan.owner_id,
        Photo.is_deleted.is_(False), Photo.file_type == FileType.image,
    ).order_by(Photo.id)
    state = {"hashes": digest_rows(hashes.filter(CleanupScope.in_scope.is_(True)).yield_per(250))}
    if compare_all:
        state["reference_hashes"] = digest_rows(hashes.yield_per(250))
    return state


def freshness(db, user, plan):
    if plan.status != "preview" or plan.request.get("config", {}).get("cleanup_mode") not in RESUMABLE_MODES:
        return None
    if plan.expires_at <= datetime.utcnow():
        return "expired"
    saved = plan.summary.get("catalog_state")
    if not saved:
        return "unknown"
    try:
        request = PlanRequest.model_validate(plan.request)
        if request.config.cleanup_mode == "duplicate" and "hashes" not in saved:
            return "unknown"
        current = catalog_state(db, user, request, include_hashes="hashes" in saved)
        if current != saved:
            return "changed"
        return "unknown" if plan.summary.get("hash_failed") else "current"
    except (ValueError, OSError):
        return "changed"


def previews(db, user, mode):
    return db.query(ToolboxPlan).filter(
        ToolboxPlan.owner_id == user.id, ToolboxPlan.kind == "cleanup",
        ToolboxPlan.status == "preview", ToolboxPlan.expires_at > datetime.utcnow(),
        ToolboxPlan.request["config"]["cleanup_mode"].as_string() == mode,
    ).order_by(ToolboxPlan.created_at.desc(), ToolboxPlan.id.desc())


def latest_preview(db, user, mode):
    return previews(db, user, mode).filter(ToolboxPlan.summary["candidate"].as_integer() > 0).first()


def reusable_preview(db, user, request):
    plan = previews(db, user, request.config.cleanup_mode).filter(
        ToolboxPlan.summary["cleanup_request_key"].as_string() == request_key(request),
    ).first()
    return plan if plan and freshness(db, user, plan) == "current" else None
