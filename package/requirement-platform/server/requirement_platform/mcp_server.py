"""Authenticated MCP tools for requirement and release management."""

import base64
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func

from .config import settings
from .db import SessionLocal
from .models import (
    AgentToken, AuditEvent, BackgroundJob, ReleaseBatch, ReleaseBatchItem, Requirement, RequirementAttachment,
    RequirementFollower, RequirementRevision, ReviewDecision, TriageReport, User, utcnow,
)
from .security import resolve_agent_token
from .services import (
    GitHubClient, audit, enqueue, requirement_snapshot, requirement_status_from_github, sync_batch_milestone,
)


class DatabaseTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        with SessionLocal() as db:
            row = resolve_agent_token(db, token)
            if not row:
                return None
            row.last_used_at = datetime.now(timezone.utc)
            db.commit()
            expires_at = int(row.expires_at.replace(tzinfo=timezone.utc).timestamp()) if row.expires_at else None
            return AccessToken(
                token=token,
                client_id=f"agent-token:{row.id}",
                subject=row.created_by,
                scopes=list(row.scopes),
                expires_at=expires_at,
                resource=settings.mcp_public_url,
                claims={"token_id": row.id},
            )


mcp = MCPServer(
    name="trailsnap-requirements",
    title="TrailSnap 需求管理",
    version="0.3.0",
    instructions=(
        "用于查询和管理 TrailSnap 需求与版本。任何写入、审核、删除和 GitHub 操作都必须遵循令牌作用域；"
        "删除为可恢复的软删除。执行 review_requirement 前先读取需求详情，理由必须具体。"
    ),
    token_verifier=DatabaseTokenVerifier(),
    auth=AuthSettings(
        issuer_url=settings.web_url,
        resource_server_url=settings.mcp_public_url,
        required_scopes=[],
        validate_token_resource=False,
    ),
)


def _identity(required_scope: str) -> tuple[AgentToken, User]:
    access = get_access_token()
    if not access or required_scope not in access.scopes:
        raise PermissionError(f"缺少 MCP 作用域：{required_scope}")
    token_id = (access.claims or {}).get("token_id")
    with SessionLocal() as db:
        token = db.query(AgentToken).filter(AgentToken.id == token_id, AgentToken.revoked_at.is_(None)).first()
        if not token:
            raise PermissionError("MCP 令牌无效或已撤销")
        user = db.query(User).filter(User.id == token.created_by, User.is_active.is_(True)).first()
        if not user or user.role not in {"owner", "admin"}:
            raise PermissionError("令牌所属账号已无管理权限")
        db.expunge(token)
        db.expunge(user)
        return token, user


def _requirement_dict(row: Requirement) -> dict[str, Any]:
    return {
        "id": row.id, "public_number": row.public_number, "reference": f"REQ-{row.public_number}",
        "type": row.type, "title": row.title, "description": row.description,
        "log_text": row.log_text, "current_behavior": row.current_behavior, "expected_behavior": row.expected_behavior,
        "steps_to_reproduce": row.steps_to_reproduce, "severity": row.severity, "product_version": row.product_version,
        "environment": row.environment, "visibility": row.visibility, "status": row.status,
        "priority": row.priority, "risk_level": row.risk_level, "review_reason": row.review_reason,
        "duplicate_of_id": row.duplicate_of_id,
        "github_issue_number": row.github_issue_number, "github_issue_url": row.github_issue_url,
        "github_state": row.github_state, "github_pull_requests": row.github_pull_requests or [],
        "source": row.source, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def _batch_dict(row: ReleaseBatch, db) -> dict[str, Any]:
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == row.id).order_by(
        ReleaseBatchItem.priority_order, ReleaseBatchItem.created_at
    ).all()
    return {
        "id": row.id, "name": row.name, "version_name": row.version_name, "batch_type": row.batch_type,
        "goal": row.goal, "status": row.status, "target_date": row.target_date, "max_risk_level": row.max_risk_level,
        "scope_summary": row.scope_summary, "github_milestone_number": row.github_milestone_number,
        "github_milestone_url": row.github_milestone_url, "locked_at": row.locked_at.isoformat() if row.locked_at else None,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "items": [{"id": item.id, "requirement_id": item.requirement_id, "priority_order": item.priority_order,
                   "delivery_status": item.delivery_status, "requirement_snapshot": item.requirement_snapshot} for item in items],
    }


