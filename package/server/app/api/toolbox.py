from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.api.deps import get_current_user
from app.db.models.user import User
from app.dependencies import get_db, BaseResponse
from app.db.models.photo import Photo
from app.db.models.task import TaskType, TaskStatus, Task
from app.service.task_manager import TaskManager
from app.crud import task as crud_task
from app.schemas.photo import Photo as PhotoSchema
from app.service.similar_photo import SimilarPhotoService
from app.db.models.task import Task, TaskType, TaskStatus
from app.schemas import photo as schemas
from app.crud import task as crud_task
from app.schemas.task import TaskResponse
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.image_description import ImageDescription as ImageDescriptionModel
from app.schemas.image_description import ImageDescription as ImageDescriptionSchema

class DuplicatePhotoGroup(BaseModel):
    md5: str
    photos: List[PhotoSchema]

class OrganizeRequest(BaseModel):
    target_root_path: str
    strategy: str # 'time', 'category', 'person', 'location'
    action: str # 'move' or 'copy'
    time_granularity: Optional[str] = 'ym' # 'ym' or 'ymd'
    time_format: Optional[str] = 'flat' # 'flat' or 'nested'
    location_granularity: Optional[str] = 'city' # 'province', 'city', 'district'
    location_format: Optional[str] = 'flat' # 'flat' or 'nested'
    time_range: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    people: Optional[List[str]] = None
    locations: Optional[List[str]] = None

class OrganizePreviewOptionsRequest(BaseModel):
    strategy: str
    location_granularity: Optional[str] = 'city'
    location_format: Optional[str] = 'flat'

class OrganizePreviewOptionsResponse(BaseModel):
    options: List[str]

class RenameRequest(BaseModel):
    target_root_path: str
    template: Optional[str] = 'IMG_{date}_{time}'

class TimeFromFilenameRequest(BaseModel):
    target_root_path: str
    only_missing_metadata: Optional[bool] = False
    make: Optional[str] = None
    model: Optional[str] = None
    time_mode: Optional[str] = 'auto'
    custom_time: Optional[str] = None

router = APIRouter()

@router.post("/duplicate-photos/scan", response_model=BaseResponse[TaskResponse])
def scan_duplicate_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    触发重复照片扫描任务。
    """
    # Check if there's already a pending or processing task
    existing_task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.FIND_DUPLICATE_PHOTOS, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )

    if existing_task:
        return BaseResponse(data=existing_task)

    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.FIND_DUPLICATE_PHOTOS,
        payload={},
        owner_id=current_user.id
    )
    return BaseResponse(data=task)

@router.get("/duplicate-photos", response_model=BaseResponse[List[DuplicatePhotoGroup]])
def get_duplicate_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取重复照片列表，返回按 MD5 分组（组内照片数 > 1）的照片列表。
    """
    # Find MD5s that have more than 1 photo
    md5_counts = db.query(
        Photo.md5,
        func.count(Photo.id).label('count')
    ).filter(
        Photo.owner_id == current_user.id,
        Photo.md5.isnot(None),
        Photo.md5 != ""
    ).group_by(
        Photo.md5
    ).having(
        func.count(Photo.id) > 1
    ).all()

    if not md5_counts:
        return BaseResponse(data=[])

    duplicate_md5s = [row.md5 for row in md5_counts]

    # Fetch all photos with these MD5s
    photos = db.query(Photo).filter(
        Photo.owner_id == current_user.id,
        Photo.md5.in_(duplicate_md5s)
    ).order_by(Photo.photo_time.desc()).all()

    # Group photos by MD5
    grouped_photos: Dict[str, List[PhotoSchema]] = {}
    for photo in photos:
        md5 = photo.md5
        if md5 not in grouped_photos:
            grouped_photos[md5] = []
        # Convert DB model to Schema dict/object. We can just use the Pydantic model dump
        # Fastapi will automatically serialize Pydantic models returned in a list/dict, 
        # but here we construct the dict structure manually.
        grouped_photos[md5].append(photo)

    # Convert to list of groups
    result = []
    for md5, photo_list in grouped_photos.items():
        result.append({
            "md5": md5,
            "photos": photo_list
        })

    return BaseResponse(data=result)


