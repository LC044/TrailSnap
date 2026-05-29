#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/7 23:20
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-photo.py
@Description : 
"""
import logging
import time
import os
import shutil
import uuid
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

import app.crud.photo
from app.core.config_manager import config_manager
from app.crud.photo import save_and_create_photo
from app.dependencies import get_db
from app.crud import album as crud_album
from app.crud import face as crud_face
from app.crud import tag as crud_tag

from app.schemas import photo as schemas
from app.schemas.metadata import PhotoMetadata, PhotoMetadataUpdate, PhotoDetail
from app.schemas import tag as tag_schemas

from app.api.deps import get_current_user
from app.db.models.user import User

from app.db.models.image_description import ImageDescription as ImageDescriptionModel
from app.schemas.image_description import ImageDescription as ImageDescriptionSchema
from app.db.models.photo import Photo
from app.service.task_manager import TaskManager
from app.db.models.task import TaskType


router = APIRouter()

# Photo Endpoints

@router.get("/recycle-bin", response_model=List[schemas.RecyclePhoto])
def get_recycle_bin(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return app.crud.photo.get_recycle_bin_photos(db, user_id=current_user.id, skip=skip, limit=limit)

@router.post("/recycle-bin/restore")
def restore_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.restore_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return {"message": f"Successfully restored {count} photos"}

@router.delete("/recycle-bin/permanent")
def permanently_delete_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.batch_delete_photos_db(db, batch_data.photo_ids, is_delete_file=True, user_id=current_user.id)
    return {"message": f"Successfully permanently deleted {count} photos"}

@router.get("", response_model=List[schemas.Photo])
def read_all_photos(
        skip: int = 0,
        limit: int = 100,
        album_id: Optional[UUID] = None,
        album_ids: Optional[List[UUID]] = Query(None),
        face_id: Optional[UUID] = None,
        face_ids: Optional[List[UUID]] = Query(None),
        tag_id: Optional[UUID] = None,
        tag_ids: Optional[List[UUID]] = Query(None),
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        years: Optional[List[int]] = Query(None),
        city: Optional[str] = None,
        cities: Optional[List[str]] = Query(None),
        scene: Optional[str] = None,
        scenes: Optional[List[str]] = Query(None),
        province: Optional[str] = None,
        provinces: Optional[List[str]] = Query(None),
        country: Optional[str] = None,
        countries: Optional[List[str]] = Query(None),
        make: Optional[str] = None,
        makes: Optional[List[str]] = Query(None),
        model: Optional[str] = None,
        models: Optional[List[str]] = Query(None),
        image_type: Optional[str] = None,
        image_types: Optional[List[str]] = Query(None),
        file_type: Optional[str] = None,
        file_types: Optional[List[str]] = Query(None),
        tag: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lng_min: Optional[float] = None,
        lng_max: Optional[float] = None,
        radius: Optional[float] = None,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        ids: Optional[List[UUID]] = Query(None),
        order_by: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    st_time = time.time()
    photos = app.crud.photo.get_all_photos(
        db, skip=skip, limit=limit, start_time=start_time, end_time=end_time,
        years=years, city=city, cities=cities, scene=scene, scenes=scenes, province=province, provinces=provinces, country=country, countries=countries, 
        make=make, makes=makes, model=model, models=models, 
        image_type=image_type, image_types=image_types, 
        file_type=file_type, file_types=file_types,
        tag=tag, album_id=album_id, album_ids=album_ids,
        face_id=face_id, face_ids=face_ids, tag_id=tag_id, tag_ids=tag_ids,
        lat_min=lat_min, lat_max=lat_max, lng_min=lng_min, lng_max=lng_max,
        radius=radius, center_lat=center_lat, center_lng=center_lng,
        order_by=order_by,
        ids=ids, user_id=current_user.id
    )
    logging.info(f"read_all_photos time: {time.time() - st_time}")
    return photos

@router.get("/detail", response_model=List[PhotoDetail])
def read_all_photos_with_detail(
        skip: int = 0,
        limit: int = 100,
        album_id: Optional[UUID] = None,
        album_ids: Optional[List[UUID]] = Query(None),
        face_id: Optional[UUID] = None,
        face_ids: Optional[List[UUID]] = Query(None),
        tag_id: Optional[UUID] = None,
        tag_ids: Optional[List[UUID]] = Query(None),
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        years: Optional[List[int]] = Query(None),
        city: Optional[str] = None,
        cities: Optional[List[str]] = Query(None),
        scene: Optional[str] = None,
        scenes: Optional[List[str]] = Query(None),
        province: Optional[str] = None,
        provinces: Optional[List[str]] = Query(None),
        country: Optional[str] = None,
        countries: Optional[List[str]] = Query(None),
        make: Optional[str] = None,
        makes: Optional[List[str]] = Query(None),
        model: Optional[str] = None,
        models: Optional[List[str]] = Query(None),
        image_type: Optional[str] = None,
        image_types: Optional[List[str]] = Query(None),
        file_type: Optional[str] = None,
        file_types: Optional[List[str]] = Query(None),
        tag: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lng_min: Optional[float] = None,
        lng_max: Optional[float] = None,
        radius: Optional[float] = None,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        ids: Optional[List[UUID]] = Query(None),
        order_by: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    st_time = time.time()
    photos = app.crud.photo.get_all_photos(
        db, skip=skip, limit=limit, start_time=start_time, end_time=end_time,
        years=years, city=city, cities=cities, scene=scene, scenes=scenes, province=province, provinces=provinces, country=country, countries=countries,
        make=make, makes=makes, model=model, models=models,
        image_type=image_type, image_types=image_types,
        file_type=file_type, file_types=file_types,
        tag=tag, album_id=album_id, album_ids=album_ids,
        face_id=face_id, face_ids=face_ids, tag_id=tag_id, tag_ids=tag_ids,
        lat_min=lat_min, lat_max=lat_max, lng_min=lng_min, lng_max=lng_max,
        radius=radius, center_lat=center_lat, center_lng=center_lng,
        order_by=order_by,
        ids=ids, user_id=current_user.id
    )
    logging.info(f"read_all_photos time: {time.time() - st_time}")
    return photos

@router.post("/batch/create")
def batch_create_photos(
    batch_data: schemas.BatchPhotoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Convert schema to dict list expected by crud
    photos_data = []
    for item in batch_data.items:
        photos_data.append({
            'photo': item.photo,
            'file_path': item.file_path,
            'photo_id': item.photo_id,
        })
    try:
        count = app.crud.photo.batch_create_photos(db, photos_data, user_id=current_user.id)
        return {"message": f"Successfully created {count} photos"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
def batch_update_photos(
        batch_data: schemas.BatchPhotoUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if batch_data.action in ['add_to_album', 'remove_from_album']:

        if not batch_data.album_id:
            raise HTTPException(status_code=400, detail="Album ID required for this action")

        if batch_data.action == 'add_to_album':
            # Verify album exists
            db_album = crud_album.get_album(db, album_id=batch_data.album_id, user_id=current_user.id)
            if not db_album:
                raise HTTPException(status_code=404, detail="Target album not found")

        count = crud_album.batch_update_album_association(db, batch_data.photo_ids, batch_data.album_id, batch_data.action, user_id=current_user.id)
        return {"message": f"Successfully updated {count} photos"}

    elif batch_data.action == 'delete':
        app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
        return {"message": "Photos moved to recycle bin successfully"}

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.delete("/batch")
def batch_delete_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return {"message": f"Successfully moved {count} photos to recycle bin"}

@router.post("/batch/transfer")
def batch_transfer_photos(
    data: schemas.BatchPhotoTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    config = config_manager.get_user_config(current_user.id, db)
    primary = config.storage.photo_storage_path or 'uploads'
    external = config.storage.external_directories or []
    allowed_roots = [os.path.abspath(primary)] + [os.path.abspath(p) for p in external]
    
    abs_target = os.path.abspath(data.target_path)
    is_allowed = any(abs_target == r or abs_target.startswith(r + os.sep) for r in allowed_roots)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Target directory not allowed")
        
    try:
        os.makedirs(abs_target, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create directory: {e}")
        
    photos = app.crud.photo.get_photos_by_ids(db, data.photo_ids, user_id=current_user.id)
    success_count = 0
    for photo in photos:
        old_path = photo.file_path
        if not old_path or not os.path.exists(old_path):
            continue
            
        filename = os.path.basename(old_path)
        new_path = os.path.join(abs_target, filename)
        
        # Handle collision
        if os.path.exists(new_path) and os.path.abspath(old_path) != os.path.abspath(new_path):
            base, ext = os.path.splitext(filename)
            new_path = os.path.join(abs_target, f"{base}_{uuid.uuid4().hex[:8]}{ext}")
            
        if data.action == 'move':
            if os.path.abspath(old_path) != os.path.abspath(new_path):
                try:
                    shutil.move(old_path, new_path)
                    photo.file_path = new_path
                    photo.filename = os.path.basename(new_path)
                    success_count += 1
                except Exception as e:
                    logging.error(f"Failed to move {old_path} to {new_path}: {e}")
        elif data.action == 'copy':
            if os.path.abspath(old_path) != os.path.abspath(new_path):
                try:
                    shutil.copy2(old_path, new_path)
                    
                    # Create new DB record
                    new_photo_data = {c.name: getattr(photo, c.name) for c in photo.__table__.columns if c.name not in ['id', 'file_path', 'filename', 'created_at', 'updated_at']}
                    new_photo = Photo(
                        id=uuid.uuid4(),
                        file_path=new_path,
                        filename=os.path.basename(new_path),
                        **new_photo_data
                    )
                    db.add(new_photo)
                    success_count += 1
                    
                    TaskManager.get_instance().add_task(db, TaskType.GENERATE_THUMBNAIL, {'photo_id': str(new_photo.id)})
                except Exception as e:
                    logging.error(f"Failed to copy {old_path} to {new_path}: {e}")
                    
    db.commit()
    return {"message": f"Successfully {data.action}ed {success_count} photos"}


@router.delete("/{photo_id}", response_model=schemas.Photo)
def delete_photo_global(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    app.crud.photo.batch_soft_delete_photos(db, [photo_id], user_id=current_user.id)
    # Fetch it again to return, or just return an empty response. Wait, return the deleted photo object.
    db_photo = app.crud.photo.get_photo(db, photo_id, include_deleted=True)
    return db_photo


@router.put("/{photo_id}", response_model=schemas.Photo)
def update_photo(photo_id: UUID, photo: schemas.PhotoUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_photo = app.crud.photo.update_photo(db, photo_id, photo, user_id=current_user.id)
    if not db_photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return db_photo

# Tag Endpoints

@router.get("/{photo_id}/tags", response_model=List[tag_schemas.PhotoTagResponse])
def get_photo_tags(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud_tag.get_photo_tags(db, photo_id, owner_id=current_user.id)


@router.post("/{photo_id}/tags", response_model=tag_schemas.PhotoTagResponse)
def add_photo_tag(photo_id: UUID, tag_data: tag_schemas.PhotoTagAdd, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo = app.crud.photo.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    return crud_tag.add_tag_to_photo(db, photo_id, tag_data.tag_name, tag_data.confidence, owner_id=current_user.id)


@router.delete("/{photo_id}/tags/{tag_id}")
def delete_photo_tag(photo_id: UUID, tag_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo = app.crud.photo.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    crud_tag.remove_tag_from_photo(db, photo_id, tag_id)
    return {"message": "Tag deleted successfully"}

@router.get("/{photo_id}/description", response_model=Optional[ImageDescriptionSchema], summary="获取图片描述")
def get_photo_description(
    photo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    desc = db.query(ImageDescriptionModel).filter(
        ImageDescriptionModel.photo_id == photo_id
    ).first()
    
    # Check ownership via photo
    if desc:
        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo or photo.owner_id != current_user.id:
             raise HTTPException(status_code=403, detail="Not authorized")
    
    return desc


@router.get("/on-this-day", response_model=List[PhotoDetail])
def get_on_this_day_photos(
    month: Optional[int] = None,
    day: Optional[int] = None,
    year: Optional[int] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取那年今日的照片
    """
    if month is None or day is None or year is None:
        now = datetime.now()
        month = month or now.month
        day = day or now.day
        year = year or now.year

    return app.crud.photo.get_on_this_day_photos(db, user_id=current_user.id, month=month, day=day, year=year, limit=limit)
