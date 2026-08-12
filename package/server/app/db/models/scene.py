from sqlalchemy import Column, String, Integer, Text, DECIMAL, JSON, DateTime, func, Boolean, ForeignKey
from app.db.types import UUID
from app.db.base import Base
import uuid

class Scene(Base):
    __tablename__ = "scenes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    level = Column(Integer)  # 1, 2, 3 etc.
    address = Column(Text)
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))
    radius = Column(Integer)  # meters
    polygon = Column(JSON)  # [[lat, lng], ...]
    is_custom = Column(Boolean, default=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
