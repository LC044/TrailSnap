"""User-authored story exclusions for person timelines."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index
from app.db.base import Base
from app.db.types import UUID


class PersonTimelineHide(Base):
    __tablename__ = "person_timeline_hides"
    __table_args__ = (
        Index("ix_person_timeline_hides_scope", "owner_id", "person_a_id", "person_b_id", "start_at", "end_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    person_a_id = Column(UUID(as_uuid=True), ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False)
    person_b_id = Column(UUID(as_uuid=True), nullable=False, default=lambda: uuid.UUID(int=0))
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
