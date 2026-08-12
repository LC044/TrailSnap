#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, Integer, UniqueConstraint, Float
from app.db.types import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.base import Base

class PhotoTag(Base):
    __tablename__ = "photo_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_name = Column(String(50), nullable=False, index=True)
    type = Column(String(50), nullable=True)
    cover_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_deleted = Column(Boolean, default=False)

class PhotoTagRelation(Base):
    __tablename__ = "photo_tag_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("photo_tags.id", ondelete="CASCADE"), nullable=False)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.now)
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('photo_id', 'tag_id', name='uq_photo_tag'),
    )