def _requirement_or_error(db, requirement_id: str, *, include_deleted: bool = False) -> Requirement:
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
        raise ValueError("需求不存在")
    return row


def _enqueue_requirement_github_sync(db, row: Requirement) -> None:
    if row.github_issue_number or (row.visibility == "public" and row.status == "candidate"):
        enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:{row.status}:{secrets.token_hex(6)}")


def _apply_github_status(db, row: Requirement, issue: dict[str, Any], actor: User) -> bool:
    before = row.status
    after = requirement_status_from_github(issue, current_status=before)
    row.github_state = issue.get("state", row.github_state)
    if after == before:
        return False
    row.status = after
    audit(db, actor.id, "requirement.status_changed", "requirement", row.id,
          before=before, after=after, reason="GitHub 状态同步：manual_sync",
          source="github_manual_sync", actor_name=actor.username)
    return True


@mcp.tool()
def list_requirements(status: str | None = None, query: str | None = None, include_deleted: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    """列出需求，可按状态和关键词筛选。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        rows = db.query(Requirement)
        if not include_deleted:
            rows = rows.filter(Requirement.deleted_at.is_(None))
        if status:
            rows = rows.filter(Requirement.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            rows = rows.filter(Requirement.title.ilike(pattern) | Requirement.description.ilike(pattern))
        return [_requirement_dict(row) for row in rows.order_by(Requirement.created_at.desc()).limit(min(max(limit, 1), 100)).all()]


@mcp.tool()
def get_requirement(requirement_id: str) -> dict[str, Any]:
    """读取一个需求的完整管理信息；支持 UUID 或 REQ-123 公共编号。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id, include_deleted=True)
        return _requirement_dict(row)


@mcp.tool()
def create_requirement(type: str, title: str, description: str, severity: str = "medium", visibility: str = "public",
                       log_text: str | None = None, current_behavior: str | None = None,
                       expected_behavior: str | None = None, steps_to_reproduce: str | None = None,
                       product_version: str | None = None, environment: dict[str, Any] | None = None) -> dict[str, Any]:
    """以令牌所属管理员身份创建需求。"""
    _, actor = _identity("requirements:write")
    if type not in {"bug", "improvement", "feature"} or severity not in {"low", "medium", "high", "critical"}:
        raise ValueError("需求类型或影响程度无效")
    if (visibility not in {"public", "private"} or not 4 <= len(title.strip()) <= 160
            or not 10 <= len(description.strip()) <= 8000):
        raise ValueError("需求内容或公开范围无效")
    with SessionLocal() as db:
        public_number = (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1
        row = Requirement(public_number=public_number, type=type, title=title.strip(), description=description.strip(), severity=severity,
                          visibility=visibility, log_text=log_text, current_behavior=current_behavior,
                          expected_behavior=expected_behavior, steps_to_reproduce=steps_to_reproduce,
                          product_version=product_version, environment=environment or {}, created_by=actor.id)
        db.add(row)
        db.flush()
        db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
        enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "requirement.created_by_agent", "requirement", row.id)
        db.commit()
        db.refresh(row)
        return _requirement_dict(row)


