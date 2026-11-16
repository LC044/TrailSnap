from sqlalchemy import Column, DateTime, ForeignKey, String
from app.db.types import UUID, Vector
from app.db.base import Base
from datetime import datetime
import uuid

class ImageVector(Base):
    __tablename__ = "image_vectors"

    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Vector(512)) # CLIP ViT-B/32 has 512 dimensions
    created_at = Column(DateTime, default=datetime.now)
    model_name = Column(String, default="clip-ViT-B-32")
    content_revision = Column(String(32), nullable=False, server_default="legacy",
        default=lambda: uuid.uuid4().hex, onupdate=lambda: uuid.uuid4().hex)
