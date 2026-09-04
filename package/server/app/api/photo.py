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
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import func

import app.crud.photo
from app.core.config_manager import config_manager
from app.crud.photo import save_and_create_photo
from app.dependencies import get_db, BaseResponse
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
from app.db.models.photo import Photo, FileType
from app.service import storage
from app.service.task_manager import TaskManager
from app.db.models.task import TaskType


from app.schemas.photo import BatchDownloadRequest

router = APIRouter()

import tempfile
import zipfile
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

@router.post("/batch-download", summary="批量下载照片")
def batch_download_photos(
    req: BatchDownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not req.photo_ids:
        raise HTTPException(status_code=400, detail="Must provide photo_ids")
        
    photos = app.crud.photo.get_photos_by_ids(db, [str(uid) for uid in req.photo_ids], user_id=current_user.id)
    if not photos:
        raise HTTPException(status_code=404, detail="No photos found")
        
    fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Dedup by case-folded name so that "Photo.jpg" and "photo.JPG"
            # don't silently overwrite each other when extracted on a
            # case-insensitive filesystem (Windows / macOS default).
            name_counts = {}
            for photo in photos:
                if photo.file_path and os.path.exists(photo.file_path):
                    filename = photo.filename or os.path.basename(photo.file_path)
                    base, ext = os.path.splitext(filename)
                    key = filename.lower()
                    if key in name_counts:
                        name_counts[key] += 1
                        name = f"{base}_{name_counts[key]}{ext}"
                    else:
                        name_counts[key] = 0
                        name = filename
                    zf.write(photo.file_path, name)
                    
        return FileResponse(
            path=temp_path,
            filename="trailsnap_export.zip",
            media_type="application/zip",
            background=BackgroundTask(os.remove, temp_path)
        )
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to create zip: {str(e)}")

# Photo Endpoints

@router.get("/recycle-bin", response_model=BaseResponse[List[schemas.RecyclePhoto]])
def get_recycle_bin(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return BaseResponse.success(data=app.crud.photo.get_recycle_bin_photos(db, user_id=current_user.id, skip=skip, limit=limit))

@router.post("/recycle-bin/restore", response_model=BaseResponse[dict])
def restore_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.restore_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return BaseResponse.success(data={"message": f"Successfully restored {count} photos"})

@router.post("/recycle-bin/restore-all", response_model=BaseResponse[dict], summary="恢复回收站全部照片")
def restore_all_recycle_bin_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Restore every photo in the caller's bin without the client listing ids.

    Same motivation as the purge endpoint: "select all" must not require paging
    the entire bin into the browser first. Restores are chunked so the write
    transaction never grows unbounded.
    """
    photo_ids = app.crud.photo.get_recycle_bin_photo_ids(db, user_id=current_user.id)
    if not photo_ids:
        return BaseResponse.success(data={"restored": 0, "message": "Recycle bin is already empty"})

    chunk_size = app.crud.photo.DELETE_CHUNK_SIZE
    count = 0
    for offset in range(0, len(photo_ids), chunk_size):
        count += app.crud.photo.restore_photos(
            db, photo_ids[offset:offset + chunk_size], user_id=current_user.id
        )
    return BaseResponse.success(data={
        "restored": count,
        "message": f"Successfully restored {count} photos",
    })

@router.get("/recycle-bin/stats", response_model=BaseResponse[schemas.RecycleBinStats], summary="回收站统计")
def get_recycle_bin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Total item count of the caller's recycle bin.

    The list endpoint is paginated, so without this the UI cannot tell how many
    photos are in the bin and "select all" can only ever mean "select the pages
    already loaded".
    """
    from app.core.system_config import system_config

    return BaseResponse.success(data={
        "total": app.crud.photo.count_recycle_bin_photos(db, user_id=current_user.id),
        "retention_days": system_config.config.recycle_bin.retention_days,
    })

@router.delete("/recycle-bin/permanent", response_model=BaseResponse[dict])
def permanently_delete_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.batch_delete_photos_db(db, batch_data.photo_ids, is_delete_file=True, user_id=current_user.id)
    return BaseResponse.success(data={"message": f"Successfully permanently deleted {count} photos"})

@router.post("/recycle-bin/purge", response_model=BaseResponse[dict], summary="清空/批量永久删除回收站（大批量转异步）")
def purge_recycle_bin(
    payload: schemas.RecycleBinPurge,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permanently delete recycle-bin photos, switching to a background job when big.

    Two problems with driving this through ``/recycle-bin/permanent``:

    1. The client had to enumerate every id, so "empty the bin" was impossible
       without scrolling the whole list into memory first. Passing
       ``photo_ids = null`` here means "everything in my bin" and the server
       resolves the ids itself.
    2. A multi-thousand photo purge runs far longer than a request should. Above
       ``ASYNC_PURGE_THRESHOLD`` the work moves to a background thread and the
       response carries a ``job_id`` to poll, so the UI can show progress instead
       of hanging on a request that may well time out.

    Small batches stay synchronous — the round trip is cheaper than polling.
    """
    from app.service import recycle_bin_purge

    if payload.photo_ids is None:
        photo_ids = app.crud.photo.get_recycle_bin_photo_ids(db, user_id=current_user.id)
    else:
        photo_ids = list(payload.photo_ids)
        if not photo_ids:
            raise HTTPException(status_code=400, detail="No photo IDs provided")

    if not photo_ids:
        return BaseResponse.success(data={
            "mode": "sync",
            "total": 0,
            "deleted": 0,
            "message": "Recycle bin is already empty",
        })

    if len(photo_ids) <= recycle_bin_purge.ASYNC_PURGE_THRESHOLD:
        count = app.crud.photo.batch_delete_photos_db(
            db, photo_ids, is_delete_file=True, user_id=current_user.id
        )
        return BaseResponse.success(data={
            "mode": "sync",
            "total": len(photo_ids),
            "deleted": count,
            "message": f"Successfully permanently deleted {count} photos",
        })

    # Refuse to fan out a second worker over the same rows.
    existing = recycle_bin_purge.active_job_for_user(current_user.id)
    if existing is not None:
        return BaseResponse.success(data={"mode": "async", **existing.to_dict()})

    try:
        job = recycle_bin_purge.start_purge_job(current_user.id, photo_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    return BaseResponse.success(data={"mode": "async", **job.to_dict()})

@router.get("/recycle-bin/purge/{job_id}", response_model=BaseResponse[dict], summary="查询回收站清理进度")
def get_recycle_bin_purge_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    from app.service import recycle_bin_purge

    job = recycle_bin_purge.get_job(job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Purge job not found")
    return BaseResponse.success(data=job.to_dict())

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
        uploaded_after: Optional[datetime] = None,
        uploaded_before: Optional[datetime] = None,
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
        order_dir: Optional[str] = None,
        folder: Optional[str] = None,
        folder_direct: bool = False,
        dedup_similar: bool = False,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    st_time = time.time()
    # 根层直属（folder 为空且要求 direct）时需要 roots 来定位「扫描根正下方」的照片
    folder_roots = None
    if folder_direct and not (folder and folder.strip()):
        from app.utils.path import get_user_roots
        folder_roots = get_user_roots(current_user.id, db)
    photos = app.crud.photo.get_all_photos(
        db, skip=skip, limit=limit, start_time=start_time, end_time=end_time,
        uploaded_after=uploaded_after, uploaded_before=uploaded_before,
        years=years, city=city, cities=cities, scene=scene, scenes=scenes, province=province, provinces=provinces, country=country, countries=countries, 
        make=make, makes=makes, model=model, models=models, 
        image_type=image_type, image_types=image_types, 
        file_type=file_type, file_types=file_types,
        tag=tag, album_id=album_id, album_ids=album_ids,
        face_id=face_id, face_ids=face_ids, tag_id=tag_id, tag_ids=tag_ids,
        lat_min=lat_min, lat_max=lat_max, lng_min=lng_min, lng_max=lng_max,
        radius=radius, center_lat=center_lat, center_lng=center_lng,
        order_by=order_by, order_dir=order_dir, folder=folder, folder_direct=folder_direct, folder_roots=folder_roots,
        ids=ids, user_id=current_user.id
    )
    logging.info(f"read_all_photos time: {time.time() - st_time}")
    if dedup_similar and photos:
        # 按策略拉取后，按 CLIP embedding 相似度去重近重复/burst 照片。
        # 局部 import 避免模块加载时拉起 sklearn（对齐 _cluster_segment）。
        # skip/limit 作用于去重前，返回数可能小于 limit（拼图恒 skip=0，无影响）。
        from app.service.moment.day_highlight_service import dedup_photo_ids
        kept_set = set(dedup_photo_ids(db, current_user.id, [p.id for p in photos]))
        photos = [p for p in photos if p.id in kept_set]
    return photos

@router.get("/folders", response_model=BaseResponse[Dict[str, Any]])
def read_photo_folders(
    parent: Optional[str] = Query("", description="相对父目录路径，空字符串表示根层；用于层级树逐层浏览"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """按文件夹层级返回某个父目录下的下一层内容（优化版）。

    采用 os.listdir 快速读取真实硬盘结构，同时利用 SQL 聚合查询获取每个目录的照片数量，
    极大提升大批量照片库下的目录树展开速度。
    """
    import os
    from sqlalchemy import func, or_
    from app.utils.path import get_user_roots, _normalize

    parent_path = (parent or "").replace("\\", "/").strip("/")
    roots = get_user_roots(current_user.id, db)

    def get_root_label(r):
        return os.path.basename(r) or r

    def _esc(s):
        return s.replace('%', '\\%').replace('_', '\\_')

    def _stored_prefix_candidates(abs_dir):
        """针对某个绝对目录，给出它在 DB file_path 里可能出现的所有前缀形式。

        DB 里的 file_path 形态不统一：外部扫描目录通常存绝对路径，而历史上传
        记录可能存相对路径。func.replace(file_path,'\\','/')
        只统一分隔符、无法把相对路径转绝对，因此这里对每个根同时生成「绝对」与
        「相对」两种前缀，用 OR 匹配，保证两种形态都能命中。
        """
        abs_dir = (abs_dir or "").replace("\\", "/").rstrip("/")
        if not abs_dir:
            return []
        cands = {abs_dir}
        try:
            rel = os.path.relpath(abs_dir).replace("\\", "/").rstrip("/")
            if rel and rel != abs_dir:
                cands.add(rel)
                cands.add("./" + rel)
        except ValueError:
            # Windows 下跨盘符 os.path.relpath 会抛错，绝对形态已足够覆盖
            pass
        return [c + "/" for c in cands]

    def _under(expr, abs_dir):
        """file_path 位于 abs_dir 子树下（含更深层级）。"""
        cands = _stored_prefix_candidates(abs_dir)
        if not cands:
            return False
        likes = [expr.like(_esc(c) + "%", escape='\\') for c in cands]
        return or_(*likes) if len(likes) > 1 else likes[0]

    children = []
    own_count = 0
    breadcrumb = []

    norm_expr = func.replace(Photo.file_path, '\\', '/')

    if not parent_path:
        for r in roots:
            name = get_root_label(r)
            norm_r = _normalize(r)

            # 计算该根目录下所有照片的总数
            count = db.query(func.count(Photo.id)).filter(
                Photo.owner_id == current_user.id,
                Photo.is_deleted == False,
                _under(norm_expr, norm_r)
            ).scalar()
            
            has_children = False
            if os.path.exists(norm_r) and os.path.isdir(norm_r):
                try:
                    for item in os.listdir(norm_r):
                        if os.path.isdir(os.path.join(norm_r, item)):
                            has_children = True
                            break
                except Exception:
                    pass
                    
            children.append({
                "name": name,
                "path": name,
                "count": count,
                "has_children": has_children
            })
            
    else:
        parts = parent_path.split("/")
        root_label = parts[0]
        remainder = "/".join(parts[1:])
        
        matched_root = None
        for r in roots:
            if get_root_label(r) == root_label:
                matched_root = r
                break
                
        if matched_root:
            norm_r = _normalize(matched_root)
            abs_dir = _normalize(os.path.join(norm_r, remainder)) if remainder else norm_r

            if os.path.exists(abs_dir) and os.path.isdir(abs_dir):
                # 一次性取出 abs_dir 子树下所有照片的 file_path，在 Python 里按
                # 「直属 / 各一级子目录」分桶统计，避免每个子目录各跑一次 count 查询。
                abs_dir_norm = _normalize(abs_dir)
                subtree_rows = db.query(Photo.file_path).filter(
                    Photo.owner_id == current_user.id,
                    Photo.is_deleted == False,
                    _under(norm_expr, abs_dir)
                ).all()

                own_count = 0
                child_counts = {}  # 一级子目录名 -> 该子树照片总数
                for fp, in subtree_rows:
                    if not fp:
                        continue
                    norm_fp = _normalize(fp)
                    if norm_fp == abs_dir_norm:
                        own_count += 1
                        continue
                    if not norm_fp.startswith(abs_dir_norm + "/"):
                        continue
                    remainder = norm_fp[len(abs_dir_norm) + 1:]
                    first_sep = remainder.find("/")
                    if first_sep == -1:
                        own_count += 1
                    else:
                        child_name = remainder[:first_sep]
                        child_counts[child_name] = child_counts.get(child_name, 0) + 1

                try:
                    for item in os.listdir(abs_dir):
                        item_path = os.path.join(abs_dir, item)
                        if os.path.isdir(item_path):
                            has_children = False
                            try:
                                for sub_item in os.listdir(item_path):
                                    if os.path.isdir(os.path.join(item_path, sub_item)):
                                        has_children = True
                                        break
                            except Exception:
                                pass

                            children.append({
                                "name": item,
                                "path": parent_path + "/" + item,
                                "count": child_counts.get(item, 0),
                                "has_children": has_children
                            })
                except Exception:
                    pass
                    
        acc = []
        for seg in parts:
            acc.append(seg)
            breadcrumb.append({"name": seg, "path": "/".join(acc)})
            
    children.sort(key=lambda x: x["name"].lower())
    
    return BaseResponse.success(data={
        "parent": parent_path,
        "breadcrumb": breadcrumb,
        "own_count": own_count,
        "children": children
    })

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

@router.post("/batch/create", response_model=BaseResponse[dict])
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
        inserted_ids = app.crud.photo.batch_create_photos(db, photos_data, user_id=current_user.id)
        return BaseResponse.success(data={"message": f"Successfully created {len(inserted_ids)} photos"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=BaseResponse[dict])
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
        return BaseResponse.success(data={"message": f"Successfully updated {count} photos"})

    elif batch_data.action == 'delete':
        app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
        return BaseResponse.success(data={"message": "Photos moved to recycle bin successfully"})

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.delete("/batch", response_model=BaseResponse[dict])
def batch_delete_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return BaseResponse.success(data={"message": f"Successfully moved {count} photos to recycle bin"})

@router.post("/batch/update", response_model=BaseResponse[dict], summary="批量更新照片元数据")
def batch_update_photos_data(
    data: schemas.BatchPhotoDataUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    success_count = 0
    for photo_id in data.photo_ids:
        update_data = schemas.PhotoUpdate()
        if data.photo_time is not None:
            update_data.photo_time = data.photo_time
        
        updated = app.crud.photo.update_photo(db, photo_id, update_data, user_id=current_user.id)
        if updated:
            if data.description is not None:
                desc = db.query(ImageDescriptionModel).filter(ImageDescriptionModel.photo_id == photo_id).first()
                if desc:
                    desc.description = data.description
                else:
                    desc = ImageDescriptionModel(photo_id=photo_id, description=data.description)
                    db.add(desc)
                db.commit()
            success_count += 1
            
    return BaseResponse.success(data={"message": f"Successfully updated {success_count} photos"})


@router.post("/batch/tags", response_model=BaseResponse[dict], summary="批量更新照片标签")
def batch_update_photos_tags(
    data: schemas.BatchPhotoTagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    success_count = 0
    for photo_id in data.photo_ids:
        photo = app.crud.photo.get_photo(db, photo_id)
        if not photo or photo.owner_id != current_user.id:
            continue
            
        for tag_name in data.tags:
            if data.action == 'add':
                crud_tag.add_tag_to_photo(db, photo_id, tag_name, 1.0, owner_id=current_user.id)
            elif data.action == 'remove':
                # find tag_id by name
                tag_record = crud_tag.get_tag_by_name(db, tag_name)
                if tag_record:
                    crud_tag.remove_tag_from_photo(db, photo_id, tag_record.id)
        success_count += 1
        
    return BaseResponse.success(data={"message": f"Successfully updated tags for {success_count} photos"})


@router.post("/batch/transfer", response_model=BaseResponse[dict])
def batch_transfer_photos(
    data: schemas.BatchPhotoTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    config = config_manager.get_user_config(current_user.id, db)
    primary = os.path.join(storage._get_storage_root(current_user.id, db), "uploads")
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
    return BaseResponse.success(data={"message": f"Successfully {data.action}ed {success_count} photos"})


@router.delete("/{photo_id}", response_model=BaseResponse[schemas.Photo])
def delete_photo_global(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    app.crud.photo.batch_soft_delete_photos(db, [photo_id], user_id=current_user.id)
    # Fetch it again to return, or just return an empty response. Wait, return the deleted photo object.
    db_photo = app.crud.photo.get_photo(db, photo_id, include_deleted=True)
    return BaseResponse.success(data=db_photo)


@router.put("/{photo_id}", response_model=BaseResponse[schemas.Photo])
def update_photo(photo_id: UUID, photo: schemas.PhotoUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        db_photo = app.crud.photo.update_photo(db, photo_id, photo, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not db_photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return BaseResponse.success(data=db_photo)


@router.put("/{photo_id}/file", response_model=BaseResponse[schemas.Photo])
async def replace_photo_file(
    photo_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_photo = app.crud.photo.get_photo(db, photo_id)
    if not db_photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if db_photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    if db_photo.file_type == FileType.video:
        raise HTTPException(status_code=400, detail="Cannot replace video file via image editor")

    try:
        new_file_path = await run_in_threadpool(
            storage.save_upload_file, file, db_photo.id, current_user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated = await run_in_threadpool(
        app.crud.photo.replace_photo_file, db, db_photo, new_file_path, current_user.id
    )
    return BaseResponse.success(data=updated)

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


@router.delete("/{photo_id}/tags/{tag_id}", response_model=BaseResponse[dict])
def delete_photo_tag(photo_id: UUID, tag_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo = app.crud.photo.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    crud_tag.remove_tag_from_photo(db, photo_id, tag_id)
    return BaseResponse.success(data={"message": "Tag deleted successfully"})

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


@router.get("/random", response_model=BaseResponse[List[PhotoDetail]], summary="获取随机照片")
def get_random_photos(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取未删除的随机图片
    """
    photos = app.crud.photo.get_random_photos(db, user_id=current_user.id, limit=limit)
    return BaseResponse(code=0, msg="success", data=photos)


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

    演示模式（DEMO_MODE）下，若按「同月同日」过滤后照片不足，则用随机照片补足，
    保证页面始终有内容展示（不一定按时间匹配）。
    """
    if month is None or day is None or year is None:
        now = datetime.now()
        month = month or now.month
        day = day or now.day
        year = year or now.year

    photos = app.crud.photo.get_on_this_day_photos(db, user_id=current_user.id, month=month, day=day, year=year, limit=limit)

    # 演示模式：时间匹配不足时，用随机照片补足到 limit，确保「那年今日」不为空
    from app.middleware.demo_mode import DEMO_MODE
    if DEMO_MODE and len(photos) < limit:
        existing_ids = {p.id for p in photos}
        need = limit - len(photos)
        random_photos = app.crud.photo.get_random_photos(db, user_id=current_user.id, limit=need + 10)
        for p in random_photos:
            if len(photos) >= limit:
                break
            if p.id not in existing_ids:
                photos.append(p)
                existing_ids.add(p.id)

    return photos
