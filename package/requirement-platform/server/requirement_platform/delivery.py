"""Domain services for immutable specifications and manual agent delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    AcceptanceCriterion, AgentRun, AgentRunQuestion, Artifact, ContextBundle, DeliveryTask,
    DomainEvent, IdempotencyRecord, PullRequestLink, Requirement, RequirementAttachment,
    RequirementSpec, TriageReport, utcnow,
)
from .schemas import RequirementSpecContent
from .services import GitHubClient, audit, enqueue


LEASE_SECONDS = 90
FINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


class DomainConflict(ValueError):
    def __init__(self, message: str, *, current_version: int | None = None, allowed_actions: list[str] | None = None):
        super().__init__(message)
        self.current_version = current_version
        self.allowed_actions = allowed_actions or []


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _event(db: Session, event_type: str, aggregate_type: str, aggregate_id: str, version: int,
           *, source: str, payload: dict[str, Any] | None = None, correlation_id: str | None = None) -> None:
    db.add(DomainEvent(event_type=event_type, aggregate_type=aggregate_type,
                       aggregate_id=aggregate_id, aggregate_version=version, source=source,
                       payload=payload or {}, correlation_id=correlation_id))
    db.flush()


def requirement_transition(db: Session, row: Requirement, target: str, *, actor_id: str | None,
                           reason: str, source: str, expected_state_version: int | None = None) -> None:
    if expected_state_version is not None and row.state_version != expected_state_version:
        raise DomainConflict("需求状态已变化，请刷新后重试", current_version=row.state_version)
    before = row.status
    if before == target:
        return
    row.status = target
    row.state_version += 1
    audit(db, actor_id, "requirement.status_changed", "requirement", row.id,
          before=before, after=target, reason=reason, source=source, state_version=row.state_version)
    _event(db, "requirement.state_changed", "requirement", row.id, row.state_version,
           source=source, payload={"before": before, "after": target, "reason": reason})


def invalidate_delivery_authorizations(db: Session, requirement: Requirement, *, actor_id: str | None,
                                       reason: str, source: str) -> bool:
    now = utcnow()
    specs = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == requirement.id,
                                             RequirementSpec.status == "approved").all()
    if not specs:
        return False
    spec_ids = [item.id for item in specs]
    for spec in specs:
        spec.status, spec.superseded_at, spec.state_version = "superseded", now, spec.state_version + 1
        _event(db, "spec.superseded", "spec", spec.id, spec.state_version, source=source,
               payload={"reason": reason, "new_requirement_revision": requirement.content_revision})
    tasks = db.query(DeliveryTask).filter(DeliveryTask.spec_id.in_(spec_ids),
                                          DeliveryTask.state.notin_({"merged", "cancelled"})).all()
    for task in tasks:
        task.state, task.blocked_reason, task.state_version = "cancelled", reason, task.state_version + 1
        for run in db.query(AgentRun).filter(AgentRun.task_id == task.id,
                                             AgentRun.status.in_({"running", "waiting_input"})).all():
            run.status, run.finished_at, run.exit_reason = "cancelled", now, reason
            run.state_version += 1
    requirement_transition(db, requirement, "submitted", actor_id=actor_id, reason=reason, source=source)
    audit(db, actor_id, "delivery.authorization_revoked", "requirement", requirement.id,
          reason=reason, spec_ids=spec_ids, task_ids=[item.id for item in tasks], source=source)
    return True


def spec_dict(db: Session, row: RequirementSpec) -> dict[str, Any]:
    criteria = db.query(AcceptanceCriterion).filter(AcceptanceCriterion.spec_id == row.id).order_by(AcceptanceCriterion.criterion_id).all()
    return {
        "id": row.id, "requirement_id": row.requirement_id, "requirement_revision": row.requirement_revision,
        "revision": row.revision,
        "schema_version": row.schema_version, "status": row.status, "content": row.content,
        "content_hash": row.content_hash, "state_version": row.state_version,
        "created_by": row.created_by, "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "acceptance": [{"id": ac.criterion_id, "given": ac.given_text, "when": ac.when_text,
                        "then": ac.then_text, "required": ac.required, "verification": ac.verification,
                        "dataset": ac.dataset} for ac in criteria],
    }


def _replace_criteria(db: Session, spec: RequirementSpec, content: dict[str, Any]) -> None:
    db.query(AcceptanceCriterion).filter(AcceptanceCriterion.spec_id == spec.id).delete()
    for item in content["acceptance"]:
        db.add(AcceptanceCriterion(spec_id=spec.id, criterion_id=item["id"], given_text=item["given"],
                                   when_text=item["when"], then_text=item["then"], required=item.get("required", True),
                                   verification=item["verification"], dataset=item.get("dataset")))


def create_spec(db: Session, requirement: Requirement, content_model: RequirementSpecContent,
                actor_id: str, expected_requirement_state_version: int) -> RequirementSpec:
    if requirement.state_version != expected_requirement_state_version:
        raise DomainConflict("需求状态已变化，请刷新后重试", current_version=requirement.state_version)
    if requirement.status in {"rejected", "duplicate", "withdrawn", "closed", "released"}:
        raise DomainConflict("当前需求状态不能创建执行规格", current_version=requirement.state_version)
    content = content_model.model_dump(mode="json")
    stale_drafts = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == requirement.id,
                                                     RequirementSpec.status == "draft").all()
    for item in stale_drafts:
        item.status, item.superseded_at, item.state_version = "superseded", utcnow(), item.state_version + 1
    latest = db.query(func.max(RequirementSpec.revision)).filter(RequirementSpec.requirement_id == requirement.id).scalar() or 0
    spec = RequirementSpec(requirement_id=requirement.id, requirement_revision=requirement.content_revision,
                           revision=latest + 1, content=content,
                           content_hash=canonical_hash(content), created_by=actor_id)
    db.add(spec)
    db.flush()
    _replace_criteria(db, spec, content)
    _event(db, "spec.created", "spec", spec.id, spec.state_version, source="rest",
           payload={"requirement_id": requirement.id, "revision": spec.revision})
    audit(db, actor_id, "spec.created", "requirement_spec", spec.id,
          requirement_id=requirement.id, revision=spec.revision, content_hash=spec.content_hash)
    return spec


def update_spec(db: Session, spec: RequirementSpec, content_model: RequirementSpecContent,
                actor_id: str, expected_state_version: int) -> RequirementSpec:
    if spec.status != "draft":
        raise DomainConflict("只有草稿规格可以编辑", current_version=spec.state_version, allowed_actions=["create_revision"])
    if spec.state_version != expected_state_version:
        raise DomainConflict("规格已变化，请刷新后重试", current_version=spec.state_version)
    content = content_model.model_dump(mode="json")
    spec.content, spec.content_hash = content, canonical_hash(content)
    spec.state_version += 1
    _replace_criteria(db, spec, content)
    _event(db, "spec.updated", "spec", spec.id, spec.state_version, source="rest")
    audit(db, actor_id, "spec.updated", "requirement_spec", spec.id, state_version=spec.state_version)
    return spec


def approve_spec(db: Session, spec: RequirementSpec, actor_id: str, expected_state_version: int,
                 *, manual_base_sha: str | None = None, allow_manual_sha: bool = False) -> RequirementSpec:
    if spec.status != "draft" or spec.state_version != expected_state_version:
        raise DomainConflict("规格不是可批准的当前草稿", current_version=spec.state_version)
    content = RequirementSpecContent.model_validate(spec.content)
    if content.blocking_questions:
        raise DomainConflict("规格仍有阻塞问题，不能批准", current_version=spec.state_version, allowed_actions=["update"])
    requirement = db.query(Requirement).filter(Requirement.id == spec.requirement_id).one()
    if requirement.content_revision != spec.requirement_revision:
        raise DomainConflict("需求内容已更新，必须基于最新内容创建新规格修订",
                             current_version=spec.state_version, allowed_actions=["create_revision"])
    try:
        base_sha = GitHubClient().get_branch_sha("master")
        sha_source = "github"
    except Exception as exc:
        if not (manual_base_sha and allow_manual_sha):
            raise DomainConflict(f"无法从 GitHub 解析 master 基线：{type(exc).__name__}", current_version=spec.state_version) from exc
        base_sha, sha_source = manual_base_sha.lower(), "owner_manual_override"
    content_data = content.model_dump(mode="json")
    content_data["repository"], content_data["target_branch"], content_data["base_sha"] = "LC044/TrailSnap", "master", base_sha
    spec.content, spec.content_hash = content_data, canonical_hash(content_data)
    now = utcnow()
    previous = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == spec.requirement_id,
                                                RequirementSpec.status == "approved", RequirementSpec.id != spec.id).all()
    for item in previous:
        item.status, item.superseded_at, item.state_version = "superseded", now, item.state_version + 1
        _event(db, "spec.superseded", "spec", item.id, item.state_version, source="rest")
    spec.status, spec.approved_by, spec.approved_at = "approved", actor_id, now
    spec.state_version += 1
    requirement_transition(db, requirement, "accepted", actor_id=actor_id, reason=f"规格 v{spec.revision} 已批准", source="spec_approval")
    if requirement.github_issue_number:
        enqueue(db, "github_issue", requirement.id, f"github_issue:{requirement.id}:spec-approved:{spec.id}")
    _event(db, "spec.approved", "spec", spec.id, spec.state_version, source="rest",
           payload={"base_sha": base_sha, "sha_source": sha_source, "content_hash": spec.content_hash})
    audit(db, actor_id, "spec.approved", "requirement_spec", spec.id,
          base_sha=base_sha, sha_source=sha_source, content_hash=spec.content_hash)
    return spec


def _build_context(db: Session, requirement: Requirement, spec: RequirementSpec) -> dict[str, Any]:
    attachments = db.query(RequirementAttachment).filter(RequirementAttachment.requirement_id == requirement.id).all()
    triage = db.query(TriageReport).filter(TriageReport.requirement_id == requirement.id,
                                           TriageReport.status == "current").order_by(TriageReport.created_at.desc()).first()
    return {
        "schema_version": 1, "role": "coding", "requirement": {
            "id": requirement.id, "number": requirement.public_number, "title": requirement.title,
            "original_description": requirement.description, "confirmed_summary": requirement.confirmed_summary,
            "content_revision": requirement.content_revision,
        },
        "spec": {"id": spec.id, "revision": spec.revision, "hash": spec.content_hash, **spec.content},
        "evidence_refs": ([{"type": "triage_report", "id": triage.id,
                             "requirement_revision": triage.requirement_version}] if triage else []) +
                         [{"type": "attachment", "id": item.id, "name": item.original_name,
                           "sha256": item.content_sha256, "processing_status": item.processing_status,
                           "download_path": f"/api/requirements/{requirement.id}/attachments/{item.id}"}
                          for item in attachments],
        "repository_constraints": {"instructions": ["AGENTS.md"], "test_entry": "tests/scripts/run-tests.ps1",
                                   "instruction_base_sha": spec.content["base_sha"]},
        "authorization": {"mode": "manual_agent", "may_merge": False, "may_release": False,
                          "may_write_default_branch": False},
    }


def create_delivery_task(db: Session, spec: RequirementSpec, actor_id: str, *, risk_level: str,
                         budget: dict[str, Any], dependency_ids: list[str]) -> DeliveryTask:
    if spec.status != "approved":
        raise DomainConflict("只能为已批准规格创建交付任务", current_version=spec.state_version)
    existing = db.query(DeliveryTask).filter(DeliveryTask.spec_id == spec.id).first()
    if existing:
        if existing.risk_level != risk_level or existing.budget != budget or existing.dependency_ids != dependency_ids:
            raise DomainConflict("该规格已有参数不同的交付任务", current_version=existing.state_version)
        return existing
    if len(set(dependency_ids)) != len(dependency_ids):
        raise DomainConflict("交付任务依赖不能重复")
    if dependency_ids:
        found = {row[0] for row in db.query(DeliveryTask.id).filter(DeliveryTask.id.in_(dependency_ids)).all()}
        if found != set(dependency_ids):
            raise DomainConflict("交付任务包含不存在的依赖")
    requirement = db.query(Requirement).filter(Requirement.id == spec.requirement_id).one()
    context = _build_context(db, requirement, spec)
    bundle = ContextBundle(spec_id=spec.id, repository="LC044/TrailSnap", target_branch="master",
                           base_sha=spec.content["base_sha"], content=context, content_hash=canonical_hash(context))
    db.add(bundle)
    db.flush()
    task = DeliveryTask(requirement_id=requirement.id, spec_id=spec.id, context_bundle_id=bundle.id,
                        repository="LC044/TrailSnap", target_branch="master", base_sha=spec.content["base_sha"],
                        risk_level=risk_level, budget=budget, dependency_ids=dependency_ids, created_by=actor_id)
    db.add(task)
    db.flush()
    _event(db, "delivery_task.created", "delivery_task", task.id, task.state_version, source="rest",
           payload={"spec_id": spec.id, "context_bundle_id": bundle.id})
    audit(db, actor_id, "delivery_task.created", "delivery_task", task.id, spec_id=spec.id)
    return task


def task_dict(db: Session, task: DeliveryTask, *, include_context: bool = False) -> dict[str, Any]:
    runs = db.query(AgentRun).filter(AgentRun.task_id == task.id).order_by(AgentRun.started_at.desc()).all()
    prs = db.query(PullRequestLink).filter(PullRequestLink.task_id == task.id).all()
    artifacts = db.query(Artifact).filter(Artifact.task_id == task.id).order_by(Artifact.created_at).all()
    data = {"id": task.id, "requirement_id": task.requirement_id, "spec_id": task.spec_id,
            "context_bundle_id": task.context_bundle_id, "repository": task.repository,
            "target_branch": task.target_branch, "base_sha": task.base_sha, "state": task.state,
            "state_version": task.state_version, "risk_level": task.risk_level, "budget": task.budget,
            "dependency_ids": task.dependency_ids, "blocked_reason": task.blocked_reason,
            "created_at": task.created_at.isoformat(), "updated_at": task.updated_at.isoformat(),
            "runs": [run_dict(db, item, include_lease=False) for item in runs],
            "pull_requests": [{"id": item.id, "number": item.pull_request_number, "url": item.url,
                               "head_sha": item.head_sha, "base_sha": item.base_sha, "state": item.state,
                               "covered_acceptance_ids": item.covered_acceptance_ids} for item in prs]}
    data["artifacts"] = [{"id": item.id, "run_id": item.run_id, "kind": item.kind, "uri": item.uri,
                          "sha256": item.sha256, "mime_type": item.mime_type, "size_bytes": item.size_bytes,
                          "access_level": item.access_level, "metadata": item.metadata_json} for item in artifacts]
    if include_context:
        bundle = db.query(ContextBundle).filter(ContextBundle.id == task.context_bundle_id).one()
        data["context_bundle"] = {"id": bundle.id, "hash": bundle.content_hash, "content": bundle.content}
    return data


def run_dict(db: Session, run: AgentRun, *, include_lease: bool = False, lease_token: str | None = None) -> dict[str, Any]:
    questions = db.query(AgentRunQuestion).filter(AgentRunQuestion.run_id == run.id).order_by(AgentRunQuestion.created_at).all()
    data = {"id": run.id, "task_id": run.task_id, "attempt_id": run.attempt_id,
            "execution_epoch": run.execution_epoch, "role": run.role, "provider": run.provider,
            "model": run.model, "status": run.status, "runner_name": run.runner_name,
            "lease_expires_at": run.lease_expires_at.isoformat(), "last_heartbeat_at": run.last_heartbeat_at.isoformat(),
            "session_reference": run.session_reference, "result": run.result, "usage": run.usage,
            "implementation_plan": run.implementation_plan,
            "exit_reason": run.exit_reason, "state_version": run.state_version,
            "started_at": run.started_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "questions": [{"id": q.id, "question": q.question, "blocking": q.blocking, "status": q.status,
                           "answer": q.answer} for q in questions]}
    if include_lease:
        data["lease_token"] = lease_token
    return data


def _expired(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now


def lease_token_for(run: AgentRun) -> str:
    """Derive a repeatable lease secret without persisting the plaintext token."""
    material = f"{run.id}:{run.attempt_id}:{run.execution_epoch}".encode()
    digest = hmac.new(settings.jwt_secret.encode(), material, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def claim_task(db: Session, *, runner_name: str, provider: str, model: str | None, role: str,
               restricted_task_id: str | None = None) -> tuple[AgentRun, str, DeliveryTask]:
    now = utcnow()
    expired_runs = db.query(AgentRun).filter(AgentRun.status.in_({"running", "waiting_input"})).all()
    for old in expired_runs:
        if _expired(old.lease_expires_at, now):
            old.status, old.finished_at, old.exit_reason = "timed_out", now, "lease expired"
            old.state_version += 1
            old_task = db.query(DeliveryTask).filter(DeliveryTask.id == old.task_id).one()
            if old_task.state not in {"pr_open", "merged", "cancelled"}:
                old_task.state, old_task.state_version = "queued", old_task.state_version + 1
    query = db.query(DeliveryTask).filter(DeliveryTask.state == "queued")
    if restricted_task_id:
        query = query.filter(DeliveryTask.id == restricted_task_id)
    task = None
    for candidate in query.order_by(DeliveryTask.created_at).all():
        dependencies = candidate.dependency_ids or []
        if not dependencies or db.query(DeliveryTask).filter(
            DeliveryTask.id.in_(dependencies), DeliveryTask.state != "merged"
        ).count() == 0:
            task = candidate
            break
    if not task:
        raise DomainConflict("当前没有可领取的交付任务")
    claimed = db.query(DeliveryTask).filter(DeliveryTask.id == task.id, DeliveryTask.state == "queued").update(
        {DeliveryTask.state: "planning", DeliveryTask.state_version: DeliveryTask.state_version + 1},
        synchronize_session=False,
    )
    if claimed != 1:
        raise DomainConflict("任务刚刚被其他 Agent 领取，请重试")
    db.refresh(task)
    active = db.query(AgentRun).filter(AgentRun.task_id == task.id, AgentRun.status.in_({"running", "waiting_input"})).first()
    if active:
        raise DomainConflict("任务已有有效执行", current_version=task.state_version)
    epoch = (db.query(func.max(AgentRun.execution_epoch)).filter(AgentRun.task_id == task.id).scalar() or 0) + 1
    run = AgentRun(task_id=task.id, execution_epoch=epoch, role=role, provider=provider, model=model,
                   runner_name=runner_name, lease_token_hash="pending",
                   lease_expires_at=now + timedelta(seconds=LEASE_SECONDS), last_heartbeat_at=now)
    db.add(run)
    db.flush()
    lease_token = lease_token_for(run)
    run.lease_token_hash = hashlib.sha256(lease_token.encode()).hexdigest()
    _event(db, "agent_run.claimed", "agent_run", run.id, run.state_version, source="mcp",
           payload={"task_id": task.id, "attempt_id": run.attempt_id, "execution_epoch": epoch})
    return run, lease_token, task


def validate_run_write(run: AgentRun, *, attempt_id: str, lease_token: str, expected_state_version: int) -> None:
    if run.attempt_id != attempt_id or not secrets.compare_digest(run.lease_token_hash, hashlib.sha256(lease_token.encode()).hexdigest()):
        raise DomainConflict("执行凭证无效")
    if run.state_version != expected_state_version:
        raise DomainConflict("执行状态已变化，请刷新后重试", current_version=run.state_version)
    if run.status in FINAL_RUN_STATES or _expired(run.lease_expires_at, utcnow()):
        raise DomainConflict("执行租约已失效", current_version=run.state_version)


def heartbeat(db: Session, run: AgentRun, *, attempt_id: str, lease_token: str,
              expected_state_version: int, session_reference: str | None) -> AgentRun:
    validate_run_write(run, attempt_id=attempt_id, lease_token=lease_token, expected_state_version=expected_state_version)
    now = utcnow()
    run.last_heartbeat_at, run.lease_expires_at = now, now + timedelta(seconds=LEASE_SECONDS)
    run.session_reference = session_reference or run.session_reference
    run.state_version += 1
    return run


def submit_question(db: Session, run: AgentRun, *, attempt_id: str, lease_token: str,
                    expected_state_version: int, question: str, blocking: bool) -> AgentRunQuestion:
    validate_run_write(run, attempt_id=attempt_id, lease_token=lease_token, expected_state_version=expected_state_version)
    row = AgentRunQuestion(run_id=run.id, question=question, blocking=blocking)
    db.add(row)
    run.status = "waiting_input" if blocking else run.status
    run.state_version += 1
    task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
    if blocking:
        task.blocked_reason, task.state_version = question, task.state_version + 1
    _event(db, "agent_run.clarification_requested", "agent_run", run.id, run.state_version, source="mcp",
           payload={"blocking": blocking, "question": question})
    return row


def submit_implementation_plan(db: Session, run: AgentRun, *, attempt_id: str, lease_token: str,
                               expected_state_version: int, plan: dict[str, Any]) -> AgentRun:
    validate_run_write(run, attempt_id=attempt_id, lease_token=lease_token, expected_state_version=expected_state_version)
    task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
    required_ids = {row.criterion_id for row in db.query(AcceptanceCriterion).filter(
        AcceptanceCriterion.spec_id == task.spec_id, AcceptanceCriterion.required.is_(True)).all()}
    missing = required_ids - set(plan.get("acceptance_plan", {}))
    if missing:
        raise DomainConflict(f"实现计划未覆盖必需验收标准：{', '.join(sorted(missing))}", current_version=run.state_version)
    run.implementation_plan, run.plan_submitted_at = plan, utcnow()
    ambiguities = [str(item).strip() for item in plan.get("ambiguities", []) if str(item).strip()]
    if ambiguities:
        run.status, task.blocked_reason = "waiting_input", "实现计划存在待澄清事项"
        task.state_version += 1
        for question in ambiguities:
            db.add(AgentRunQuestion(run_id=run.id, question=question, blocking=True))
    else:
        run.status, task.state, task.blocked_reason = "running", "implementing", None
        task.state_version += 1
    run.state_version += 1
    _event(db, "implementation_plan.submitted", "agent_run", run.id, run.state_version, source="mcp",
           payload={"covered_acceptance_ids": sorted(plan["acceptance_plan"]), "ambiguity_count": len(ambiguities)})
    return run


def answer_run_question(db: Session, question: AgentRunQuestion, *, actor_id: str, answer: str,
                        expected_run_state_version: int, requires_spec_revision: bool) -> AgentRun:
    run = db.query(AgentRun).filter(AgentRun.id == question.run_id).one()
    if question.status != "open" or run.state_version != expected_run_state_version:
        raise DomainConflict("澄清问题或执行状态已变化", current_version=run.state_version)
    question.answer, question.answered_at, question.status = answer, utcnow(), "answered"
    task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
    if requires_spec_revision:
        run.status, run.finished_at, run.exit_reason = "cancelled", utcnow(), "spec revision required"
        task.state, task.blocked_reason = "changes_requested", "规格需要修订并重新授权"
    else:
        remaining = db.query(AgentRunQuestion).filter(AgentRunQuestion.run_id == run.id,
                                                      AgentRunQuestion.status == "open",
                                                      AgentRunQuestion.blocking.is_(True)).count()
        if remaining == 0:
            run.status, task.blocked_reason = "running", None
    run.state_version += 1
    task.state_version += 1
    _event(db, "agent_run.clarification_answered", "agent_run", run.id, run.state_version, source="rest",
           payload={"question_id": question.id, "requires_spec_revision": requires_spec_revision})
    audit(db, actor_id, "agent_run.clarification_answered", "agent_run_question", question.id,
          run_id=run.id, requires_spec_revision=requires_spec_revision)
    return run


def submit_result(db: Session, run: AgentRun, *, attempt_id: str, lease_token: str,
                  expected_state_version: int, result: dict[str, Any]) -> AgentRun:
    validate_run_write(run, attempt_id=attempt_id, lease_token=lease_token, expected_state_version=expected_state_version)
    if not run.implementation_plan:
        raise DomainConflict("必须先提交覆盖全部必需 AC 的实现计划", current_version=run.state_version)
    if run.status != "running":
        raise DomainConflict("当前执行状态不能提交结果", current_version=run.state_version)
    if result["status"] == "succeeded":
        task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
        required_ids = {row.criterion_id for row in db.query(AcceptanceCriterion).filter(
            AcceptanceCriterion.spec_id == task.spec_id, AcceptanceCriterion.required.is_(True)).all()}
        missing = required_ids - set(result.get("acceptance_coverage", {}))
        if missing:
            raise DomainConflict(f"成功结果未覆盖必需验收标准：{', '.join(sorted(missing))}", current_version=run.state_version)
        if not result.get("head_sha"):
            raise DomainConflict("成功结果必须绑定完整 head SHA", current_version=run.state_version)
    now = utcnow()
    run.status, run.result, run.usage = result["status"], result, result.get("usage", {})
    run.exit_reason, run.finished_at, run.state_version = result.get("exit_reason"), now, run.state_version + 1
    task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
    task.state = "implementing" if run.status == "succeeded" else ("cancelled" if run.status == "cancelled" else "changes_requested")
    task.blocked_reason = None if run.status == "succeeded" else (run.exit_reason or result.get("summary"))
    task.state_version += 1
    _event(db, "agent_run.completed", "agent_run", run.id, run.state_version, source="mcp",
           payload={"status": run.status, "task_id": task.id, "head_sha": result.get("head_sha")})
    return run


def register_artifact(db: Session, run: AgentRun, *, attempt_id: str, lease_token: str,
                      expected_state_version: int, producer_token_id: str, artifact: dict[str, Any]) -> Artifact:
    validate_run_write(run, attempt_id=attempt_id, lease_token=lease_token, expected_state_version=expected_state_version)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(artifact.get("sha256", ""))):
        raise DomainConflict("产物 SHA-256 格式无效")
    if artifact.get("access_level") not in {"private", "manager", "public"} or int(artifact.get("size_bytes", -1)) < 0:
        raise DomainConflict("产物访问级别或大小无效")
    existing = db.query(Artifact).filter(Artifact.run_id == run.id, Artifact.sha256 == artifact["sha256"].lower(),
                                         Artifact.uri == artifact["uri"]).first()
    if existing:
        return existing
    row = Artifact(task_id=run.task_id, run_id=run.id, producer_token_id=producer_token_id,
                   kind=artifact["kind"], uri=artifact["uri"], sha256=artifact["sha256"].lower(),
                   mime_type=artifact["mime_type"], size_bytes=artifact["size_bytes"],
                   access_level=artifact["access_level"], metadata_json=artifact.get("metadata", {}))
    db.add(row)
    run.state_version += 1
    db.flush()
    _event(db, "artifact.registered", "agent_run", run.id, run.state_version, source="mcp",
           payload={"artifact_id": row.id, "kind": row.kind, "sha256": row.sha256})
    return row


def link_pull_request(db: Session, task: DeliveryTask, *, number: int, url: str, head_sha: str, base_sha: str,
                      covered_ids: list[str], expected_state_version: int) -> PullRequestLink:
    if task.state_version != expected_state_version:
        raise DomainConflict("交付任务已变化，请刷新后重试", current_version=task.state_version)
    if task.state not in {"implementing", "pr_open", "changes_requested"}:
        raise DomainConflict("当前任务状态不能关联 PR", current_version=task.state_version)
    valid_ids = {row.criterion_id for row in db.query(AcceptanceCriterion).filter(AcceptanceCriterion.spec_id == task.spec_id).all()}
    if not set(covered_ids).issubset(valid_ids):
        raise DomainConflict("PR 覆盖了规格中不存在的验收标准", current_version=task.state_version)
    remote = GitHubClient().get_pull_request(number)
    if remote.get("html_url") != url or remote.get("head", {}).get("sha", "").lower() != head_sha.lower():
        raise DomainConflict("PR URL 或 head SHA 与 GitHub 事实不一致", current_version=task.state_version)
    if remote.get("base", {}).get("ref") != "master" or remote.get("base", {}).get("repo", {}).get("full_name") != "LC044/TrailSnap":
        raise DomainConflict("PR 不属于批准仓库或目标分支", current_version=task.state_version)
    if remote.get("base", {}).get("sha", "").lower() != base_sha.lower():
        raise DomainConflict("PR base SHA 与上报值不一致", current_version=task.state_version)
    existing = db.query(PullRequestLink).filter(PullRequestLink.repository == task.repository,
                                                PullRequestLink.pull_request_number == number).first()
    if existing and existing.task_id != task.id:
        raise DomainConflict("该 PR 已关联其他交付任务")
    row = existing or PullRequestLink(task_id=task.id, repository=task.repository, pull_request_number=number,
                                      url=url, head_sha=head_sha.lower(), base_sha=base_sha.lower())
    row.covered_acceptance_ids, row.state = covered_ids, "open"
    db.add(row)
    task.state, task.state_version = "pr_open", task.state_version + 1
    _event(db, "pr.linked", "delivery_task", task.id, task.state_version, source="mcp",
           payload={"number": number, "head_sha": head_sha, "base_sha": base_sha})
    return row


def cancel_run(db: Session, run: AgentRun, actor_id: str) -> AgentRun:
    if run.status in FINAL_RUN_STATES:
        return run
    run.status, run.finished_at, run.exit_reason = "cancelled", utcnow(), "cancelled by administrator"
    run.state_version += 1
    task = db.query(DeliveryTask).filter(DeliveryTask.id == run.task_id).one()
    task.state, task.state_version, task.blocked_reason = "cancelled", task.state_version + 1, run.exit_reason
    _event(db, "agent_run.cancelled", "agent_run", run.id, run.state_version, source="rest")
    audit(db, actor_id, "agent_run.cancelled", "agent_run", run.id, task_id=task.id)
    return run


def idempotent_result(db: Session, *, actor_key: str, operation: str, key: str,
                      request: dict[str, Any], action) -> tuple[dict[str, Any], bool]:
    request_hash = canonical_hash(request)
    existing = db.query(IdempotencyRecord).filter(IdempotencyRecord.actor_key == actor_key,
                                                   IdempotencyRecord.operation == operation,
                                                   IdempotencyRecord.idempotency_key == key).first()
    if existing:
        if existing.request_hash != request_hash:
            raise DomainConflict("同一 Idempotency-Key 不能用于不同请求")
        return existing.response, True
    response = action()
    db.flush()
    stored_response = dict(response)
    if operation == "claim_task":
        stored_response.pop("lease_token", None)
    db.add(IdempotencyRecord(actor_key=actor_key, operation=operation, idempotency_key=key,
                             request_hash=request_hash, response=stored_response))
    try:
        db.flush()
    except IntegrityError as exc:
        raise DomainConflict("幂等写入发生并发冲突，请使用相同请求重试") from exc
    return response, False
