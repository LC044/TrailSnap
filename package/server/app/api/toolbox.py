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
    score_subquery = db.query(
        ImageDescriptionModel.photo_id.label("photo_id"),
        func.max(
            func.coalesce(ImageDescriptionModel.memory_score, 0) +
            func.coalesce(ImageDescriptionModel.quality_score, 0)
        ).label("score")
    ).group_by(ImageDescriptionModel.photo_id).subquery()

    query = db.query(Photo).join(
        score_subquery,
        Photo.id == score_subquery.c.photo_id
    ).filter(
        Photo.owner_id == current_user.id,
        Photo.is_deleted == False
    )

    if sort_by == "desc":
        query = query.order_by(
            score_subquery.c.score.desc(),
            Photo.photo_time.desc().nulls_last(),
            Photo.id.desc(),
        )
    else:
        query = query.order_by(
            score_subquery.c.score.asc(),
            Photo.photo_time.asc().nulls_last(),
            Photo.id.asc(),
        )

    photos = query.offset(skip).limit(limit).all()
    return BaseResponse(data=photos)
