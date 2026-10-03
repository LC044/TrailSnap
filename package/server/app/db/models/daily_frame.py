"""Owner-scoped daily selections and immutable rendered works."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, false

from app.db.base import Base
from app.db.types import UUID


class DailyFrameCalendar(Base):
    __tablename__ = "daily_frame_calendars"

    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    timezone = Column(String(80), nullable=False)
    locked = Column(Boolean, nullable=False, default=False, server_default=false())
    revision = Column(Integer, nullable=False, default=0, server_default="0")


class DailyFrame(Base):
    __tablename__ = "daily_frames"
    __table_args__ = (UniqueConstraint("owner_id", "day", name="uq_daily_frame_owner_day"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Date, nullable=False)
    # Keep the selection when the source is permanently deleted. Do not cascade.
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    mode = Column(String(8), nullable=False, default="still")
    start_seconds = Column(Float, nullable=False, default=0)
    caption = Column(String(120), nullable=False, default="")
    version = Column(Integer, nullable=False, default=1)
    removed = Column(Boolean, nullable=False, default=False, server_default=false())
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class DailyFrameWork(Base):
    __tablename__ = "daily_frame_works"
    __table_args__ = (UniqueConstraint("owner_id", "fingerprint", name="uq_daily_frame_work_fingerprint"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    is_preview = Column(Boolean, nullable=False, default=False, server_default=false())
    status = Column(String(16), nullable=False, default="queued")
    generation = Column(Integer, nullable=False, default=1)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    processed_items = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    output_path = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    deleted_at = Column(DateTime, nullable=True)
