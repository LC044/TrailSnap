"""Administrative user and agent-token HTTP endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .responses import ok
from ..db import get_db
from ..domain.common import audit
from ..models import AgentToken, DeliveryTask, User
from ..presenters import user_data
from ..schemas import AgentTokenCreate, RoleUpdate
from ..security import create_agent_token_value, manager, owner


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(_owner: User = Depends(owner), db: Session = Depends(get_db)):
    return ok([user_data(row, db) for row in db.query(User).order_by(User.created_at).all()])


@router.patch("/users/{user_id}/role")
def update_user_role(user_id: str, payload: RoleUpdate, actor: User = Depends(owner), db: Session = Depends(get_db)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if row.role == "owner":
        raise HTTPException(status_code=409, detail="Owner role cannot be changed here")
    before = row.role
    row.role = payload.role
    audit(db, actor.id, "user.role_changed", "user", row.id, before=before, after=row.role)
    db.commit()
    return ok(user_data(row, db))


@router.get("/agent-tokens")
def list_agent_tokens(actor: User = Depends(manager), db: Session = Depends(get_db)):
    query = db.query(AgentToken)
    if actor.role != "owner":
        query = query.filter(AgentToken.created_by == actor.id)
    rows = query.order_by(AgentToken.created_at.desc()).all()
    return ok([{
        "id": row.id,
        "name": row.name,
        "token_prefix": row.token_prefix,
        "scopes": row.scopes,
        "project_key": row.project_key,
        "agent_role": row.agent_role,
        "task_id": row.task_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "created_at": row.created_at.isoformat(),
    } for row in rows])


@router.post("/agent-tokens")
def create_agent_token(payload: AgentTokenCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    if payload.task_id and not db.query(DeliveryTask).filter(DeliveryTask.id == payload.task_id).first():
        raise HTTPException(status_code=404, detail="Delivery task not found")
    if "tasks:claim" in payload.scopes and payload.agent_role not in {None, "coding"}:
        raise HTTPException(status_code=409, detail="Phase B only supports coding task claims")
    value, prefix, token_hash = create_agent_token_value()
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    row = AgentToken(
        name=payload.name,
        token_prefix=prefix,
        token_hash=token_hash,
        scopes=sorted(set(payload.scopes)),
        created_by=actor.id,
        expires_at=expires_at,
        project_key=payload.project_key,
        agent_role=payload.agent_role,
        task_id=payload.task_id,
    )
    db.add(row)
    db.flush()
    audit(db, actor.id, "agent_token.created", "agent_token", row.id, name=row.name, scopes=row.scopes)
    db.commit()
    return ok({
        "id": row.id,
        "name": row.name,
        "token": value,
        "token_prefix": prefix,
        "scopes": row.scopes,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }, "令牌仅显示一次，请立即保存")


@router.delete("/agent-tokens/{token_id}")
def revoke_agent_token(token_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    query = db.query(AgentToken).filter(AgentToken.id == token_id)
    if actor.role != "owner":
        query = query.filter(AgentToken.created_by == actor.id)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent token not found")
    row.revoked_at = datetime.now(timezone.utc)
    audit(db, actor.id, "agent_token.revoked", "agent_token", row.id)
    db.commit()
    return ok({"revoked": True})
