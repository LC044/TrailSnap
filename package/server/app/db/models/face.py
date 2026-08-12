#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, DECIMAL, JSON, Integer, Index
from app.db.types import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.types import VECTOR

from app.db.base import Base

class FaceIdentity(Base):
    __tablename__ = "face_identities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_name = Column(String(500), index=True)
    description = Column(String(500), nullable=True)
    tags = Column(JSON, nullable=True)
    # use_alter=True to handle circular dependency during creation
    default_face_id = Column(Integer, ForeignKey("faces.id", use_alter=True, ondelete="SET NULL"), nullable=True)
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_deleted = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)

    # Relationships
    faces = relationship("Face", back_populates="identity", foreign_keys="Face.face_identity_id")

class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    face_identity_id = Column(UUID(as_uuid=True), ForeignKey("face_identities.id", ondelete="SET NULL"), nullable=True)
    face_feature = Column(VECTOR(512))  # Human face feature vector
    face_rect = Column(JSON)     # 人脸检测框 [x1, y1, x2, y2]
    face_confidence = Column(DECIMAL(5, 4))
    recognize_confidence = Column(DECIMAL(5, 4))
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    photo = relationship("Photo", back_populates="faces")
    identity = relationship("FaceIdentity", back_populates="faces", foreign_keys=[face_identity_id])

    # 索引定义（核心新增）
    __table_args__ = (
        # 为photo_id加索引：命名规范「idx_表名_字段名」
        Index("idx_face_photo_id", "photo_id"),
        # 为face_identity_id加索引
        Index("idx_face_identity_id", "face_identity_id"),
        # 向量索引
        Index(
            "idx_face_feature",
            "face_feature",
            postgresql_using="hnsw",
            postgresql_ops={"face_feature": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
    )