@router.post("/similar/tasks", response_model=BaseResponse[TaskResponse])
def create_similar_photo_task(
    threshold: float = 0.9,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new similar photo clustering task
    """
    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.SIMILAR_PHOTO_CLUSTERING,
        payload={"threshold": threshold},
        owner_id=current_user.id
    )
    return BaseResponse(data=task)

@router.get("/similar/tasks/latest", response_model=BaseResponse[Optional[TaskResponse]])
def get_latest_similar_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the latest similar photo clustering task
    """
    task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.SIMILAR_PHOTO_CLUSTERING, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )
    
    if task:
        return BaseResponse(data=task)

    # If no pending/processing task, check ImageCluster for the latest task_id
    latest_cluster = db.query(ImageCluster).join(
        PhotoCluster, ImageCluster.cluster_id == PhotoCluster.cluster_id
    ).join(
        Photo, PhotoCluster.photo_id == Photo.id
    ).filter(
        Photo.owner_id == current_user.id,
        ImageCluster.cluster_type == "SIMILARITY"
    ).order_by(ImageCluster.created_at.desc()).first()

    if latest_cluster and latest_cluster.task_id:
        try:
            task_id_uuid = UUID(latest_cluster.task_id)
        except ValueError:
            return BaseResponse(data=None)
            
        return BaseResponse(data=TaskResponse(
            id=task_id_uuid,
            type=TaskType.SIMILAR_PHOTO_CLUSTERING,
            status=TaskStatus.COMPLETED.value,
            created_at=latest_cluster.created_at,
            updated_at=latest_cluster.created_at,
            total_items=0,
            processed_items=0,
            result=None
        ))
        
    return BaseResponse(data=None)

@router.get("/similar/tasks/{task_id}", response_model=BaseResponse[TaskResponse])
def get_similar_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the status of a specific similar photo clustering task
    """
    task = crud_task.get_task_by_id_and_owner(db, task_id, current_user.id)
    
    if task:
        return BaseResponse(data=task)
        
    # If not in Task table, it was either completed or deleted.
    # We assume it's completed.
    return BaseResponse(data=TaskResponse(
        id=task_id,
        type=TaskType.SIMILAR_PHOTO_CLUSTERING,
        status=TaskStatus.COMPLETED.value,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        total_items=0,
        processed_items=0,
        result=None
    ))

@router.get("/similar/tasks/{task_id}/result", response_model=BaseResponse[List[List[schemas.Photo]]])
def get_similar_task_result(
    task_id: UUID,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the result of a similar photo clustering task
    """
    result = []
    current_skip = skip
    # Safety break to avoid infinite loops
    max_loops = 100 
    loop_count = 0
    
    while len(result) < limit and loop_count < max_loops:
        loop_count += 1
        
        # Calculate how many more we need
        remaining_needed = limit - len(result)
        # Fetch at least 20 or remaining_needed to be efficient
        fetch_limit = max(remaining_needed, 20)
        
        clusters = db.query(ImageCluster).filter(
            ImageCluster.task_id == str(task_id),
            ImageCluster.cluster_type == "SIMILARITY"
        ).order_by(ImageCluster.created_at.desc()).offset(current_skip).limit(fetch_limit).all()

        if not clusters:
            break

        processed_count = 0
        deleted_count = 0
        
        for cluster in clusters:
            # If we have enough results, we stop adding to result,
            # but we simply break and let the offset calculation handle the next page start.
            if len(result) >= limit:
                break
                
            processed_count += 1
            
            photo_clusters = db.query(PhotoCluster).filter(PhotoCluster.cluster_id == cluster.cluster_id).all()
            photo_ids = [pc.photo_id for pc in photo_clusters]

            should_delete = False
            cluster_photos = []
            
            if not photo_ids:
                should_delete = True
            else:
                photos_query = db.query(Photo, ImageDescriptionModel).outerjoin(
                    ImageDescriptionModel, Photo.id == ImageDescriptionModel.photo_id
                ).filter(
                    Photo.id.in_(photo_ids),
                    Photo.owner_id == current_user.id
                ).all()

                for photo, desc in photos_query:
                    score = 0
                    if desc:
                        score = (desc.memory_score or 0) + (desc.quality_score or 0)
                    
                    cluster_photos.append((photo, score))
                
                # Sort by score desc, then photo_time desc
                cluster_photos.sort(key=lambda x: (x[1], x[0].photo_time or datetime.min), reverse=True)
                
                if len(cluster_photos) < 2:
                    should_delete = True
            
            if should_delete:
                # Delete invalid cluster
                db.delete(cluster)
                # Commit to ensure DB state reflects deletion for next query or consistency
                db.commit() 
                deleted_count += 1
            else:
                result.append([x[0] for x in cluster_photos])
        
        # Update current_skip for the next iteration or next page logic
        # logic: we advanced 'processed_count' positions in the original list,
        # but 'deleted_count' items were removed, so the DB shifts.
        # Next item is at 'current_skip + processed_count - deleted_count'
        current_skip = current_skip + processed_count - deleted_count

    return BaseResponse(data=result)

