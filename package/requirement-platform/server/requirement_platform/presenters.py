"""Read-model presenters used by HTTP endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import func
from sqlalchemy.orm import Session

from .delivery import spec_dict, task_dict
from .models import (
    ClarificationQuestion,
    DeliveryTask,
    GitHubIdentity,
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementAttachment,
    RequirementFollower,
    RequirementSpec,
    TriageReport,
    User,
)
from .schemas import BatchRead, GitHubIdentityRead, RequirementRead, UserRead


@dataclass(frozen=True)
class RequirementListContext:
    creator_names: dict[str, str]
    follower_counts: dict[str, int]
    latest_reports: dict[str, TriageReport]


def requirement_list_context(db: Session, rows: list[Requirement]) -> RequirementListContext:
    ids = [row.id for row in rows]
    creator_ids = {row.created_by for row in rows if row.created_by}
    creator_names = dict(db.query(User.id, User.username).filter(User.id.in_(creator_ids)).all()) if creator_ids else {}
    follower_counts = {
        requirement_id: count for requirement_id, count in db.query(
            RequirementFollower.requirement_id, func.count(RequirementFollower.id)
        ).filter(RequirementFollower.requirement_id.in_(ids)).group_by(RequirementFollower.requirement_id).all()
    } if ids else {}
    latest_reports: dict[str, TriageReport] = {}
    if ids:
        reports = db.query(TriageReport).filter(TriageReport.requirement_id.in_(ids)).order_by(
            TriageReport.requirement_id, TriageReport.created_at.desc()
        ).all()
        for report in reports:
            latest_reports.setdefault(report.requirement_id, report)
    return RequirementListContext(creator_names, follower_counts, latest_reports)


def user_data(row: User, db: Session) -> dict:
    data = UserRead.model_validate(row).model_dump(mode="json")
    identity = db.query(GitHubIdentity).filter(GitHubIdentity.user_id == row.id).first()
    data["github"] = GitHubIdentityRead.model_validate(identity).model_dump(mode="json") if identity else None
    return data


def requirement_data(
    row: Requirement,
    db: Session,
    *,
    include_private: bool = False,
    include_contact: bool = False,
    list_context: RequirementListContext | None = None,
) -> dict:
    data = RequirementRead.model_validate(row).model_dump(mode="json")
    if not include_private:
        data["log_text"] = None
    creator = (
        list_context.creator_names.get(row.created_by or "")
        if list_context is not None
        else db.query(User.username).filter(User.id == row.created_by).scalar() if row.created_by else None
    )
    data["created_by_name"] = creator or row.submitter_name or "匿名用户"
    if not include_contact:
        data["submitter_contact"] = None
    data["follower_count"] = (
        list_context.follower_counts.get(row.id, 0)
        if list_context is not None
        else db.query(func.count(RequirementFollower.id)).filter(
            RequirementFollower.requirement_id == row.id
        ).scalar() or 0
    )
    report = (
        list_context.latest_reports.get(row.id)
        if list_context is not None
        else db.query(TriageReport).filter(TriageReport.requirement_id == row.id).order_by(
            TriageReport.created_at.desc()
        ).first()
    )
    if report:
        public_fields = {
            "schema_version", "problem_summary", "category", "completeness_items",
            "duplicate_candidates", "recommended_disposition", "acceptance_draft", "fallback_reason",
        }
        data["triage"] = report.report if include_private else {
            key: value for key, value in report.report.items() if key in public_fields
        }
        data["triage_provider"] = report.provider if include_private else None
        data["triage_model"] = report.model if include_private else None
    else:
        data["triage"] = None
        data["triage_provider"] = None
        data["triage_model"] = None
    attachments = db.query(RequirementAttachment).filter(
        RequirementAttachment.requirement_id == row.id
    ).order_by(RequirementAttachment.created_at).all() if include_private else []
    data["attachments"] = [{
        "id": item.id,
        "name": item.original_name,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "kind": item.kind,
        "content_sha256": item.content_sha256,
        "processing_status": item.processing_status,
        "processing_error": item.processing_error,
        "created_at": item.created_at.isoformat(),
        "download_url": f"/api/requirements/{row.id}/attachments/{item.id}",
    } for item in attachments]
    questions = db.query(ClarificationQuestion).filter(
        ClarificationQuestion.requirement_id == row.id
    ).order_by(ClarificationQuestion.created_at).all()
    if row.created_by is not None and include_private:
        data["clarifications"] = [{
            "id": item.id,
            "question_id": item.question_id,
            "target_field": item.target_field,
            "question": item.question,
            "rationale": item.rationale,
            "blocking": item.blocking,
            "suggested_options": item.suggested_options,
            "status": item.status,
            "answer": item.answer,
            "round_number": item.round_number,
        } for item in questions]
    else:
        data["clarifications"] = []
    if include_private:
        specs = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == row.id).order_by(
            RequirementSpec.revision.desc()
        ).all()
        data["specs"] = [spec_dict(db, item) for item in specs]
        tasks = db.query(DeliveryTask).filter(DeliveryTask.requirement_id == row.id).order_by(
            DeliveryTask.created_at.desc()
        ).all()
        data["delivery_tasks"] = [task_dict(db, item) for item in tasks]
    return data


def batch_data(row: ReleaseBatch, db: Session, *, include_private: bool = False) -> dict:
    data = BatchRead.model_validate(row).model_dump(mode="json")
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == row.id).order_by(
        ReleaseBatchItem.priority_order, ReleaseBatchItem.created_at
    ).all()
    data["items"] = []
    for item in items:
        snapshot = item.requirement_snapshot
        if snapshot.get("visibility") == "private" and not include_private:
            snapshot = {
                "id": snapshot.get("id"),
                "title": "私密需求",
                "type": snapshot.get("type"),
                "status": snapshot.get("status"),
                "visibility": "private",
            }
        data["items"].append({
            "id": item.id,
            "requirement_id": item.requirement_id,
            "priority_order": item.priority_order,
            "delivery_status": item.delivery_status,
            "requirement_snapshot": snapshot,
        })
    return data
