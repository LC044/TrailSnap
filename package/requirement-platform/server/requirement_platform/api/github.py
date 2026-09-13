import json
import secrets

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..delivery import requirement_transition
from ..domain import requirements as requirement_service
from ..domain.common import audit, enqueue
from ..integrations.github import (
    closing_issue_numbers, pull_request_summary, requirement_status_from_github, verify_webhook,
)
from ..models import (
    DeliveryTask, GitHubIdentity, PullRequestLink, Requirement, RequirementFollower, User, WebhookEvent,
)
from ..presenters import requirement_data
from ..schemas import GitHubIssueLinkInput, ReasonInput
from ..security import manager
from ..services import GitHubClient
from .responses import ok

router = APIRouter(tags=["github"])


def enqueue_github_sync(db: Session, row: Requirement) -> None:
    requirement_service.enqueue_github_sync(db, row, unique_suffix=secrets.token_hex(6))


def next_requirement_number(db: Session) -> int:
    return (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1


def apply_github_status(
    db: Session, row: Requirement, issue: dict, *, action: str | None = None,
    changed_label: str | None = None, actor_id: str | None = None, actor_name: str = "GitHub",
    source: str = "github",
) -> bool:
    row.github_state = issue.get("state", row.github_state)
    suggested = requirement_status_from_github(issue, current_status=row.status, action=action, changed_label=changed_label)
    before = row.status
    changed = suggested != before
    if changed:
        requirement_transition(
            db, row, suggested, actor_id=actor_id,
            reason=f"GitHub Issue 状态同步为 {issue.get('state', 'unknown')}", source=source,
        )
    audit(
        db, actor_id, "github.requirement_state_observed", "requirement", row.id,
        platform_status=row.status, suggested_status=suggested, github_state=row.github_state,
        source=source, actor_name=actor_name, github_action=action,
    )
    return changed


@router.post("/api/requirements/{requirement_id}/github/create")
def create_requirement_github_issue(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.github_issue_number:
        raise HTTPException(status_code=409, detail="Requirement already has a GitHub issue")
    try:
        data = GitHubClient().create_issue(row)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub issue creation failed: {exc}") from exc
    row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
    enqueue_github_sync(db, row)
    audit(db, actor.id, "github.issue.created", "requirement", row.id, issue_number=data["number"])
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@router.post("/api/admin/github/issues/sync")
def import_github_issues(actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        issues = GitHubClient().list_issues()
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub Issue 同步失败：{exc}") from exc
    created = updated = skipped = 0
    for issue in issues:
        number = issue.get("number")
        if not number:
            skipped += 1
            continue
        label_names = [label.get("name", "") if isinstance(label, dict) else str(label) for label in issue.get("labels", [])]
        kind = "bug" if any(name.lower() == "bug" for name in label_names) else (
            "feature" if any(name.lower() in {"enhancement", "feature"} for name in label_names) else "improvement"
        )
        row = db.query(Requirement).filter(Requirement.github_issue_number == number).first()
        if row:
            row.github_issue_url = issue.get("html_url")
            if row.source == "github":
                row.title = (issue.get("title") or f"GitHub Issue #{number}")[:160]
                row.description = ((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000]
                row.type = kind
            apply_github_status(
                db, row, issue, actor_id=actor.id, actor_name=actor.username, source="github_manual_sync",
            )
            updated += 1
            continue
        row = Requirement(
            public_number=next_requirement_number(db),
            type=kind, title=(issue.get("title") or f"GitHub Issue #{number}")[:160],
            description=((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000],
            severity="medium", visibility="public", status="submitted", source="github", created_by=actor.id,
            github_issue_number=number, github_issue_url=issue.get("html_url"), github_state=issue.get("state"),
        )
        db.add(row)
        db.flush()
        db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
        apply_github_status(
            db, row, issue, actor_id=actor.id, actor_name=actor.username, source="github_manual_sync",
        )
        if row.status == "submitted":
            enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "github.issue.imported", "requirement", row.id, issue_number=number)
        created += 1
    audit(db, actor.id, "github.issues.synchronized", "github_repository", settings.github_repo,
          created=created, updated=updated, skipped=skipped, total=len(issues))
    db.commit()
    return ok({"created": created, "updated": updated, "skipped": skipped, "total": len(issues)})


@router.post("/api/requirements/{requirement_id}/github/link")
def link_requirement_github_issue(requirement_id: str, payload: GitHubIssueLinkInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    other = db.query(Requirement).filter(Requirement.github_issue_number == payload.issue_number, Requirement.id != row.id).first()
    if other:
        raise HTTPException(status_code=409, detail="GitHub issue is already linked to another requirement")
    try:
        data = GitHubClient().get_issue(payload.issue_number)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub issue lookup failed: {exc}") from exc
    row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
    apply_github_status(db, row, data, actor_id=actor.id, actor_name=actor.username, source="github_link")
    enqueue_github_sync(db, row)
    audit(db, actor.id, "github.issue.linked", "requirement", row.id, issue_number=data["number"])
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@router.delete("/api/requirements/{requirement_id}/github/link")
def unlink_requirement_github_issue(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or not row.github_issue_number:
        raise HTTPException(status_code=404, detail="Linked GitHub issue not found")
    issue_number = row.github_issue_number
    row.github_issue_number, row.github_issue_url, row.github_state = None, None, None
    audit(db, actor.id, "github.issue.unlinked", "requirement", row.id, issue_number=issue_number)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@router.post("/api/requirements/{requirement_id}/github/close")
def close_requirement_github_issue(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or not row.github_issue_number:
        raise HTTPException(status_code=404, detail="Linked GitHub issue not found")
    data = GitHubClient().update_issue_state(row.github_issue_number, "closed")
    row.github_state = data.get("state", "closed")
    audit(db, actor.id, "github.issue.closed", "requirement", row.id, platform_status=row.status,
          issue_number=row.github_issue_number, reason=payload.reason, source="platform")
    db.commit()
    return ok(requirement_data(row, db, include_private=True))




@router.post("/api/hooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not verify_webhook(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    delivery_id = x_github_delivery or ""
    if not delivery_id:
        raise HTTPException(status_code=400, detail="Missing delivery id")
    if db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first():
        return ok({"duplicate": True})
    payload = json.loads(body)
    event = WebhookEvent(delivery_id=delivery_id, event_type=x_github_event or "unknown", payload=payload)
    db.add(event)
    if x_github_event == "issues":
        issue = payload.get("issue") or {}
        row = db.query(Requirement).filter(Requirement.github_issue_number == issue.get("number")).first()
        if row:
            sender = payload.get("sender") or {}
            identity = db.query(GitHubIdentity).filter(GitHubIdentity.github_user_id == sender.get("id")).first()
            action = payload.get("action")
            changed_label = (payload.get("label") or {}).get("name")
            if action in {"closed", "reopened", "labeled", "unlabeled"}:
                changed = apply_github_status(
                    db, row, issue, action=action, changed_label=changed_label,
                    actor_id=identity.user_id if identity else None,
                    actor_name=f"GitHub @{sender.get('login', 'unknown')}", source="github_webhook",
                )
            else:
                row.github_state = issue.get("state", row.github_state)
                changed = False
            if changed:
                enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:webhook:{delivery_id}")
    elif x_github_event == "pull_request":
        pull_request = payload.get("pull_request") or {}
        pull_request_number = pull_request.get("number") or payload.get("number")
        linked_issue_numbers = closing_issue_numbers(pull_request)
        if pull_request_number:
            summary = pull_request_summary({**pull_request, "number": pull_request_number})
            delivery_link = db.query(PullRequestLink).filter(
                PullRequestLink.repository == settings.github_repo,
                PullRequestLink.pull_request_number == pull_request_number,
            ).first()
            if delivery_link:
                delivery_link.url = summary.get("url") or delivery_link.url
                delivery_link.head_sha = str((pull_request.get("head") or {}).get("sha") or delivery_link.head_sha)
                delivery_link.state = summary["state"]
                task = db.query(DeliveryTask).filter(DeliveryTask.id == delivery_link.task_id).one()
                if summary["state"] == "merged" and task.state != "merged":
                    task.state, task.state_version = "merged", task.state_version + 1
                    requirement = db.query(Requirement).filter(Requirement.id == task.requirement_id).one()
                    requirement_transition(db, requirement, "merged", actor_id=None,
                                           reason=f"关联 PR #{pull_request_number} 已合并，等待版本发布",
                                           source="github_pull_request_webhook")
            linked_rows = db.query(Requirement).filter(
                Requirement.github_issue_number.is_not(None), Requirement.deleted_at.is_(None)
            ).all()
            for row in linked_rows:
                related = [
                    item for item in (row.github_pull_requests or [])
                    if item.get("number") != pull_request_number
                ]
                is_linked = row.github_issue_number in linked_issue_numbers
                if is_linked:
                    related.append(summary)
                    related.sort(key=lambda item: item.get("number") or 0, reverse=True)
                if related != (row.github_pull_requests or []):
                    was_linked = any(
                        item.get("number") == pull_request_number for item in (row.github_pull_requests or [])
                    )
                    row.github_pull_requests = related
                    audit(
                        db, None,
                        "github.pull_request.updated" if is_linked else "github.pull_request.unlinked",
                        "requirement", row.id, source="github_webhook",
                        pull_request_number=pull_request_number, pull_request_url=summary.get("url"),
                        newly_linked=is_linked and not was_linked,
                    )
                if is_linked and summary["state"] == "merged":
                    audit(db, None, "github.pull_request.merged", "requirement", row.id,
                          source="github_pull_request_webhook", pull_request_number=pull_request_number)
    event.processed = True
    db.commit()
    return ok({"accepted": True})
