#!/usr/bin/env python
# -*- coding: utf-8 -*-

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, BigInteger, Integer, Enum, Float, JSON, Boolean, Index
from app.db.types import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class FileType(enum.Enum):
    image = 'image'
    video = 'video'
    live_photo = 'live_photo'

class ImageType(str, enum.Enum):
    SCREENSHOT = "Screenshot"
    CAMERA = "Camera"
    OTHER = "Other"

class Photo(Base):
    __tablename__ = "photos"
    # PostgreSQL compiles this as a hash index so arbitrarily long TEXT paths
    # do not exceed the B-tree index tuple limit. SQLite ignores the dialect
    # option and keeps its regular B-tree index.
    __table_args__ = (
        Index("ix_photos_file_path", "file_path", postgresql_using="hash"),
        Index("uq_photos_owner_backup_key", "owner_id", "backup_key", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), index=True)
    photo_time = Column(DateTime, index=True)
    file_path = Column(Text, nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    upload_time = Column(DateTime, default=datetime.now)
    size = Column(BigInteger)
    width = Column(Integer)
    height = Column(Integer)
    duration = Column(Float, default=0)
    image_type = Column(Enum(ImageType))  # Screenshot, Camera, Other
    md5 = Column(String(32), nullable=True, index=True)
    backup_key = Column(String(255), nullable=True)
    # Task Status Tracking: {"thumbnail": true, "metadata": true, "face": false}
    processed_tasks = Column(JSON, default={})
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    # Soft delete fields
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    albums = relationship("Album", secondary="album_photos", back_populates="photos")
    metadata_info = relationship("PhotoMetadata", uselist=False, back_populates="photo", cascade="all, delete-orphan")
    faces = relationship("Face", back_populates="photo", cascade="all, delete-orphan")
    image_description = relationship("ImageDescription", uselist=False, back_populates="photo", cascade="all, delete-orphan")
    color_info = relationship("PhotoColor", uselist=False, back_populates="photo", cascade="all, delete-orphan")
    tags = relationship("PhotoTag", secondary="photo_tag_relations", backref="photos")

    @property
    def album_ids(self):
        return [str(album.id) for album in self.albums]
