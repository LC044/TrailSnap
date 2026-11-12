"""CLIP rules, reproducible revisions and manual classification decisions."""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    JSON,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from app.db.base import Base
from app.db.types import UUID


class ClipCategory(Base):
    __tablename__ = "clip_categories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("photo_tags.id", ondelete="CASCADE"),
        nullable=False,
    )
    preset_key = Column(String(100))
    groups = Column(JSON, nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    __table_args__ = (
        UniqueConstraint("owner_id", "preset_key", name="uq_clip_preset_owner"),
    )


class ClipRuleRevision(Base):
    __tablename__ = "clip_rule_revisions"
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clip_categories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision = Column(Integer, primary_key=True)
    descriptions = Column(JSON, nullable=False)
    strictness = Column(String(20), nullable=False, default="standard")
    thresholds = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class TagDecision(Base):
    __tablename__ = "photo_tag_decisions"
    photo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("photo_tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    keep = Column(Boolean, nullable=False)
