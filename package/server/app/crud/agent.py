from typing import List, Optional, Union
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models.agent import AgentSession, AgentMessage
from app.schemas.agent import AgentSessionCreate, AgentSessionUpdate, AgentMessageCreate

# 隐藏的"记忆专用会话"标题标记。该会话不面向用户，仅用于承载长期记忆锚点，
# 因此在会话列表接口中会被过滤掉。
MEMORY_SESSION_TITLE = "__memory__"
# 记忆消息的 content_type，区别于普通对话消息。
MEMORY_CONTENT_TYPE = "memory"

# ---- Session CRUD ----

def get_session(db: Session, session_id: Union[str, UUID]) -> Optional[AgentSession]:
    if isinstance(session_id, str):
        session_id = UUID(session_id)
    return db.query(AgentSession).filter(AgentSession.id == session_id).first()

def get_sessions_by_user(
    db: Session, user_id: Union[str, UUID], skip: int = 0, limit: int = 100
) -> List[AgentSession]:
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    return (
        db.query(AgentSession)
        .filter(AgentSession.user_id == user_id)
        .filter(AgentSession.title != MEMORY_SESSION_TITLE)
        .order_by(desc(AgentSession.is_pinned), desc(AgentSession.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

def create_session(db: Session, obj_in: AgentSessionCreate, user_id: Union[str, UUID]) -> AgentSession:
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    db_obj = AgentSession(
        **obj_in.model_dump(exclude_unset=True, exclude_none=True),
        user_id=user_id,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def update_session(db: Session, db_obj: AgentSession, obj_in: AgentSessionUpdate) -> AgentSession:
    update_data = obj_in.model_dump(exclude_unset=True)
    for field in update_data:
        setattr(db_obj, field, update_data[field])
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_session(db: Session, session_id: Union[str, UUID]) -> bool:
    if isinstance(session_id, str):
        session_id = UUID(session_id)
    db_obj = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if db_obj:
        db.delete(db_obj)
        db.commit()
        return True
    return False

# ---- Message CRUD ----

def get_messages_by_session(
    db: Session, session_id: Union[str, UUID], skip: int = 0, limit: int = 100
) -> List[AgentMessage]:
    if isinstance(session_id, str):
        session_id = UUID(session_id)
    return (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )

def create_message(db: Session, obj_in: AgentMessageCreate) -> AgentMessage:
    db_obj = AgentMessage(**obj_in.model_dump())
    db.add(db_obj)
    
    # Update session's summary_update_time
    session = db.query(AgentSession).filter(AgentSession.id == obj_in.session_id).first()
    if session:
        session.summary_update_time = datetime.now()
        db.add(session)
        
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_messages_by_session(db: Session, session_id: Union[str, UUID]) -> bool:
    if isinstance(session_id, str):
        session_id = UUID(session_id)
    db.query(AgentMessage).filter(AgentMessage.session_id == session_id).delete()
    db.commit()
    return True

# ---- 长期记忆（照片即记忆）----
# 设计：每个用户拥有一个隐藏的"记忆专用会话"（title == MEMORY_SESSION_TITLE），
# 其下仅保存一条 role="system"、content_type=MEMORY_CONTENT_TYPE 的消息，
# 记忆锚点全部存放在该消息的 content_ext 中。这样无需新增任何表或字段。

def get_or_create_memory_session(db: Session, user_id: Union[str, UUID]) -> AgentSession:
    """获取用户的记忆专用会话，不存在则创建。"""
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    session = (
        db.query(AgentSession)
        .filter(
            AgentSession.user_id == user_id,
            AgentSession.title == MEMORY_SESSION_TITLE,
        )
        .first()
    )
    if session:
        return session
    session = AgentSession(
        user_id=user_id,
        title=MEMORY_SESSION_TITLE,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def get_memory_message(db: Session, user_id: Union[str, UUID]) -> Optional[AgentMessage]:
    """获取用户记忆会话下承载记忆锚点的那条消息（可能不存在）。"""
    session = get_or_create_memory_session(db, user_id)
    return (
        db.query(AgentMessage)
        .filter(
            AgentMessage.session_id == session.id,
            AgentMessage.content_type == MEMORY_CONTENT_TYPE,
        )
        .order_by(AgentMessage.created_at)
        .first()
    )

def upsert_memory_message(
    db: Session, user_id: Union[str, UUID], content_ext: dict
) -> AgentMessage:
    """写入/更新用户的记忆锚点。整条 content_ext 覆盖式写入（合并逻辑由上层负责）。"""
    session = get_or_create_memory_session(db, user_id)
    msg = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.session_id == session.id,
            AgentMessage.content_type == MEMORY_CONTENT_TYPE,
        )
        .order_by(AgentMessage.created_at)
        .first()
    )
    if msg:
        msg.content_ext = content_ext
        db.add(msg)
    else:
        msg = AgentMessage(
            session_id=session.id,
            role="system",
            content="",  # content 非空约束：记忆内容放在 content_ext，这里留空字符串
            content_type=MEMORY_CONTENT_TYPE,
            content_ext=content_ext,
        )
        db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