@mcp.tool()
def update_requirement(requirement_id: str, type: str | None = None, title: str | None = None, description: str | None = None,
                       log_text: str | None = None, current_behavior: str | None = None, expected_behavior: str | None = None,
                       steps_to_reproduce: str | None = None, severity: str | None = None, product_version: str | None = None,
                       environment: dict[str, Any] | None = None, visibility: str | None = None) -> dict[str, Any]:
    """更新需求正文；未传入的字段保持不变。"""
    _, actor = _identity("requirements:write")
    if type and type not in {"bug", "improvement", "feature"}:
        raise ValueError("需求类型无效")
    if severity and severity not in {"low", "medium", "high", "critical"}:
        raise ValueError("影响程度无效")
    if visibility and visibility not in {"public", "private"}:
        raise ValueError("公开范围无效")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id)
        db.add(RequirementRevision(requirement_id=row.id, editor_id=actor.id, snapshot=requirement_snapshot(row), reason="mcp updated"))
        values = {"type": type, "title": title, "description": description, "log_text": log_text,
                  "current_behavior": current_behavior, "expected_behavior": expected_behavior,
                  "steps_to_reproduce": steps_to_reproduce, "severity": severity, "product_version": product_version,
                  "environment": environment, "visibility": visibility}
        for field, value in values.items():
            if value is not None:
                setattr(row, field, value.strip() if isinstance(value, str) else value)
        row.version += 1
        _enqueue_requirement_github_sync(db, row)
        enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "requirement.updated", "requirement", row.id, source="mcp", version=row.version)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def review_requirement(requirement_id: str, action: str, reason: str, priority: str = "normal", risk_level: str = "medium",
                       duplicate_of_id: str | None = None) -> dict[str, Any]:
    """人工授权的 Agent 审核需求并修改其状态。"""
    _, actor = _identity("requirements:review")
    statuses = {"candidate": "candidate", "needs_information": "needs_information", "rejected": "rejected",
                "deferred": "deferred", "duplicate": "duplicate", "close": "closed"}
    if action not in statuses or len(reason.strip()) < 2:
        raise ValueError("审核动作或理由无效")
    if priority not in {"low", "normal", "high", "urgent"} or risk_level not in {"low", "medium", "high", "critical"}:
        raise ValueError("优先级或风险等级无效")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id)
        if action == "duplicate":
            target = _requirement_or_error(db, duplicate_of_id or "")
            if target.id == row.id:
                raise ValueError("重复需求不能指向自身")
            row.duplicate_of_id = target.id
            for follower in db.query(RequirementFollower).filter(RequirementFollower.requirement_id == row.id).all():
                if not db.query(RequirementFollower).filter(RequirementFollower.requirement_id == target.id,
                                                           RequirementFollower.user_id == follower.user_id).first():
                    db.add(RequirementFollower(requirement_id=target.id, user_id=follower.user_id))
        before = row.status
        row.status, row.review_reason, row.priority, row.risk_level = statuses[action], reason.strip(), priority, risk_level
        _enqueue_requirement_github_sync(db, row)
        db.add(ReviewDecision(requirement_id=row.id, reviewer_id=actor.id, action=action, reason=reason,
                              metadata_json={"source": "mcp", "priority": priority, "risk_level": risk_level,
                                             "duplicate_of_id": duplicate_of_id}))
        audit(db, actor.id, f"requirement.{action}", "requirement", row.id, source="mcp", reason=reason,
              before=before, after=row.status)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def delete_requirement(requirement_id: str, reason: str) -> dict[str, Any]:
    """软删除需求；数据和审计记录仍保留，可由管理员恢复。"""
    _, actor = _identity("requirements:review")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row:
            raise ValueError("需求不存在或已删除")
        active_batch = db.query(ReleaseBatchItem).join(ReleaseBatch, ReleaseBatch.id == ReleaseBatchItem.batch_id).filter(
            ReleaseBatchItem.requirement_id == row.id,
            ReleaseBatch.status.notin_({"completed", "cancelled"}),
            ReleaseBatchItem.delivery_status != "removed",
        ).first()
        if active_batch:
            raise ValueError("需求仍在活动版本中，请先移出版本")
        row.deleted_at, row.deleted_by, row.delete_reason = datetime.now(timezone.utc), actor.id, reason.strip()
        audit(db, actor.id, "requirement.deleted", "requirement", row.id, source="mcp", reason=reason)
        db.commit()
        return {"id": row.id, "deleted": True}


