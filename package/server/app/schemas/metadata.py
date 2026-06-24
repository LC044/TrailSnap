#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/21 21:15
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-metadata.py
@Description : 
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, computed_field
from app.db.models.photo import FileType
from app.schemas.album import Album
from app.schemas.face import FaceIdentitySchema
from app.schemas.image_description import ImageDescription
from app.schemas.photo import Photo
from app.schemas.tag import PhotoTagResponse

# Metadata Schemas
class PhotoMetadataBase(BaseModel):
    exif_info: Optional[str] = None

    # Camera info
    make: Optional[str] = None
    model: Optional[str] = None
    shooting_params: Optional[Dict[str, Any]] = None

    # Enhanced location fields
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    city: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None


class PhotoMetadataCreate(PhotoMetadataBase):
    pass


class PhotoMetadataUpdate(PhotoMetadataBase):
    pass


class BatchLocationUpdate(BaseModel):
    photo_ids: List[UUID]
    latitude: float
    longitude: float
    formatted_address: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    country: Optional[str] = None

class PhotoMetadata(PhotoMetadataBase):
    photo_id: UUID
    file_path: Optional[str] = None
    albums: Optional[List[Album]] = None
    faces_identities: Optional[List[FaceIdentitySchema]] = None
    tags: Optional[List[PhotoTagResponse]] = None
    class Config:
        from_attributes = True

class PhotoDetail(Photo):
    metadata_info: Optional[PhotoMetadata] = None
    image_description: Optional[ImageDescription] = None