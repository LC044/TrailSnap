import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from app.db.types import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class ImageCluster(Base):
    __tablename__ = "image_clusters"

    cluster_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(255), nullable=True)
    cluster_type = Column(String(50), nullable=False)
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    photos = relationship("PhotoCluster", back_populates="cluster", cascade="all, delete-orphan")


class PhotoCluster(Base):
    __tablename__ = "photo_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("image_clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    cluster = relationship("ImageCluster", back_populates="photos")
    photo = relationship("Photo")

    __table_args__ = (
        # This table has no unique constraint to piggyback on, so a photo_id
        # lookup was a full table scan. Every photo deletion has to run one to
        # enforce ON DELETE CASCADE, which is what made purging a large recycle
        # bin degrade super-linearly.
        Index("ix_photo_clusters_photo_id", "photo_id"),
        # Cluster membership is always read cluster-first ("show me this group"),
        # and the cascade from image_clusters needs it too.
        Index("ix_photo_clusters_cluster_id", "cluster_id"),
    )