@mcp.tool()
def restore_requirement(requirement_id: str) -> dict[str, Any]:
    """恢复一个被软删除的需求。"""
    _, actor = _identity("requirements:review")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_not(None)).first()
        if not row:
            raise ValueError("已删除需求不存在")
        row.deleted_at, row.deleted_by, row.delete_reason = None, None, None
        audit(db, actor.id, "requirement.restored", "requirement", row.id, source="mcp")
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def create_github_issue(requirement_id: str) -> dict[str, Any]:
    """为需求创建并关联 GitHub Issue。"""
    _, actor = _identity("github:write")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row:
            raise ValueError("需求不存在")
        if row.github_issue_number:
            return _requirement_dict(row)
        data = GitHubClient().create_issue(row)
        row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
        _enqueue_requirement_github_sync(db, row)
        audit(db, actor.id, "github.issue.created", "requirement", row.id, source="mcp", issue_number=data["number"])
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def link_github_issue(requirement_id: str, issue_number: int) -> dict[str, Any]:
    """把已有 GitHub Issue 关联到需求。"""
    _, actor = _identity("github:write")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row:
            raise ValueError("需求不存在")
        other = db.query(Requirement).filter(Requirement.github_issue_number == issue_number, Requirement.id != row.id).first()
        if other:
            raise ValueError("该 Issue 已关联其他需求")
        data = GitHubClient().get_issue(issue_number)
        row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
        _apply_github_status(db, row, data, actor)
        _enqueue_requirement_github_sync(db, row)
        audit(db, actor.id, "github.issue.linked", "requirement", row.id, source="mcp", issue_number=issue_number)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def close_github_issue(requirement_id: str, reason: str) -> dict[str, Any]:
    """关闭平台需求，并由后台任务同步关闭已关联的 GitHub Issue。"""
    _, actor = _identity("github:write")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row or not row.github_issue_number:
            raise ValueError("需求不存在或尚未关联 Issue")
        before = row.status
        row.status, row.review_reason = "closed", reason.strip()
        _enqueue_requirement_github_sync(db, row)
        audit(db, actor.id, "requirement.closed", "requirement", row.id, source="mcp",
              before=before, after="closed", issue_number=row.github_issue_number, reason=reason)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def list_versions() -> list[dict[str, Any]]:
    """列出版本批次、范围条目、交付状态和 GitHub Milestone。"""
    _identity("versions:read")
    with SessionLocal() as db:
        return [_batch_dict(row, db) for row in db.query(ReleaseBatch).order_by(ReleaseBatch.created_at.desc()).all()]


@mcp.tool()
def get_version(batch_id: str) -> dict[str, Any]:
    """读取一个版本批次的完整范围、交付状态和 Milestone 信息。"""
    _identity("versions:read")
    with SessionLocal() as db:
        row = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        if not row:
            raise ValueError("版本批次不存在")
        return _batch_dict(row, db)


@mcp.tool()
def create_version(name: str, version_name: str, goal: str, batch_type: str = "feature", target_date: str | None = None,
                   max_risk_level: str = "high") -> dict[str, Any]:
    """创建版本批次。"""
    _, actor = _identity("versions:write")
    if batch_type not in {"fix", "feature", "major", "hotfix"} or max_risk_level not in {"low", "medium", "high", "critical"}:
        raise ValueError("版本类型或最大风险等级无效")
    with SessionLocal() as db:
        if db.query(ReleaseBatch).filter(ReleaseBatch.version_name == version_name).first():
            raise ValueError("版本号已存在")
        row = ReleaseBatch(name=name.strip(), version_name=version_name.strip(), goal=goal.strip(), batch_type=batch_type,
                           target_date=target_date, max_risk_level=max_risk_level, created_by=actor.id)
        db.add(row)
        db.flush()
        audit(db, actor.id, "release_batch.created", "release_batch", row.id, source="mcp", version_name=row.version_name)
        db.commit()
        return _batch_dict(row, db)


