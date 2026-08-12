#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import Column, String, ForeignKey, Text, JSON, DECIMAL, Index
from app.db.types import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class PhotoMetadata(Base):
    __tablename__ = "photo_metadata"

    __table_args__ = (
        Index('idx_location_lat_lng', 'latitude', 'longitude'),
        Index('idx_location_city', 'city'),
        Index('idx_location_province', 'province'),
        Index('idx_location_country', 'country'),
    )

    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    exif_info = Column(Text)    # EXIF info as text
    # Enhanced location fields
    longitude = Column(DECIMAL(10, 7))
    latitude = Column(DECIMAL(10, 7))
    city = Column(String(100), index=True)
    district = Column(String(100), index=True)
    province = Column(String(100), index=True)
    country = Column(String(100), index=True)
    address = Column(Text, index=True)

    # Camera info
    make = Column(String(100))
    model = Column(String(100))
    shooting_params = Column(JSON)

    location_api = Column(String(255)) # API info for location

    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    scene = relationship("Scene")

    photo = relationship("Photo", back_populates="metadata_info")
