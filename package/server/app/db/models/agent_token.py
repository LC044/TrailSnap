from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from app.db.types import UUID
import uuid
from datetime import datetime
from app.db.base import Base

class AgentToken(Base):
    __tablename__ = "agent_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
