import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import UUID


class AgentActionPlan(Base):
    """A user-confirmed, auditable and reversible Agent write plan."""

    __tablename__ = "agent_action_plans"
    __table_args__ = (
        Index("ix_agent_action_plans_user_status", "user_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_type = Column(String(50), nullable=False, default="album_organize")
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="proposed")
    operations = Column(JSON, nullable=False, default=dict)
    preview = Column(JSON, nullable=False, default=dict)
    undo_data = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    undone_at = Column(DateTime(timezone=True), nullable=True)