@mcp.tool()
def add_version_requirement(batch_id: str, requirement_id: str, priority_order: int = 0) -> dict[str, Any]:
    """把候选需求加入未锁定的版本范围。"""
    _, actor = _identity("versions:write")
    with SessionLocal() as db:
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        requirement = _requirement_or_error(db, requirement_id)
        if not batch:
            raise ValueError("版本批次不存在")
        if batch.status not in {"planning", "candidate_selection"}:
            raise ValueError("版本范围已锁定")
        if requirement.status not in {"candidate", "scheduled"}:
            raise ValueError("只能加入候选需求")
        ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        if ranks.get(requirement.risk_level, 4) > ranks.get(batch.max_risk_level, 3):
            raise ValueError("需求风险超过版本上限")
        if db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id,
                                             ReleaseBatchItem.requirement_id == requirement.id).first():
            raise ValueError("需求已在该版本中")
        db.add(ReleaseBatchItem(batch_id=batch.id, requirement_id=requirement.id, priority_order=max(priority_order, 0),
                                requirement_snapshot=requirement_snapshot(requirement)))
        batch.status = "candidate_selection"
        audit(db, actor.id, "release_batch.item_added", "release_batch", batch.id, source="mcp", requirement_id=requirement.id)
        db.commit()
        return _batch_dict(batch, db)


@mcp.tool()
def remove_version_requirement(batch_id: str, item_id: str) -> dict[str, Any]:
    """从未锁定版本中移除一个范围条目。"""
    _, actor = _identity("versions:write")
    with SessionLocal() as db:
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        item = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id).first()
        if not batch or not item:
            raise ValueError("版本条目不存在")
        if batch.status not in {"planning", "candidate_selection"}:
            raise ValueError("版本范围已锁定")
        audit(db, actor.id, "release_batch.item_removed", "release_batch", batch.id, source="mcp", requirement_id=item.requirement_id)
        db.delete(item)
        db.commit()
        return {"removed": True, "item_id": item_id}


@mcp.tool()
def lock_version(batch_id: str) -> dict[str, Any]:
    """锁定版本范围，并把条目需求置为已排期。"""
    _, actor = _identity("versions:write")
    with SessionLocal() as db:
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch_id).all()
        if not batch or not items:
            raise ValueError("版本不存在或没有需求")
        if batch.status not in {"planning", "candidate_selection"}:
            raise ValueError("版本范围已锁定")
        batch.status, batch.locked_at = "scope_locked", utcnow()
        for item in items:
            requirement = _requirement_or_error(db, item.requirement_id)
            item.requirement_snapshot = requirement_snapshot(requirement)
            before, requirement.status = requirement.status, "scheduled"
            _enqueue_requirement_github_sync(db, requirement)
            audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id, source="mcp", before=before, after="scheduled")
        enqueue(db, "github_milestone", batch.id, f"github_milestone:{batch.id}")
        audit(db, actor.id, "release_batch.locked", "release_batch", batch.id, source="mcp", count=len(items))
        db.commit()
        return _batch_dict(batch, db)


@mcp.tool()
def update_version_status(batch_id: str, status: str, reason: str) -> dict[str, Any]:
    """推进、暂停、阻塞、发布或完成版本；完成/取消仅所有者令牌可执行。"""
    _, actor = _identity("versions:write")
    transitions = {"planning": {"cancelled"}, "candidate_selection": {"cancelled"},
                   "scope_locked": {"developing", "blocked", "paused", "cancelled"},
                   "developing": {"testing", "blocked", "paused", "cancelled"},
                   "testing": {"developing", "release_ready", "blocked", "paused", "cancelled"},
                   "release_ready": {"testing", "published", "blocked", "paused", "cancelled"},
                   "published": {"completed"}, "blocked": {"developing", "testing", "release_ready", "paused", "cancelled"},
                   "paused": {"developing", "testing", "release_ready", "blocked", "cancelled"}}
    with SessionLocal() as db:
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        if not batch or status not in transitions.get(batch.status, set()):
            raise ValueError("无效的版本状态流转")
        if status in {"completed", "cancelled"} and actor.role != "owner":
            raise PermissionError("只有所有者可以完成或取消版本")
        items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id).all()
        if status == "published" and any(item.delivery_status not in {"completed", "removed"} for item in items):
            raise ValueError("所有需求完成后才能发布")
        before, batch.status = batch.status, status
        requirement_status = {"developing": "developing", "testing": "testing", "release_ready": "release_ready",
                              "published": "released", "completed": "released"}.get(status)
        if requirement_status:
            for item in items:
                if requirement_status != "released" or item.delivery_status == "completed":
                    requirement = _requirement_or_error(db, item.requirement_id)
                    old, requirement.status = requirement.status, requirement_status
                    _enqueue_requirement_github_sync(db, requirement)
                    audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id, source="mcp", before=old, after=requirement_status, reason=reason)
        audit(db, actor.id, "release_batch.status_changed", "release_batch", batch.id, source="mcp", before=before, after=status, reason=reason)
        db.commit()
        return _batch_dict(batch, db)


