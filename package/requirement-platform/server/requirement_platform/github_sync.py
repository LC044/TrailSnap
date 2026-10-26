"""Apply verified PR facts consistently for webhooks, late links and reconciliation."""
from sqlalchemy.orm import Session

from .config import settings
from .delivery import requirement_transition
from .domain.common import audit, enqueue
from .integrations.github import closing_issue_numbers, pull_request_summary
from .models import DeliveryTask, PullRequestLink, Requirement
from .services import GitHubClient


TERMINAL_STATUSES = {"closed", "released", "rejected", "duplicate", "withdrawn"}


def apply_pull_request(db: Session, pull_request: dict, *, source: str) -> int:
    base = pull_request.get("base") or {}
    if (base.get("repo") or {}).get("full_name", "").lower() != settings.github_repo.lower():
        return 0
    if base.get("ref") != "master" or not pull_request.get("number"):
        return 0
    summary = pull_request_summary(pull_request)
    number = summary["number"]
    link = db.query(PullRequestLink).filter(
        PullRequestLink.repository == settings.github_repo,
        PullRequestLink.pull_request_number == number,
    ).first()
    task = db.get(DeliveryTask, link.task_id) if link else None
    if link:
        # A delayed opened/synchronize delivery cannot undo an observed merge.
        if link.state == "merged" and summary["state"] != "merged":
            return 0
        link.url = summary.get("url") or link.url
        link.head_sha = str((pull_request.get("head") or {}).get("sha") or link.head_sha)
        link.state = summary["state"]
        if summary["state"] == "merged" and task.state not in {"merged", "cancelled"}:
            task.state, task.state_version = "merged", task.state_version + 1

    issue_numbers = closing_issue_numbers(pull_request)
    closed = 0
    for row in db.query(Requirement).filter(Requirement.deleted_at.is_(None)).all():
        if summary["state"] != "merged" and any(
            item.get("number") == number and item.get("state") == "merged"
            for item in (row.github_pull_requests or [])
        ):
            continue
        explicit = bool(task and task.requirement_id == row.id)
        is_linked = explicit or row.github_issue_number in issue_numbers
        related = [item for item in (row.github_pull_requests or []) if item.get("number") != number]
        if is_linked:
            related.append(summary)
            related.sort(key=lambda item: item.get("number") or 0, reverse=True)
        if related != (row.github_pull_requests or []):
            row.github_pull_requests = related
            audit(db, None, "github.pull_request.updated" if is_linked else "github.pull_request.unlinked",
                  "requirement", row.id, source=source, pull_request_number=number,
                  pull_request_url=summary.get("url"))
        if not is_linked or summary["state"] != "merged" or row.status in TERMINAL_STATUSES:
            continue
        if explicit and task.state == "cancelled":
            continue
        requirement_transition(db, row, "closed", actor_id=None,
                               reason=f"关联 PR #{number} 已合并到 master：{summary.get('url') or ''}",
                               source=source)
        if row.github_issue_number:
            enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:pr-merged:{number}:v{row.state_version}")
        closed += 1
    return closed


def reconcile_pull_requests(db: Session, _object_id: str) -> None:
    client = GitHubClient()
    closed = 0
    # Do not use a recent-page cutoff: an old PR may have been linked only today.
    for pull_request in client.iter_closed_pull_requests():
        if pull_request.get("merged_at") or pull_request.get("merged"):
            closed += apply_pull_request(db, pull_request, source="github_pr_reconciliation")
    audit(db, None, "github.pull_requests.reconciled", "github_repository", settings.github_repo,
          closed_requirements=closed)


def schedule_pull_request_reconciliation(db: Session) -> None:
    from datetime import datetime, timezone
    if not (settings.github_token or (settings.github_app_id and settings.github_installation_id
                                      and settings.github_private_key)):
        return
    hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    enqueue(db, "github_pull_requests", settings.github_repo, f"github_pull_requests:{settings.github_repo}:{hour}")
