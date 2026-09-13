"""Release-batch business rules shared by HTTP and MCP adapters."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..delivery import DomainConflict, requirement_transition
from ..models import DeliveryTask, ReleaseBatch, ReleaseBatchItem, Requirement, utcnow
from .common import audit, enqueue, requirement_snapshot
from .requirements import enqueue_github_sync, get_requirement


class ReleaseNotFound(ValueError):
    pass


TRANSITIONS = {
    "planning": {"cancelled"},
    "candidate_selection": {"cancelled"},
    "scope_locked": {"developing", "blocked", "paused", "cancelled"},
    "developing": {"testing", "blocked", "paused", "cancelled"},
    "testing": {"developing", "release_ready", "blocked", "paused", "cancelled"},
    "release_ready": {"testing", "published", "blocked", "paused", "cancelled"},
    "published": {"completed"},
    "blocked": {"developing", "testing", "release_ready", "paused", "cancelled"},
    "paused": {"developing", "testing", "release_ready", "blocked", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def get_batch(db: Session, batch_id: str) -> ReleaseBatch:
    row = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    if not row:
        raise ReleaseNotFound("Version batch not found")
    return row


def add_item(
    db: Session,
    batch: ReleaseBatch,
    requirement: Requirement,
    *,
    actor_id: str,
    priority_order: int,
    source: str,
) -> ReleaseBatchItem:
    if batch.status not in {"planning", "candidate_selection"}:
        raise DomainConflict("Version scope is locked")
    if requirement.status not in {"candidate", "scheduled"}:
        raise DomainConflict("Only candidate requirements can be scheduled")
    risk_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    if risk_rank.get(requirement.risk_level, 4) > risk_rank.get(batch.max_risk_level, 3):
        raise DomainConflict("Requirement risk exceeds the version batch limit")
    if db.query(ReleaseBatchItem.id).filter(
        ReleaseBatchItem.batch_id == batch.id,
        ReleaseBatchItem.requirement_id == requirement.id,
    ).first():
        raise DomainConflict("Requirement is already in this batch")
    item = ReleaseBatchItem(
        batch_id=batch.id,
        requirement_id=requirement.id,
        priority_order=max(priority_order, 0),
        requirement_snapshot=requirement_snapshot(requirement),
    )
    db.add(item)
    batch.status = "candidate_selection"
    audit(db, actor_id, "release_batch.item_added", "release_batch", batch.id,
          source=source, requirement_id=requirement.id)
    return item


def remove_item(
    db: Session, batch: ReleaseBatch, item: ReleaseBatchItem, *, actor_id: str, source: str
) -> None:
    if batch.status not in {"planning", "candidate_selection"}:
        raise DomainConflict("Version scope is locked")
    audit(db, actor_id, "release_batch.item_removed", "release_batch", batch.id,
          source=source, requirement_id=item.requirement_id)
    db.delete(item)


def lock_batch(db: Session, batch: ReleaseBatch, *, actor_id: str, source: str) -> ReleaseBatch:
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id).all()
    if not items:
        raise DomainConflict("Version batch has no requirements")
    if batch.status not in {"planning", "candidate_selection"}:
        raise DomainConflict("Version scope is already locked")
    batch.status = "scope_locked"
    batch.locked_at = utcnow()
    for item in items:
        requirement = get_requirement(db, item.requirement_id)
        item.requirement_snapshot = requirement_snapshot(requirement)
        requirement_transition(
            db, requirement, "scheduled", actor_id=actor_id,
            reason=f"加入版本 {batch.version_name}", source=source,
        )
        enqueue_github_sync(db, requirement, unique_suffix=f"batch:{batch.id}")
    enqueue(db, "github_milestone", batch.id, f"github_milestone:{batch.id}")
    audit(db, actor_id, "release_batch.locked", "release_batch", batch.id,
          source=source, count=len(items))
    return batch


def change_status(
    db: Session,
    batch: ReleaseBatch,
    *,
    actor_id: str,
    actor_role: str,
    status: str,
    reason: str,
    source: str,
) -> ReleaseBatch:
    before = batch.status
    if status != before and status not in TRANSITIONS.get(before, set()):
        raise DomainConflict(f"Invalid version transition: {before} -> {status}")
    if status in {"completed", "cancelled"} and actor_role != "owner":
        raise PermissionError("Only the owner can complete or cancel a version")
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id).all()
    if status == "published" and any(item.delivery_status not in {"completed", "removed"} for item in items):
        raise DomainConflict("All included requirements must be completed before publishing")
    batch.status = status
    target = {
        "developing": "developing",
        "testing": "testing",
        "release_ready": "release_ready",
        "published": "released",
        "completed": "released",
    }.get(status)
    if target:
        for item in items:
            if target == "released" and item.delivery_status != "completed":
                continue
            requirement = get_requirement(db, item.requirement_id)
            if db.query(DeliveryTask.id).filter(DeliveryTask.requirement_id == requirement.id).first():
                raise DomainConflict("新交付任务不能由旧版本状态接口推进", current_version=requirement.state_version)
            requirement_transition(db, requirement, target, actor_id=actor_id, reason=reason, source=source)
            enqueue_github_sync(db, requirement, unique_suffix=f"batch:{batch.id}:{status}")
    audit(db, actor_id, "release_batch.status_changed", "release_batch", batch.id,
          source=source, before=before, after=status, reason=reason)
    return batch


def change_delivery_status(
    db: Session,
    batch: ReleaseBatch,
    item: ReleaseBatchItem,
    *,
    actor_id: str,
    status: str,
    source: str,
) -> ReleaseBatchItem:
    allowed = {"not_started", "developing", "pr_open", "testing", "completed", "blocked", "removed"}
    if status not in allowed:
        raise ValueError("Invalid delivery status")
    if batch.status in {"planning", "candidate_selection"}:
        raise DomainConflict("Lock the version scope before updating delivery status")
    if batch.status in {"published", "completed", "cancelled"}:
        raise DomainConflict("Version delivery status is no longer editable")
    item.delivery_status = status
    target = {"developing": "developing", "pr_open": "developing", "testing": "testing", "completed": "release_ready"}.get(status)
    if target:
        requirement = get_requirement(db, item.requirement_id)
        if db.query(DeliveryTask.id).filter(DeliveryTask.requirement_id == requirement.id).first():
            raise DomainConflict("新交付任务不能由旧版本条目接口推进", current_version=requirement.state_version)
        requirement_transition(db, requirement, target, actor_id=actor_id,
                               reason=f"版本交付状态：{status}", source=source)
        enqueue_github_sync(db, requirement, unique_suffix=f"batch-item:{item.id}:{status}")
    audit(db, actor_id, "release_batch.delivery_status", "release_batch", batch.id,
          source=source, item_id=item.id, status=status)
    return item