@mcp.tool()
def update_version_delivery_status(batch_id: str, item_id: str, status: str) -> dict[str, Any]:
    """更新已锁定版本中一个需求的交付状态。"""
    _, actor = _identity("versions:write")
    allowed = {"not_started", "developing", "pr_open", "testing", "completed", "blocked", "removed"}
    with SessionLocal() as db:
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        item = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id).first()
        if not batch or not item or status not in allowed:
            raise ValueError("版本条目或交付状态无效")
        if batch.status in {"planning", "candidate_selection", "published", "completed", "cancelled"}:
            raise ValueError("当前版本状态不能修改交付进度")
        item.delivery_status = status
        mapping = {"developing": "developing", "pr_open": "developing", "testing": "testing", "completed": "release_ready"}
        if status in mapping:
            requirement = _requirement_or_error(db, item.requirement_id)
            before = requirement.status
            requirement.status = mapping[status]
            _enqueue_requirement_github_sync(db, requirement)
            audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id, source="mcp",
                  before=before, after=requirement.status, reason=f"版本交付状态：{status}")
        audit(db, actor.id, "release_batch.delivery_status", "release_batch", batch.id, source="mcp", item_id=item.id, status=status)
        db.commit()
        return {"id": item.id, "delivery_status": item.delivery_status}


@mcp.tool()
def upload_requirement_attachment(requirement_id: str, filename: str, content_base64: str,
                                  content_type: str = "application/octet-stream") -> dict[str, Any]:
    """为需求上传附件。内容必须是 Base64；单文件最大 5MB，最多 5 个附件。"""
    _, actor = _identity("requirements:write")
    safe_name = Path(filename).name[:255]
    suffix = Path(safe_name).suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".txt", ".log", ".json", ".pdf"}
    if not safe_name or suffix not in allowed:
        raise ValueError("附件类型不支持")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as exc:
        raise ValueError("content_base64 不是有效 Base64") from exc
    if not content or len(content) > settings.max_attachment_bytes:
        raise ValueError("附件为空或超过大小限制")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id)
        count = db.query(func.count(RequirementAttachment.id)).filter(RequirementAttachment.requirement_id == row.id).scalar() or 0
        if count >= settings.max_attachments_per_requirement:
            raise ValueError("附件数量已达到上限")
        upload_dir = Path(settings.upload_dir).resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"mcp-{secrets.token_hex(16)}{suffix}"
        target = upload_dir / stored_name
        target.write_bytes(content)
        item = RequirementAttachment(requirement_id=row.id, uploaded_by=actor.id, original_name=safe_name, stored_name=stored_name,
                                     content_type=content_type[:100], size_bytes=len(content), kind="image" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "file")
        try:
            db.add(item)
            db.flush()
            audit(db, actor.id, "requirement.attachment_uploaded", "requirement", row.id, source="mcp", attachment_id=item.id, name=safe_name)
            db.commit()
        except Exception:
            db.rollback()
            target.unlink(missing_ok=True)
            raise
        return {"id": item.id, "name": item.original_name, "content_type": item.content_type, "size_bytes": item.size_bytes, "kind": item.kind}


@mcp.tool()
def list_requirement_attachments(requirement_id: str) -> list[dict[str, Any]]:
    """列出需求附件元数据。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        _requirement_or_error(db, requirement_id)
        return [{"id": item.id, "name": item.original_name, "content_type": item.content_type, "size_bytes": item.size_bytes,
                 "kind": item.kind, "created_at": item.created_at.isoformat()} for item in db.query(RequirementAttachment).filter(
                 RequirementAttachment.requirement_id == requirement_id).order_by(RequirementAttachment.created_at).all()]


@mcp.tool()
def download_requirement_attachment(requirement_id: str, attachment_id: str) -> dict[str, Any]:
    """下载需求附件，返回 Base64 内容和元数据。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        _requirement_or_error(db, requirement_id)
        item = db.query(RequirementAttachment).filter(RequirementAttachment.id == attachment_id,
                                                       RequirementAttachment.requirement_id == requirement_id).first()
        if not item:
            raise ValueError("附件不存在")
        path = Path(settings.upload_dir).resolve() / item.stored_name
        if not path.is_file():
            raise ValueError("附件文件不存在")
        return {"id": item.id, "name": item.original_name, "content_type": item.content_type,
                "content_base64": base64.b64encode(path.read_bytes()).decode("ascii")}


