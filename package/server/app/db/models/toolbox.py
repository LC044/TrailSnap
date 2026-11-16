"""Persistent plans separate user confirmation from filesystem execution."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.types import TypeDecorator
from app.db.base import Base
from app.db.types import PortableJSON, UUID


class PlanPath(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        from app.utils.portable_config import transform_paths
        return transform_paths(value, encode=True, key="source_path")

    def process_result_value(self, value, dialect):
        from app.utils.portable_config import transform_paths
        return transform_paths(value, encode=False, key="source_path")


class ToolboxPlan(Base):
    __tablename__ = "toolbox_plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="preview")
    version = Column(Integer, nullable=False, default=1)
    request = Column(PortableJSON, nullable=False)
    summary = Column(PortableJSON, nullable=False, default=dict)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    stop_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    __table_args__ = (Index("ix_toolbox_plans_owner_created", "owner_id", "created_at"),)


class ToolboxPlanItem(Base):
    __tablename__ = "toolbox_plan_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("toolbox_plans.id", ondelete="CASCADE"), nullable=False)
    photo_id = Column(UUID(as_uuid=True), nullable=False)
    source = Column(PlanPath, nullable=False)
    target = Column(PlanPath, nullable=False, default="")
    status = Column(String(20), nullable=False, default="ready")
    reason = Column(Text, nullable=False, default="")
    fingerprint = Column(PortableJSON, nullable=False, default=dict)
    detail = Column(PortableJSON, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_toolbox_items_plan_status", "plan_id", "status", "id"),
        Index("ix_toolbox_items_photo", "photo_id"),
    )


class CleanupScope(Base):
    """Frozen comparison population; outside references can never be selected."""
    __tablename__ = "cleanup_scope"
    plan_id = Column(UUID(as_uuid=True), ForeignKey("toolbox_plans.id", ondelete="CASCADE"), primary_key=True)
    photo_id = Column(UUID(as_uuid=True), primary_key=True)
    in_scope = Column(Boolean, nullable=False)


class CleanupGroup(Base):
    __tablename__ = "cleanup_groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("toolbox_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    representative_id = Column(UUID(as_uuid=True), nullable=False)
    key = Column(String(128), nullable=False)
    count = Column(Integer, nullable=False, default=0)


class CleanupMember(Base):
    __tablename__ = "cleanup_members"
    plan_id = Column(UUID(as_uuid=True), ForeignKey("toolbox_plans.id", ondelete="CASCADE"), primary_key=True)
    photo_id = Column(UUID(as_uuid=True), primary_key=True)
    group_id = Column(Integer, ForeignKey("cleanup_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    in_scope = Column(Boolean, nullable=False)


class CleanupSelection(Base):
    __tablename__ = "cleanup_selections"
    plan_id = Column(UUID(as_uuid=True), ForeignKey("toolbox_plans.id", ondelete="CASCADE"), primary_key=True)
    item_id = Column(Integer, ForeignKey("toolbox_plan_items.id", ondelete="CASCADE"), primary_key=True)


class CleanupHash(Base):
    __tablename__ = "cleanup_hashes"
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    size = Column(String(32), nullable=False)
    mtime_ns = Column(String(32), nullable=False)
    md5 = Column(String(32), nullable=False)
    path_digest = Column(String(64), nullable=False)
