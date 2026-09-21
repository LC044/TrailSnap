"""Persistent, user-owned memory events and their explainable associations."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.types import UUID


class MemoryStatus(str, enum.Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MemoryOrigin(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"
    ALBUM = "album"
    AGENT = "agent"


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_owner_status_start", "owner_id", "status", "start_time"),
        Index("ix_memories_owner_updated", "owner_id", "updated_at"),
        UniqueConstraint("owner_id", "candidate_fingerprint", name="uq_memories_owner_fingerprint"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(MemoryStatus), nullable=False, default=MemoryStatus.CANDIDATE, index=True)
    origin = Column(Enum(MemoryOrigin), nullable=False, default=MemoryOrigin.AUTO)
    title = Column(String(255), nullable=False)
    title_source = Column(String(16), nullable=False, default="system")
    story = Column(Text, nullable=True)
    story_source = Column(String(16), nullable=False, default="system")
    story_generation_status = Column(String(16), nullable=False, default="idle")
    story_generation_started_at = Column(DateTime, nullable=True)
    story_generation_error = Column(Text, nullable=True)
    cover_photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    cover_source = Column(String(16), nullable=False, default="system")
    start_time = Column(DateTime, nullable=True, index=True)
    end_time = Column(DateTime, nullable=True)
    time_source = Column(String(16), nullable=False, default="inferred")
    confidence = Column(Float, nullable=True)
    algorithm_version = Column(String(32), nullable=True)
    candidate_fingerprint = Column(String(64), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    confirmed_at = Column(DateTime, nullable=True)
    ignored_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    deleted_at = Column(DateTime, nullable=True)

    cover = relationship("Photo", foreign_keys=[cover_photo_id])
    photo_links = relationship("MemoryPhoto", cascade="all, delete-orphan", back_populates="memory")
    people = relationship("MemoryPerson", cascade="all, delete-orphan", back_populates="memory")
    places = relationship("MemoryPlace", cascade="all, delete-orphan", back_populates="memory")
    tickets = relationship("MemoryTicket", cascade="all, delete-orphan", back_populates="memory")
    evidence = relationship("MemoryEvidence", cascade="all, delete-orphan", back_populates="memory")


class MemoryPhoto(Base):
    __tablename__ = "memory_photos"
    __table_args__ = (
        UniqueConstraint("memory_id", "photo_id", name="uq_memory_photo"),
        Index("ix_memory_photos_photo_id", "photo_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False, default="normal")
    source = Column(String(24), nullable=False, default="inferred")
    confidence = Column(Float, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    memory = relationship("Memory", back_populates="photo_links")
    photo = relationship("Photo")


class MemoryPerson(Base):
    __tablename__ = "memory_people"
    __table_args__ = (UniqueConstraint("memory_id", "face_identity_id", name="uq_memory_person"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    face_identity_id = Column(UUID(as_uuid=True), ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(24), nullable=False, default="inferred")
    confidence = Column(Float, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=False)

    memory = relationship("Memory", back_populates="people")
    identity = relationship("FaceIdentity")


class MemoryPlace(Base):
    __tablename__ = "memory_places"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    level = Column(String(24), nullable=False, default="city")
    source = Column(String(24), nullable=False, default="inferred")
    confidence = Column(Float, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=False)

    memory = relationship("Memory", back_populates="places")
    scene = relationship("Scene")


class MemoryTicket(Base):
    __tablename__ = "memory_tickets"
    __table_args__ = (UniqueConstraint("memory_id", "ticket_type", "ticket_id", name="uq_memory_ticket"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_type = Column(String(16), nullable=False)
    ticket_id = Column(String(36), nullable=False)
    source = Column(String(24), nullable=False, default="inferred")
    confidence = Column(Float, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=False)

    memory = relationship("Memory", back_populates="tickets")


class MemoryEvidence(Base):
    __tablename__ = "memory_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(String(24), nullable=False)
    summary = Column(String(500), nullable=False)
    score = Column(Float, nullable=True)
    source_refs = Column(JSON, nullable=False, default=list)
    payload = Column(JSON, nullable=False, default=dict)
    algorithm_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    memory = relationship("Memory", back_populates="evidence")


class MemoryRelation(Base):
    __tablename__ = "memory_relations"
    __table_args__ = (UniqueConstraint("memory_id", "related_memory_id", "relation_type", name="uq_memory_relation"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    related_memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
