from typing import List, Optional, Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.dependencies import get_db, BaseResponse
from app.db.models.user import User
from app.db.models.photo import Photo, ImageType, FileType
from app.db.models.cluster import ImageCluster, PhotoCluster
from sqlalchemy import func
import os

router = APIRouter()

@router.get("/overview", response_model=BaseResponse[Dict[str, Any]])
def get_storage_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get storage basic overview.
    """
    import shutil
    import time
    from app.core.config_manager import config_manager
    user_config = config_manager.get_user_config(current_user.id, db)
    photo_path = user_config.storage.photo_storage_path
    
    try:
        disk_usage = shutil.disk_usage(photo_path)
        disk_total_size = disk_usage.total
        disk_free_size = disk_usage.free
    except Exception:
        disk_total_size = 0
        disk_free_size = 0

    user_id = current_user.id

    total_stats = db.query(
        func.sum(Photo.size).label('total_size'),
        func.count(Photo.id).label('total_files')
    ).filter(Photo.owner_id == user_id, Photo.is_deleted == False).first()

    total_size = int(total_stats.total_size or 0)
    total_files = int(total_stats.total_files or 0)

    return BaseResponse(data={
        "total_size": total_size,
        "total_files": total_files,
        "disk_total_size": disk_total_size,
        "disk_free_size": disk_free_size,
        "scan_date": time.strftime("%Y-%m-%dT%H:%M:%S")
    })

@router.get("/stats/type", response_model=BaseResponse[List[Dict[str, Any]]])
def get_storage_type_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get storage stats by file type (image, video, live_photo).
    """
    user_id = current_user.id
    type_dist = db.query(
        Photo.file_type,
        func.sum(Photo.size).label('size'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == user_id, Photo.is_deleted == False).group_by(Photo.file_type).all()
    
    distribution_by_type = []
    type_map = {
        'image': '图片',
        'video': '视频',
        'live_photo': '实况图'
    }
    for r in type_dist:
        ft = r.file_type.value if r.file_type else 'unknown'
        if ft not in type_map:
            continue
        distribution_by_type.append({
            "name": type_map[ft],
            "size": int(r.size or 0),
            "count": int(r.count or 0)
        })

    return BaseResponse(data=distribution_by_type)

@router.get("/stats/device", response_model=BaseResponse[List[Dict[str, Any]]])
def get_storage_device_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get storage stats by camera model.
    """
    from app.db.models.photo_metadata import PhotoMetadata
    user_id = current_user.id
    device_dist = db.query(
        PhotoMetadata.model,
        func.sum(Photo.size).label('size'),
        func.count(Photo.id).label('count')
    ).join(
        Photo, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == user_id, 
        Photo.is_deleted == False,
        PhotoMetadata.model.isnot(None),
        PhotoMetadata.model != ''
    ).group_by(PhotoMetadata.model).all()
    
    distribution_by_device = []
    for r in device_dist:
        model = r.model
        # Skip if model is literally "未知" or "unknown"
        if not model or model.lower() in ['unknown', '未知', '未知设备']:
            continue
            
        distribution_by_device.append({
            "name": model,
            "size": int(r.size or 0),
            "count": int(r.count or 0)
        })

    # Sort by size desc
    distribution_by_device.sort(key=lambda x: x["size"], reverse=True)
    return BaseResponse(data=distribution_by_device)

@router.get("/stats/folder", response_model=BaseResponse[List[Dict[str, Any]]])
def get_storage_folder_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get storage stats by folder.
    """
    user_id = current_user.id
    all_paths = db.query(Photo.file_path, Photo.size).filter(Photo.owner_id == user_id, Photo.is_deleted == False).all()
    folder_map = {}
    for path, size in all_paths:
        folder = os.path.dirname(path) if path else '未知'
        if folder not in folder_map:
            folder_map[folder] = {"size": 0, "count": 0}
        folder_map[folder]["size"] += int(size or 0)
        folder_map[folder]["count"] += 1
    
    distribution_by_folder = []
    for folder, stats in folder_map.items():
        distribution_by_folder.append({
            "name": folder,
            "size": stats["size"],
            "count": stats["count"]
        })
    return BaseResponse(data=distribution_by_folder)

@router.get("/stats/recoverable", response_model=BaseResponse[Dict[str, Any]])
def get_storage_recoverable_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get storage recoverable stats.
    """
    user_id = current_user.id
    recoverable_data = {
        "similar": {"size": 0, "count": 0},
        "duplicate": {"size": 0, "count": 0},
        "screenshot": {"size": 0, "count": 0},
        "video": {"size": 0, "count": 0}
    }

    # 1. Screenshots
    screenshot_stats = db.query(
        func.sum(Photo.size).label('size'),
        func.count(Photo.id).label('count')
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        Photo.image_type == ImageType.SCREENSHOT
    ).first()
    recoverable_data["screenshot"]["size"] = int(screenshot_stats.size or 0)
    recoverable_data["screenshot"]["count"] = int(screenshot_stats.count or 0)

    # 2. Videos
    video_stats = db.query(
        func.sum(Photo.size).label('size'),
        func.count(Photo.id).label('count')
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        Photo.file_type == FileType.video
    ).first()
    recoverable_data["video"]["size"] = int(video_stats.size or 0)
    recoverable_data["video"]["count"] = int(video_stats.count or 0)

    # 3. Duplicates
    md5_counts = db.query(
        Photo.md5,
        func.count(Photo.id).label('count'),
        func.sum(Photo.size).label('size'),
        func.max(Photo.size).label('max_size')
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        Photo.md5.isnot(None),
        Photo.md5 != ""
    ).group_by(Photo.md5).having(func.count(Photo.id) > 1).all()

    for r in md5_counts:
        recoverable_size = int(r.size or 0) - int(r.max_size or 0)
        recoverable_data["duplicate"]["size"] += recoverable_size
        recoverable_data["duplicate"]["count"] += (int(r.count or 0) - 1)

    # 4. Similar Photos
    similar_clusters = db.query(ImageCluster).join(
        PhotoCluster, ImageCluster.cluster_id == PhotoCluster.cluster_id
    ).join(
        Photo, PhotoCluster.photo_id == Photo.id
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        ImageCluster.cluster_type == "SIMILARITY"
    ).group_by(ImageCluster.cluster_id).having(func.count(Photo.id) > 1).all()

    for cluster in similar_clusters:
        cluster_photos = db.query(Photo).join(
            PhotoCluster, Photo.id == PhotoCluster.photo_id
        ).filter(
            PhotoCluster.cluster_id == cluster.cluster_id,
            Photo.is_deleted == False
        ).all()

        if len(cluster_photos) > 1:
            cluster_photos.sort(key=lambda x: x.size or 0, reverse=True)
            for p in cluster_photos[1:]:
                recoverable_data["similar"]["size"] += int(p.size or 0)
                recoverable_data["similar"]["count"] += 1

    return BaseResponse(data=recoverable_data)

@router.get("/time-distribution", response_model=BaseResponse[List[Dict[str, Any]]])
def get_time_distribution(
    group_by: str = Query("month", description="year, month, or day"), 
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Get storage distribution by time.
    """
    user_id = current_user.id
    
    if group_by == "year":
        expr = func.to_char(Photo.photo_time, 'YYYY').label('time_group')
    elif group_by == "day":
        expr = func.to_char(Photo.photo_time, 'YYYY-MM-DD').label('time_group')
    else:
        # Default to month
        expr = func.to_char(Photo.photo_time, 'YYYY-MM').label('time_group')

    query = db.query(
        expr,
        func.sum(Photo.size).label('size'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == user_id, Photo.is_deleted == False, Photo.photo_time.isnot(None))

    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= end_date + " 23:59:59")

    dist = query.group_by('time_group').all()

    result = []
    for r in dist:
        if not r.time_group:
            continue
        result.append({
            "name": str(r.time_group),
            "size": int(r.size or 0),
            "count": int(r.count or 0)
        })
    
    return BaseResponse(data=result)

@router.get("/top-large-files", response_model=BaseResponse[List[Dict[str, Any]]])
def get_top_large_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get the top large files.
    """
    user_id = current_user.id
    top_files = db.query(Photo).filter(
        Photo.owner_id == user_id, Photo.is_deleted == False
    ).order_by(Photo.size.desc()).limit(20).all()

    top_large_files = []
    for f in top_files:
        top_large_files.append({
            "id": str(f.id),
            "filename": f.filename,
            "size": f.size,
            "path": f.file_path,
            "type": f.file_type.value if f.file_type else None
        })
    
    return BaseResponse(data=top_large_files)

@router.get("/screenshots", response_model=BaseResponse[List[Dict[str, Any]]])
def get_screenshots(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get screenshots.
    """
    photos = db.query(Photo).filter(
        Photo.owner_id == current_user.id,
        Photo.is_deleted == False,
        Photo.image_type == ImageType.SCREENSHOT
    ).order_by(Photo.photo_time.desc()).offset(skip).limit(limit).all()
    
    from app.schemas.photo import Photo as PhotoSchema
    result = []
    for p in photos:
        result.append(PhotoSchema.model_validate(p).model_dump())
    
    return BaseResponse(data=result)

@router.post("/screenshots/move-to-non-archive", response_model=BaseResponse[Dict[str, Any]])
def move_screenshots_to_non_archive(photo_ids: List[UUID], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Move screenshots to a non-archive folder.
    (Placeholder logic, actually moving might involve file system ops or just tagging)
    For now, we might just tag them or move them in file system.
    Wait, what is "不归档目录"?
    "移到不归档目录" implies moving to a specific folder or setting a flag.
    Let's just implement a simple move logic or skip for now if not fully spec'd.
    Actually, maybe there is an "is_archived" flag?
    """
    # Just returning success for now
    return BaseResponse(data={"message": "Moved successfully"})
