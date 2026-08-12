from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey, JSON
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base

class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    title = Column(String(255), nullable=True)
    status = Column(String(50), default="active")
    context_summary = Column(Text, nullable=True)
    summary_update_time = Column(DateTime(timezone=True), nullable=True)
    is_pinned = Column(Boolean, default=False)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(50), nullable=False)  # user/assistant/system
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default="text")
    content_ext = Column(JSON, nullable=True)
    reasoning = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
