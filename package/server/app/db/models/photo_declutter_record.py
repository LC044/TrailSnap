#!/usr/bin/env python
# -*- coding: utf-8 -*-

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from app.db.base import Base
from app.db.types import UUID


class PhotoDeclutterRecord(Base):
    """A user's durable keep/delete decision in the swipe-filter workflow."""

    __tablename__ = "photo_declutter_records"
    __table_args__ = (
        UniqueConstraint("owner_id", "photo_id", name="uq_photo_declutter_owner_photo"),
        CheckConstraint("decision IN ('keep', 'delete')", name="ck_photo_declutter_decision"),
        Index("ix_photo_declutter_owner_decision", "owner_id", "decision"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision = Column(String(16), nullable=False)
    processed_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
