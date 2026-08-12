from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from app.db.types import UUID
from sqlalchemy.sql import func
from app.db.base import Base

class ImageDescription(Base):
    __tablename__ = "image_descriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(Text, nullable=True) # 图片的描述
    memory_score = Column(Float, nullable=True) # 0-100，值得回忆的程度
    quality_score = Column(Float, nullable=True) # 0-100，图片的美观度
    tags = Column(JSON, nullable=True) # 图片的标签，例如["人物", "动物", "风景"]
    reason = Column(Text, nullable=True) # 评分原因
    narrative = Column(Text, nullable=True) # 一句话文案
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    photo = relationship("Photo", back_populates="image_description")
