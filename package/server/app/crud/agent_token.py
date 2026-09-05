import secrets
import string
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from functools import lru_cache

from sqlalchemy.orm import Session
from app.db.models.agent_token import AgentToken

# 使用一个简单的全局字典作为缓存，以便可以手动使缓存失效
_token_cache = {}

def generate_token_string(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "ts_" + ''.join(secrets.choice(alphabet) for _ in range(length))

def create_agent_token(
    db: Session,
    user_id: UUID,
    name: str,
    expires_at: datetime,
    scopes: Optional[List[str]] = None,
) -> AgentToken:
    token_str = generate_token_string()
    db_obj = AgentToken(
        user_id=user_id,
        name=name,
        token=token_str,
        expires_at=expires_at,
        scopes=scopes or ["photos:read", "albums:read", "people:read"],
        is_deleted=False
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    
    # 存入缓存
    _token_cache[token_str] = db_obj
    return db_obj

def get_tokens_by_user(db: Session, user_id: UUID) -> List[AgentToken]:
    return db.query(AgentToken).filter(
        AgentToken.user_id == user_id,
        AgentToken.is_deleted == False
    ).order_by(AgentToken.created_at.desc()).all()

def delete_agent_token(db: Session, token_id: UUID, user_id: UUID) -> bool:
    token_obj = db.query(AgentToken).filter(
        AgentToken.id == token_id,
        AgentToken.user_id == user_id
    ).first()
    
    if not token_obj:
        return False
        
    token_obj.is_deleted = True
    db.commit()
    
    # 使缓存失效
    if token_obj.token in _token_cache:
        del _token_cache[token_obj.token]
        
    return True

def get_token_by_string(db: Session, token: str) -> Optional[AgentToken]:
    if token in _token_cache:
        cached_token = _token_cache[token]
        if not cached_token.is_deleted:
            return cached_token
            
    db_obj = db.query(AgentToken).filter(
        AgentToken.token == token,
        AgentToken.is_deleted == False
    ).first()
    
    if db_obj:
        _token_cache[token] = db_obj
        
    return db_obj
