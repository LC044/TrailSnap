from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.db.types import UUID
from app.db.base import Base

class IndexLog(Base):
    __tablename__ = 'index_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(50), nullable=False)
    file_path = Column(Text, nullable=False)
    photo_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