@mcp.tool()
def get_requirement_records(requirement_id: str) -> dict[str, Any]:
    """读取需求的审计历史、编辑版本和审核记录。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        _requirement_or_error(db, requirement_id)
        events = db.query(AuditEvent).filter(AuditEvent.object_type == "requirement", AuditEvent.object_id == requirement_id).order_by(AuditEvent.created_at).all()
        revisions = db.query(RequirementRevision).filter(RequirementRevision.requirement_id == requirement_id).order_by(RequirementRevision.created_at).all()
        reviews = db.query(ReviewDecision).filter(ReviewDecision.requirement_id == requirement_id).order_by(ReviewDecision.created_at).all()
        return {"history": [{"id": x.id, "action": x.action, "details": x.details, "created_at": x.created_at.isoformat()} for x in events],
                "revisions": [{"id": x.id, "editor_id": x.editor_id, "snapshot": x.snapshot, "reason": x.reason, "created_at": x.created_at.isoformat()} for x in revisions],
                "reviews": [{"id": x.id, "reviewer_id": x.reviewer_id, "action": x.action, "reason": x.reason, "metadata": x.metadata_json, "created_at": x.created_at.isoformat()} for x in reviews]}


@mcp.tool()
def get_requirement_triage(requirement_id: str) -> list[dict[str, Any]]:
    """读取需求的 AI/规则分诊报告。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        _requirement_or_error(db, requirement_id)
        return [{"id": x.id, "requirement_version": x.requirement_version, "provider": x.provider, "model": x.model,
                 "report": x.report, "confidence": x.confidence, "created_at": x.created_at.isoformat()} for x in db.query(TriageReport).filter(
                 TriageReport.requirement_id == requirement_id).order_by(TriageReport.created_at.desc()).all()]


@mcp.tool()
def list_background_jobs(requirement_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """查询后台分诊、GitHub 同步和 Milestone 任务状态。"""
    _identity("requirements:read")
    with SessionLocal() as db:
        query = db.query(BackgroundJob)
        if requirement_id:
            query = query.filter(BackgroundJob.object_id == requirement_id)
        return [{"id": x.id, "job_type": x.job_type, "object_id": x.object_id, "status": x.status, "attempts": x.attempts,
                 "last_error": x.last_error, "created_at": x.created_at.isoformat()} for x in query.order_by(BackgroundJob.created_at.desc()).limit(min(max(limit, 1), 100)).all()]


@mcp.tool()
def set_requirement_following(requirement_id: str, following: bool) -> dict[str, Any]:
    """以令牌所属账号关注或取消关注需求。"""
    _, actor = _identity("requirements:write")
    with SessionLocal() as db:
        _requirement_or_error(db, requirement_id)
        row = db.query(RequirementFollower).filter(RequirementFollower.requirement_id == requirement_id,
                                                   RequirementFollower.user_id == actor.id).first()
        if following and not row:
            db.add(RequirementFollower(requirement_id=requirement_id, user_id=actor.id))
        elif not following and row:
            db.delete(row)
        db.commit()
        return {"requirement_id": requirement_id, "following": following}


@mcp.tool()
def withdraw_requirement(requirement_id: str, reason: str = "Agent 请求撤回") -> dict[str, Any]:
    """撤回令牌所属账号创建的、尚未排期的需求。"""
    _, actor = _identity("requirements:write")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id)
        if row.created_by != actor.id:
            raise PermissionError("只能撤回令牌所属账号创建的需求")
        if row.status in {"scheduled", "developing", "testing", "release_ready", "released"}:
            raise ValueError("已排期需求不能撤回")
        before, row.status = row.status, "withdrawn"
        audit(db, actor.id, "requirement.withdrawn", "requirement", row.id, source="mcp", before=before, after="withdrawn", reason=reason)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def unlink_github_issue(requirement_id: str) -> dict[str, Any]:
    """解除需求与 GitHub Issue 的关联，不会删除远端 Issue。"""
    _, actor = _identity("github:write")
    with SessionLocal() as db:
        row = _requirement_or_error(db, requirement_id)
        if not row.github_issue_number:
            raise ValueError("需求尚未关联 GitHub Issue")
        number = row.github_issue_number
        row.github_issue_number, row.github_issue_url, row.github_state = None, None, None
        audit(db, actor.id, "github.issue.unlinked", "requirement", row.id, source="mcp", issue_number=number)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def list_github_issues() -> list[dict[str, Any]]:
    """读取仓库中最近更新的 GitHub Issues（排除 Pull Request）。"""
    _identity("github:write")
    return [{"number": issue.get("number"), "title": issue.get("title"), "state": issue.get("state"),
             "url": issue.get("html_url"), "labels": [x.get("name") for x in issue.get("labels", [])]} for issue in GitHubClient().list_issues()]


