import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, JSON, Integer, Index, text
from app.db.types import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class PhotoColor(Base):
    """照片色彩与情绪数据 - 存储每张照片的主色调、亮度、饱和度及情绪暗示"""
    __tablename__ = "photo_colors"
    __table_args__ = (Index('ix_photo_colors_analysis_version_attempted', 'analysis_version', 'analysis_attempted_at'),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    # 主色调列表，如 [{"hex": "#E8A87C", "ratio": 0.45}, ...]，按占比降序
    dominant_colors = Column(JSON, nullable=True)
    # 平均亮度 0-1
    brightness = Column(Float, nullable=True)
    # 平均饱和度 0-1
    saturation = Column(Float, nullable=True)
    # 情绪暗示: warm / cool / neutral / vibrant / muted
    emotion_hint = Column(String(20), nullable=True)
    # Existing rows default to v1; imports after this release explicitly store v2.
    analysis_version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    analysis_attempted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    photo = relationship("Photo", back_populates="color_info")
