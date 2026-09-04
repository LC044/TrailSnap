#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/8/10 22:29 
@Author      : SiYuan 
@Email       : sixyuan044@gmail.com
@File        : server-album.py 
@Description : 
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Index, JSON, UniqueConstraint, Float
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.db.types import UUID, Vector

from app.db.base import Base


class Album(Base):
    """
    相册表
    """
    __tablename__ = 'albums'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    create_time = Column(DateTime, default=datetime.now)
    description = Column(Text)

    # Relationships
    cover_id = Column("cover", UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    cover = relationship("Photo", foreign_keys=[cover_id])

    # New Fields
    type = Column(String(20), nullable=False, default="user") # user, smart, conditional
    condition = Column(JSON, nullable=True)
    query_embedding = Column(Vector(512), nullable=True)
    num_photos = Column(Integer, default=0)
    threshold = Column(Float, default=0.25, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    # M:N relationship with Photo
    photos = relationship("Photo", secondary="album_photos", back_populates="albums")

    # Shared users
    shared_users = relationship("User", secondary="album_shared_users", backref="shared_albums")


class AlbumPhoto(Base):
    __tablename__ = 'album_photos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    album_id = Column(UUID(as_uuid=True), ForeignKey('albums.id', ondelete='CASCADE'), nullable=False)
    photo_id = Column(UUID(as_uuid=True), ForeignKey('photos.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('album_id', 'photo_id', name='uq_album_photo'),
        # The unique constraint's index is keyed (album_id, photo_id), so it cannot
        # serve a photo_id-only lookup. Without this index, deleting a photo forces
        # a full scan of album_photos to enforce the ON DELETE CASCADE — which made
        # emptying a large recycle bin quadratic.
        Index('ix_album_photos_photo_id', 'photo_id'),
    )


class AlbumSharedUser(Base):
    __tablename__ = 'album_shared_users'

    album_id = Column(UUID(as_uuid=True), ForeignKey('albums.id', ondelete='CASCADE'), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    created_at = Column(DateTime, default=datetime.now)
