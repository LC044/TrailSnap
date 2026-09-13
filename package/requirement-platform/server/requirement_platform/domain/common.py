"""Small persistence helpers shared across domain use cases."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent, BackgroundJob, Requirement


def requirement_snapshot(row: Requirement) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "description": row.description,
        "current_behavior": row.current_behavior,
        "expected_behavior": row.expected_behavior,
        "steps_to_reproduce": row.steps_to_reproduce,
        "severity": row.severity,
        "product_version": row.product_version,
        "environment": row.environment,
        "visibility": row.visibility,
        "status": row.status,
        "priority": row.priority,
        "risk_level": row.risk_level,
        "version": row.version,
        "content_revision": row.content_revision,
    }


def audit(db: Session, actor_id: str | None, action: str, object_type: str, object_id: str, **details) -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, object_type=object_type, object_id=object_id, details=details))


def enqueue(db: Session, job_type: str, object_id: str, key: str, payload: dict | None = None) -> BackgroundJob:
    existing = db.query(BackgroundJob).filter(BackgroundJob.idempotency_key == key).first()
    if existing:
        return existing
    job = BackgroundJob(job_type=job_type, object_id=object_id, payload=payload or {}, idempotency_key=key)
    db.add(job)
    return job


def retry_at(attempts: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=min(3600, 2 ** min(attempts, 10)))
