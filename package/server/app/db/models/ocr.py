from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey, DateTime
from app.db.types import UUID
from sqlalchemy.sql import func
from app.db.base import Base

class OCR(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(String, index=True)
    text_score = Column(Float)
    polygon = Column(JSON)  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