@router.delete("/similar/tasks/{task_id}", response_model=BaseResponse[Dict[str, Any]])
def cancel_similar_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel/Delete a similar photo clustering task
    """
    task = crud_task.get_task_by_id_and_owner(db, task_id, current_user.id)
    
    if task:
        if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            task.status = TaskStatus.CANCELLED
            # Note: This doesn't stop the running thread immediately if it's processing, 
            # but TaskWorker should handle cancellation check.
        crud_task.delete_task(db, task)
    else:
        # Check if it exists in ImageCluster
        clusters = db.query(ImageCluster).filter(ImageCluster.task_id == str(task_id)).all()
        if not clusters:
            return BaseResponse(code=404, msg="Task not found", data=None)
        for cluster in clusters:
            db.delete(cluster)
            
    db.commit()
    return BaseResponse(data={"message": "Task deleted"})

@router.get("/similar", response_model=BaseResponse[List[List[schemas.SimilarPhoto]]], deprecated=True)
def get_similar_photos(
    threshold: float = 0.9,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"Getting similar photos with threshold {threshold} for user {current_user.id}")
    service = SimilarPhotoService(db, str(current_user.id))
    return BaseResponse(data=service.get_similar_groups(threshold))

@router.get("/cleanup", response_model=BaseResponse[List[schemas.Photo]])
def get_photos_for_cleanup(
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "asc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Join with ImageDescription to access scores
    query = db.query(Photo).join(ImageDescriptionModel, Photo.id == ImageDescriptionModel.photo_id).filter(Photo.owner_id == current_user.id, Photo.is_deleted == False)

    # Calculate score: memory_score + quality_score
    # We use coalesce to treat nulls as 0
    score_expr = func.coalesce(ImageDescriptionModel.memory_score, 0) + func.coalesce(ImageDescriptionModel.quality_score, 0)

    if sort_by == "desc":
        query = query.order_by(score_expr.desc())
    else:
        query = query.order_by(score_expr.asc())

    photos = query.offset(skip).limit(limit).all()
    return BaseResponse(data=photos)

@router.post("/organize/tasks", response_model=BaseResponse[TaskResponse])
def start_organize_task(
    req: OrganizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    触发图片文件整理任务。
    """
    existing_task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.ORGANIZE_PHOTOS, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )

    if existing_task:
        return BaseResponse(data=existing_task)

    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.ORGANIZE_PHOTOS,
        payload=req.model_dump(),
        owner_id=current_user.id
    )
    return BaseResponse(data=task)