@mcp.tool()
def sync_github_issues() -> dict[str, int]:
    """从 GitHub 导入/更新 Issue，并按统一映射记录平台状态变化。"""
    _, actor = _identity("github:write")
    issues = GitHubClient().list_issues()
    created = updated = skipped = 0
    with SessionLocal() as db:
        for issue in issues:
            number = issue.get("number")
            if not number:
                skipped += 1
                continue
            labels = [x.get("name", "") if isinstance(x, dict) else str(x) for x in issue.get("labels", [])]
            kind = "bug" if any(name.lower() == "bug" for name in labels) else ("feature" if any(name.lower() in {"enhancement", "feature"} for name in labels) else "improvement")
            row = db.query(Requirement).filter(Requirement.github_issue_number == number).first()
            if row:
                row.github_issue_url = issue.get("html_url")
                if row.source == "github":
                    row.title = (issue.get("title") or f"GitHub Issue #{number}")[:160]
                    row.description = ((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000]
                    row.type = kind
                _apply_github_status(db, row, issue, actor)
                updated += 1
                continue
            row = Requirement(public_number=(db.query(func.max(Requirement.public_number)).scalar() or 0) + 1, type=kind,
                              title=(issue.get("title") or f"GitHub Issue #{number}")[:160],
                              description=((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000],
                              severity="medium", visibility="public", status="submitted", source="github", created_by=actor.id,
                              github_issue_number=number, github_issue_url=issue.get("html_url"), github_state=issue.get("state"))
            db.add(row)
            db.flush()
            db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
            _apply_github_status(db, row, issue, actor)
            if row.status == "submitted":
                enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
            created += 1
        audit(db, actor.id, "github.issues.synchronized", "github_repository", settings.github_repo, source="mcp", created=created, updated=updated, skipped=skipped, total=len(issues))
        db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total": len(issues)}


@mcp.tool()
def sync_github_milestone(batch_id: str) -> dict[str, Any]:
    """立即创建/同步版本的 GitHub Milestone，并关联范围内的 Issues。"""
    _identity("github:write")
    with SessionLocal() as db:
        if not db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first():
            raise ValueError("版本批次不存在")
        sync_batch_milestone(db, batch_id)
        batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
        return _batch_dict(batch, db)


def _transport_security_settings() -> TransportSecuritySettings:
    """Trust the configured public endpoints while retaining DNS rebinding protection."""
    allowed_hosts = {"127.0.0.1:*", "localhost:*", "[::1]:*"}
    allowed_origins = {"http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"}

    for endpoint in (settings.mcp_public_url, settings.web_url):
        parsed = urlsplit(endpoint)
        if not parsed.scheme or not parsed.hostname:
            continue
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        allowed_hosts.update({host, f"{host}:*"})
        allowed_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(allowed_hosts),
        allowed_origins=sorted(allowed_origins),
    )


mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=_transport_security_settings(),
)
