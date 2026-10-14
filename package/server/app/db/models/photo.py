#!/usr/bin/env python
# -*- coding: utf-8 -*-

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, BigInteger, Integer, Enum, Float, JSON, Boolean, Index, text
from app.db.types import UUID
from sqlalchemy.orm import relationship, object_session
from sqlalchemy.ext.hybrid import hybrid_property
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
        Index("ix_photos_storage_reference", "owner_id", "storage_root_id"),
        Index("uq_photos_owner_backup_key", "owner_id", "backup_key", unique=True),
        Index(
            "ix_photos_owner_alive",
            "owner_id",
            "id",
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = false"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), index=True)
    photo_time = Column(DateTime, index=True)
    _file_path = Column("file_path", Text, nullable=False)
    storage_root_id = Column(UUID(as_uuid=True), ForeignKey("storage_roots.id"), nullable=True)
    storage_relative_path = Column(Text, nullable=True)
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

    @hybrid_property
    def file_path(self):
        # Historical Alembic migrations deliberately load only pre-existing columns.
        if "storage_root_id" not in self.__dict__:
            return self._file_path
        if self.storage_root_id is None and self.storage_relative_path is None:
            return self._file_path
        if self.storage_root_id is None or not self.storage_relative_path:
            raise ValueError("Incomplete photo storage reference")
        from app.service.storage_paths import resolve_path
        return str(resolve_path(self.owner_id, self.storage_root_id, self.storage_relative_path, object_session(self)))

    @file_path.setter
    def file_path(self, value):
        self._file_path = value
        # New locations are encoded when the transaction is flushed, after owner_id
        # has been populated. Clear stale references immediately after a rename.
        from sqlalchemy import inspect
        if "storage_root_id" in self.__dict__ or inspect(self).transient:
            self.storage_root_id = None
            self.storage_relative_path = None

    @file_path.expression
    def file_path(cls):
        from app.service.storage_paths import photo_path_expression
        return photo_path_expression(cls)

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