@router.post("/organize/preview-options", response_model=BaseResponse[OrganizePreviewOptionsResponse])
def get_organize_preview_options(
    req: OrganizePreviewOptionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取整理策略的可用选项列表。
    """
    from app.db.models.photo import Photo
    from app.db.models.face import Face, FaceIdentity
    from app.db.models.tag import PhotoTag, PhotoTagRelation
    from app.db.models.photo_metadata import PhotoMetadata
    from sqlalchemy import and_, or_
    import os
    
    options = set()
    
    if req.strategy == 'category':
        tags = db.query(PhotoTag.tag_name)\
            .join(PhotoTagRelation, PhotoTag.id == PhotoTagRelation.tag_id)\
            .join(Photo, PhotoTagRelation.photo_id == Photo.id)\
            .filter(Photo.owner_id == current_user.id, Photo.is_deleted.is_(False))\
            .distinct().all()
            
        for (tag_name,) in tags:
            if tag_name:
                options.add(tag_name)
                
        has_untagged = db.query(Photo.id)\
            .outerjoin(PhotoTagRelation, Photo.id == PhotoTagRelation.photo_id)\
            .filter(
                Photo.owner_id == current_user.id, 
                Photo.is_deleted.is_(False),
                PhotoTagRelation.tag_id.is_(None)
            ).first()
            
        if has_untagged:
            options.add('未分类')

    elif req.strategy == 'person':
        identities = db.query(FaceIdentity.identity_name)\
            .join(Face, FaceIdentity.id == Face.face_identity_id)\
            .join(Photo, Face.photo_id == Photo.id)\
            .filter(
                Photo.owner_id == current_user.id, 
                Photo.is_deleted.is_(False),
                FaceIdentity.identity_name.isnot(None),
                FaceIdentity.identity_name != ''
            ).distinct().all()
            
        for (identity_name,) in identities:
            options.add(identity_name)
            
        valid_photo_ids_query = db.query(Face.photo_id)\
            .join(FaceIdentity, Face.face_identity_id == FaceIdentity.id)\
            .filter(FaceIdentity.identity_name.isnot(None), FaceIdentity.identity_name != '')
            
        has_unnamed = db.query(Photo.id)\
            .filter(
                Photo.owner_id == current_user.id, 
                Photo.is_deleted.is_(False),
                Photo.id.notin_(valid_photo_ids_query)
            ).first()
            
        if has_unnamed:
            options.add('未命名')

    elif req.strategy == 'location':
        locations = db.query(PhotoMetadata.province, PhotoMetadata.city, PhotoMetadata.district)\
            .join(Photo, PhotoMetadata.photo_id == Photo.id)\
            .filter(Photo.owner_id == current_user.id, Photo.is_deleted.is_(False))\
            .distinct().all()
            
        for prov, city, dist in locations:
            if not prov and not city and not dist:
                continue
                
            parts = []
            if req.location_granularity == 'province' and prov:
                parts.append(prov)
            elif req.location_granularity == 'city' and city:
                parts.append(city)
            elif req.location_granularity == 'district' and dist:
                parts.append(dist)
            elif req.location_granularity == 'province_city':
                if prov: parts.append(prov)
                if city and (not parts or parts[-1] != city): parts.append(city)
            elif req.location_granularity == 'city_district':
                if city: parts.append(city)
                if dist and (not parts or parts[-1] != dist): parts.append(dist)
            elif req.location_granularity == 'province_city_district':
                if prov: parts.append(prov)
                if city and (not parts or parts[-1] != city): parts.append(city)
                if dist and (not parts or parts[-1] != dist): parts.append(dist)
            
            if not parts:
                options.add('未知位置')
            else:
                if req.location_format == 'nested':
                    options.add(os.path.join(*parts))
                else:
                    options.add("-".join(parts))
                    
        if '未知位置' not in options:
            has_unknown_location = db.query(Photo.id)\
                .outerjoin(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
                .filter(
                    Photo.owner_id == current_user.id, 
                    Photo.is_deleted.is_(False),
                    or_(
                        PhotoMetadata.photo_id.is_(None),
                        and_(
                            (PhotoMetadata.province == '') | PhotoMetadata.province.is_(None),
                            (PhotoMetadata.city == '') | PhotoMetadata.city.is_(None),
                            (PhotoMetadata.district == '') | PhotoMetadata.district.is_(None)
                        )
                    )
                ).first()
                
            if has_unknown_location:
                options.add('未知位置')
                
    return BaseResponse(data=OrganizePreviewOptionsResponse(options=list(options)))

@router.get("/organize/tasks/latest", response_model=BaseResponse[Optional[TaskResponse]])
def get_latest_organize_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.ORGANIZE_PHOTOS, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value, TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]
    )
    return BaseResponse(data=task)

@router.post("/rename/tasks", response_model=BaseResponse[TaskResponse])
def start_rename_task(
    req: RenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    触发批量重命名任务。
    """
    existing_task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.BATCH_RENAME, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )

    if existing_task:
        return BaseResponse(data=existing_task)

    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.BATCH_RENAME,
        payload=req.model_dump(),
        owner_id=current_user.id
    )
    return BaseResponse(data=task)

@router.get("/rename/tasks/latest", response_model=BaseResponse[Optional[TaskResponse]])
def get_latest_rename_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.BATCH_RENAME, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value, TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]
    )
    return BaseResponse(data=task)

@router.post("/time-from-filename/tasks", response_model=BaseResponse[TaskResponse])
def start_time_from_filename_task(
    req: TimeFromFilenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    触发从文件名修改时间任务。
    """
    existing_task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.BATCH_TIME_FROM_FILENAME, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )

    if existing_task:
        return BaseResponse(data=existing_task)

    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.BATCH_TIME_FROM_FILENAME,
        payload=req.model_dump(),
        owner_id=current_user.id
    )
    return BaseResponse(data=task)

@router.get("/time-from-filename/tasks/latest", response_model=BaseResponse[Optional[TaskResponse]])
def get_latest_time_from_filename_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.BATCH_TIME_FROM_FILENAME, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value, TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]
    )
    return BaseResponse(data=task)

