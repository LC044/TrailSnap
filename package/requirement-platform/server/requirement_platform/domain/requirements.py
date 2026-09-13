"""Requirement business rules shared by every transport."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..delivery import DomainConflict, requirement_transition
from ..models import (
    DeliveryTask,
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementFollower,
    ReviewDecision,
)
from .common import audit, enqueue


class RequirementNotFound(ValueError):
    pass


def get_requirement(db: Session, requirement_id: str, *, include_deleted: bool = False) -> Requirement:
    number_text = requirement_id.upper().removeprefix("REQ-").lstrip("0") or "0"
    query = db.query(Requirement)
    if number_text.isdigit():
        query = query.filter(Requirement.public_number == int(number_text))
    else:
        query = query.filter(Requirement.id == requirement_id)
    if not include_deleted:
        query = query.filter(Requirement.deleted_at.is_(None))
    row = query.first()
    if not row:
        raise RequirementNotFound("Requirement not found")
    return row


def enqueue_github_sync(db: Session, row: Requirement, *, unique_suffix: str) -> None:
    if row.github_issue_number or (row.visibility == "public" and row.status == "candidate"):
        enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:{row.status}:{unique_suffix}")


def review_requirement(
    db: Session,
    row: Requirement,
    *,
    actor_id: str,
    action: str,
    reason: str,
    priority: str,
    risk_level: str,
    duplicate_of_id: str | None,
    source: str,
    sync_suffix: str,
) -> Requirement:
    statuses = {
        "candidate": "candidate",
        "needs_information": "needs_information",
        "rejected": "rejected",
        "deferred": "deferred",
        "duplicate": "duplicate",
        "close": "closed",
    }
    if action not in statuses or len(reason.strip()) < 2:
        raise ValueError("审核动作或理由无效")
    if priority not in {"low", "normal", "high", "urgent"}:
        raise ValueError("优先级无效")
    if risk_level not in {"low", "medium", "high", "critical"}:
        raise ValueError("风险等级无效")

    if action == "duplicate":
        target = get_requirement(db, duplicate_of_id or "")
        if target.id == row.id:
            raise ValueError("重复需求不能指向自身")
        row.duplicate_of_id = target.id
        followers = db.query(RequirementFollower).filter(RequirementFollower.requirement_id == row.id).all()
        for follower in followers:
            exists = db.query(RequirementFollower).filter(
                RequirementFollower.requirement_id == target.id,
                RequirementFollower.user_id == follower.user_id,
            ).first()
            if not exists:
                db.add(RequirementFollower(requirement_id=target.id, user_id=follower.user_id))

    before = row.status
    reason = reason.strip()
    requirement_transition(db, row, statuses[action], actor_id=actor_id, reason=reason, source=source)
    row.review_reason = reason
    row.priority = priority
    row.risk_level = risk_level
    db.add(ReviewDecision(
        requirement_id=row.id,
        reviewer_id=actor_id,
        action=action,
        reason=reason,
        metadata_json={
            "source": source,
            "priority": priority,
            "risk_level": risk_level,
            "duplicate_of_id": duplicate_of_id,
        },
    ))
    enqueue_github_sync(db, row, unique_suffix=sync_suffix)
    audit(
        db,
        actor_id,
        f"requirement.{action}",
        "requirement",
        row.id,
        source=source,
        reason=reason,
        before=before,
        after=row.status,
    )
    return row


def change_requirement_status(
    db: Session,
    row: Requirement,
    *,
    actor_id: str,
    status: str,
    reason: str,
    source: str,
    sync_suffix: str,
) -> Requirement:
    if status in {"accepted", "developing", "testing", "release_ready", "merged", "released"} and db.query(
        DeliveryTask.id
    ).filter(DeliveryTask.requirement_id == row.id).first():
        raise DomainConflict(
            "新交付任务的状态只能由规格、执行、PR 和发布事实推进",
            current_version=row.state_version,
        )
    requirement_transition(db, row, status, actor_id=actor_id, reason=reason.strip(), source=source)
    row.review_reason = reason.strip()
    enqueue_github_sync(db, row, unique_suffix=sync_suffix)
    return row


def soft_delete_requirement(
    db: Session, row: Requirement, *, actor_id: str, reason: str, source: str
) -> Requirement:
    active_batch = db.query(ReleaseBatchItem).join(
        ReleaseBatch, ReleaseBatch.id == ReleaseBatchItem.batch_id
    ).filter(
        ReleaseBatchItem.requirement_id == row.id,
        ReleaseBatch.status.notin_({"completed", "cancelled"}),
        ReleaseBatchItem.delivery_status != "removed",
    ).first()
    if active_batch:
        raise DomainConflict("需求仍在活动版本中，请先移出版本", current_version=row.state_version)
    row.deleted_at = datetime.now(timezone.utc)
    row.deleted_by = actor_id
    row.delete_reason = reason.strip()
    audit(db, actor_id, "requirement.deleted", "requirement", row.id, source=source, reason=reason.strip())
    return row


def restore_requirement(db: Session, row: Requirement, *, actor_id: str, source: str) -> Requirement:
    if not row.deleted_at:
        raise DomainConflict("需求未被删除", current_version=row.state_version)
    row.deleted_at = None
    row.deleted_by = None
    row.delete_reason = None
    audit(db, actor_id, "requirement.restored", "requirement", row.id, source=source)
    return row
