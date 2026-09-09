"""Authenticated MCP tools for requirement and release management."""

from datetime import datetime, timezone
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from sqlalchemy import func

from .config import settings
from .db import SessionLocal
from .models import (
    AgentToken, ReleaseBatch, ReleaseBatchItem, Requirement, RequirementFollower, RequirementRevision, ReviewDecision, User,
)
from .security import resolve_agent_token
from .services import GitHubClient, audit, enqueue, requirement_snapshot


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
    version="0.2.0",
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
        "current_behavior": row.current_behavior, "expected_behavior": row.expected_behavior,
        "steps_to_reproduce": row.steps_to_reproduce, "severity": row.severity,
        "product_version": row.product_version, "visibility": row.visibility, "status": row.status,
        "priority": row.priority, "risk_level": row.risk_level, "review_reason": row.review_reason,
        "github_issue_number": row.github_issue_number, "github_issue_url": row.github_issue_url,
        "github_state": row.github_state, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


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
        number_text = requirement_id.upper().removeprefix("REQ-").lstrip("0") or "0"
        row = db.query(Requirement).filter(
            Requirement.public_number == int(number_text)
        ).first() if number_text.isdigit() else db.query(Requirement).filter(Requirement.id == requirement_id).first()
        if not row:
            raise ValueError("需求不存在")
        return _requirement_dict(row)


@mcp.tool()
def create_requirement(type: str, title: str, description: str, severity: str = "medium", visibility: str = "public", expected_behavior: str | None = None) -> dict[str, Any]:
    """以令牌所属管理员身份创建需求。"""
    _, actor = _identity("requirements:write")
    if type not in {"bug", "improvement", "feature"} or severity not in {"low", "medium", "high", "critical"}:
        raise ValueError("需求类型或影响程度无效")
    if visibility not in {"public", "private"} or len(title.strip()) < 4 or len(description.strip()) < 10:
        raise ValueError("需求内容或公开范围无效")
    with SessionLocal() as db:
        public_number = (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1
        row = Requirement(public_number=public_number, type=type, title=title.strip(), description=description.strip(), severity=severity,
                          visibility=visibility, expected_behavior=expected_behavior, created_by=actor.id)
        db.add(row)
        db.flush()
        db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
        enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "requirement.created_by_agent", "requirement", row.id)
        db.commit()
        db.refresh(row)
        return _requirement_dict(row)


@mcp.tool()
def update_requirement(requirement_id: str, title: str | None = None, description: str | None = None,
                       expected_behavior: str | None = None, severity: str | None = None,
                       visibility: str | None = None) -> dict[str, Any]:
    """更新需求正文；未传入的字段保持不变。"""
    _, actor = _identity("requirements:write")
    if severity and severity not in {"low", "medium", "high", "critical"}:
        raise ValueError("影响程度无效")
    if visibility and visibility not in {"public", "private"}:
        raise ValueError("公开范围无效")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row:
            raise ValueError("需求不存在")
        db.add(RequirementRevision(requirement_id=row.id, editor_id=actor.id, snapshot=requirement_snapshot(row), reason="mcp updated"))
        values = {"title": title, "description": description, "expected_behavior": expected_behavior,
                  "severity": severity, "visibility": visibility}
        for field, value in values.items():
            if value is not None:
                setattr(row, field, value.strip() if isinstance(value, str) else value)
        row.version += 1
        enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "requirement.updated", "requirement", row.id, source="mcp", version=row.version)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def review_requirement(requirement_id: str, action: str, reason: str, priority: str = "normal", risk_level: str = "medium") -> dict[str, Any]:
    """人工授权的 Agent 审核需求并修改其状态。"""
    _, actor = _identity("requirements:review")
    statuses = {"candidate": "candidate", "needs_information": "needs_information", "rejected": "rejected",
                "deferred": "deferred", "close": "closed"}
    if action not in statuses or len(reason.strip()) < 2:
        raise ValueError("审核动作或理由无效")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row:
            raise ValueError("需求不存在")
        row.status, row.review_reason, row.priority, row.risk_level = statuses[action], reason.strip(), priority, risk_level
        db.add(ReviewDecision(requirement_id=row.id, reviewer_id=actor.id, action=action, reason=reason,
                              metadata_json={"source": "mcp", "priority": priority, "risk_level": risk_level}))
        audit(db, actor.id, f"requirement.{action}", "requirement", row.id, source="mcp", reason=reason)
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
        audit(db, actor.id, "github.issue.linked", "requirement", row.id, source="mcp", issue_number=issue_number)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def close_github_issue(requirement_id: str, reason: str) -> dict[str, Any]:
    """关闭已关联的 GitHub Issue，并同步关闭平台需求。"""
    _, actor = _identity("github:write")
    with SessionLocal() as db:
        row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
        if not row or not row.github_issue_number:
            raise ValueError("需求不存在或尚未关联 Issue")
        data = GitHubClient().update_issue_state(row.github_issue_number, "closed")
        row.github_state, row.status, row.review_reason = data["state"], "closed", reason.strip()
        audit(db, actor.id, "github.issue.closed", "requirement", row.id, source="mcp",
              issue_number=row.github_issue_number, reason=reason)
        db.commit()
        return _requirement_dict(row)


@mcp.tool()
def list_versions() -> list[dict[str, Any]]:
    """列出版本批次及状态。"""
    _identity("versions:read")
    with SessionLocal() as db:
        return [{"id": row.id, "name": row.name, "version_name": row.version_name, "goal": row.goal,
                 "status": row.status, "target_date": row.target_date, "locked_at": row.locked_at.isoformat() if row.locked_at else None}
                for row in db.query(ReleaseBatch).order_by(ReleaseBatch.created_at.desc()).all()]


mcp_http_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)
