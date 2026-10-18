"""Stable storage identities; locations are relative only for portable libraries."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Index, CheckConstraint
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID


class StorageRoot(Base):
    __tablename__ = "storage_roots"
    __table_args__ = (
        Index("ix_storage_roots_owner", "owner_id"),
        CheckConstraint("kind IN ('managed', 'instance-relative', 'external')", name="ck_storage_root_kind"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False)
    location = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
