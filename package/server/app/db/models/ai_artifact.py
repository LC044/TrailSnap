import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import UUID


class AIArtifact(Base):
    """A user-owned, editable output produced by the album agent."""

    __tablename__ = "ai_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content_json = Column(JSON, nullable=False, default=dict)
    html_content = Column(Text, nullable=True)
    html_config = Column(JSON, nullable=False, default=dict)
    source_photo_ids = Column(JSON, nullable=False, default=list)
    source_ticket_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(30), nullable=False, default="draft", index=True)
    version = Column(Integer, nullable=False, default=1)
    created_by_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
