#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2026/5/19 20:28
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-metadata.py
@Description : 
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.dependencies import get_db, BaseResponse
from app.crud import photo as crud_photo
from app.crud import album as crud_album
from app.crud import face as crud_face
from app.crud import tag as crud_tag
from app.schemas import ocr as schemas
from app.db.models.photo import Photo
from app.schemas.metadata import PhotoMetadataUpdate, PhotoMetadata, BatchLocationUpdate

router = APIRouter()

# Metadata Endpoints

@router.get("", response_model=PhotoMetadata)
def get_photo_metadata(
        photo_id: UUID = Query(..., description="The ID of the photo"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    db_metadata = crud_photo.get_photo_metadata(db, photo_id=photo_id, user_id=current_user.id)

    if not db_metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    photo = crud_photo.get_photo(db, photo_id=photo_id, include_deleted=True)
    albums = crud_album.get_albums_by_photo_id(db, photo_id=photo_id)
    faces_identities = crud_face.get_identities_by_photo_id(db, photo_id=photo_id)
    tags = crud_tag.get_photo_tags(db, photo_id=photo_id, owner_id=current_user.id)

    photo_metadata = PhotoMetadata.model_validate(db_metadata)
    photo_metadata.file_path = photo.file_path
    photo_metadata.albums = albums
    photo_metadata.faces_identities = faces_identities
    photo_metadata.tags = tags

    return photo_metadata


@router.put("", response_model=PhotoMetadata)
def update_photo_metadata(
        photo_id: UUID,
        metadata: PhotoMetadataUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    result = crud_photo.update_photo_metadata(db, photo_id=photo_id, metadata=metadata, user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Photo not found or access denied")
    return result


@router.post("/batch-location")
def batch_update_location(
        batch_data: BatchLocationUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")

    updated_count = 0
    for photo_id in batch_data.photo_ids:
        update_data: dict = {
            "latitude": batch_data.latitude,
            "longitude": batch_data.longitude,
        }
        if batch_data.formatted_address:
            update_data["address"] = batch_data.formatted_address
        if batch_data.province:
            update_data["province"] = batch_data.province
        if batch_data.city:
            update_data["city"] = batch_data.city
        if batch_data.district:
            update_data["district"] = batch_data.district
        if batch_data.country:
            update_data["country"] = batch_data.country

        metadata_update = PhotoMetadataUpdate(**update_data)
        result = crud_photo.update_photo_metadata(
            db, photo_id=photo_id, metadata=metadata_update, user_id=current_user.id
        )
        if result:
            updated_count += 1

    return BaseResponse(data={"message": f"Successfully updated location for {updated_count} photos", "count": updated_count})

