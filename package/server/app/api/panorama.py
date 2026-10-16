from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.db.models.task import Task, TaskType, TaskStatus
from app.dependencies import BaseResponse, get_db
from app.service.panorama import detect_file, derivative
from app.utils.panorama import apply_detection, full_geometry, validate_geometry

router = APIRouter()


class PanoramaUpdate(BaseModel):
    mode: Literal["auto", "ordinary", "equirectangular"]
    geometry: dict | None = None


def owned_photo(db: Session, owner_id: UUID, photo_id: UUID) -> Photo | None:
    return db.query(Photo).filter(Photo.id == photo_id, Photo.owner_id == owner_id,
                                  Photo.is_deleted.is_(False), Photo.file_type == FileType.image).first()


def describe(photo: Photo) -> dict:
    return {"projection": photo.panorama_projection, "geometry": photo.panorama_metadata,
            "override": photo.panorama_override, "source": "manual" if photo.panorama_override else "metadata",
            "width": photo.width, "height": photo.height}


@router.get("/{photo_id}/panorama", response_model=BaseResponse[dict])
def get_panorama(photo_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    photo = owned_photo(db, user.id, photo_id)
    if not photo:
        return BaseResponse.fail(code=404, msg="照片不存在")
    return BaseResponse.success(data=describe(photo))


@router.put("/{photo_id}/panorama", response_model=BaseResponse[dict])
def update_panorama(photo_id: UUID, payload: PanoramaUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    photo = owned_photo(db, user.id, photo_id)
    if not photo:
        return BaseResponse.fail(code=404, msg="照片不存在")
    try:
        if payload.mode == "auto":
            detected = detect_file(photo.file_path)
            db.refresh(photo)
            photo.panorama_override = None
            apply_detection(photo, detected)
        elif payload.mode == "ordinary":
            photo.panorama_override = "ordinary"
            photo.panorama_projection = None
            photo.panorama_metadata = None
        else:
            from app.service.disk_budget import budgeted_open
            from app.utils.image_loading import Image
            with budgeted_open(photo.file_path) as source, Image.open(source) as image:
                if image.getexif().get(274, 1) != 1:
                    raise ValueError("请先将图片方向归一化后再设置全景")
                candidate = payload.geometry or photo.panorama_metadata or photo.panorama_detected
                geometry = validate_geometry(candidate, image.width, image.height) if candidate else full_geometry(image.width, image.height)
                photo.width, photo.height = image.width, image.height
            photo.panorama_override = "equirectangular"
            photo.panorama_projection = "equirectangular"
            photo.panorama_metadata = geometry
        db.commit()
        return BaseResponse.success(data=describe(photo))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        db.rollback()
        return BaseResponse.fail(code=400, msg=str(exc))


@router.get("/{photo_id}/panorama/image")
def panorama_image(photo_id: UUID, high: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    photo = owned_photo(db, user.id, photo_id)
    if not photo or not photo.panorama_projection or not photo.panorama_metadata:
        return BaseResponse.fail(code=404, msg="全景照片不存在")
    if high and (photo.panorama_metadata["fullWidth"] > 8192 or photo.panorama_metadata["fullWidth"] * photo.panorama_metadata["fullHeight"] > 33554432):
        return BaseResponse.fail(code=400, msg="请使用标准清晰度浏览此照片")
    try:
        path, width, height = derivative(photo, high)
    except (OSError, ValueError):
        return BaseResponse.fail(code=400, msg="全景预览生成失败")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache",
        "X-Panorama-Width": str(width), "X-Panorama-Height": str(height)})


@router.post("/panorama/scan", response_model=BaseResponse[dict])
def scan_panorama(after: UUID | None = None, limit: int = Query(200, ge=1, le=500),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False), Photo.file_type == FileType.image)
    if after:
        query = query.filter(Photo.id > after)
    rows = query.order_by(Photo.id).limit(limit + 1).all()
    ids = [row.id for row in rows[:limit]]
    active = {row.photo_id for row in db.query(Task.photo_id).filter(Task.owner_id == user.id,
        Task.type == TaskType.SCAN_PANORAMA.value, Task.status.in_([TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]), Task.photo_id.in_(ids)).all()}
    for photo_id in ids:
        if photo_id not in active:
            db.add(Task(type=TaskType.SCAN_PANORAMA.value, photo_id=photo_id, owner_id=user.id,
                        payload={"photo_id": str(photo_id)}, priority=10000))
    db.commit()
    from app.service.task_manager import TaskManager
    TaskManager.get_instance().start_worker_for_pending_tasks()
    return BaseResponse.success(data={"queued": len(set(ids) - active), "next": str(ids[-1]) if len(rows) > limit else None})
