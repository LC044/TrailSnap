"""User-defined long-lived life chapters and explainable suggestions."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.db.base import Base
from app.db.types import UUID


class LifeChapter(Base):
    __tablename__ = "life_chapters"
    __table_args__ = (
        Index("ix_life_chapters_owner_status_start", "owner_id", "status", "start_date"),
        UniqueConstraint("owner_id", "candidate_fingerprint", name="uq_life_chapter_candidate"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="candidate")
    origin = Column(String(16), nullable=False, default="auto")
    is_hidden = Column(Boolean, nullable=False, default=False)
    title = Column(String(80), nullable=False)
    summary = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    cover_photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    candidate_fingerprint = Column(String(64), nullable=True)
    evidence = Column(JSON, nullable=False, default=list)
    source_ids = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    deleted_at = Column(DateTime, nullable=True)
