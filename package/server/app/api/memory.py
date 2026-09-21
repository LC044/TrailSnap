from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.memory import MemoryStatus
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.memory import (
    MemoryCreate,
    MemoryDiscoverRequest,
    MemoryMergeRequest,
    MemoryPhotoChange,
    MemorySplitRequest,
    MemoryStoryRequest,
    MemoryUpdate,
)
from app.service import memory as memory_service


router = APIRouter()


@router.get("", summary="获取记忆列表")
def list_memories(
    status: MemoryStatus = Query(MemoryStatus.CONFIRMED),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = memory_service.list_owned(db, current_user.id, status, skip, limit)
    return BaseResponse.success(data={
        "items": [memory_service.serialize(db, row) for row in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    })


@router.get("/counts", summary="获取各状态记忆数量")
def memory_counts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    counts = {}
    for status in (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED, MemoryStatus.IGNORED):
        _, total = memory_service.list_owned(db, current_user.id, status, 0, 1)
        counts[status.value] = total
    return BaseResponse.success(data=counts)


@router.post("/discover", summary="从照片中发现候选记忆")
def discover_memories(
    payload: MemoryDiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = memory_service.discover(
        db,
        current_user.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        min_photos=payload.min_photos,
        max_candidates=payload.max_candidates,
    )
    return BaseResponse.success(data={
        "created": len(rows),
        "items": [memory_service.serialize(db, row) for row in rows],
    })


@router.post("/merge", summary="合并记忆")
def merge_memories(
    payload: MemoryMergeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.merge(
        db, current_user.id, payload.memory_ids,
        title=payload.title, story=payload.story, cover_photo_id=payload.cover_photo_id,
    )
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("", summary="手动创建记忆")
def create_memory(
    payload: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.create(db, current_user.id, payload)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.get("/{memory_id}", summary="获取记忆详情")
def get_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.patch("/{memory_id}", summary="编辑记忆")
def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    row = memory_service.update(db, row, current_user.id, payload)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("/{memory_id}/confirm", summary="确认候选记忆")
def confirm_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    if row.status not in {MemoryStatus.CANDIDATE, MemoryStatus.IGNORED}:
        raise HTTPException(status_code=400, detail="当前状态不能确认")
    row = memory_service.change_status(db, row, MemoryStatus.CONFIRMED)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("/{memory_id}/story/generate", summary="使用 AI 生成记忆故事")
async def generate_memory_story(
    memory_id: UUID,
    payload: MemoryStoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    row = await memory_service.generate_story(db, row, current_user.id, tone=payload.tone)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("/{memory_id}/ignore", summary="忽略候选记忆")
def ignore_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    if row.status != MemoryStatus.CANDIDATE:
        raise HTTPException(status_code=400, detail="只有候选记忆可以忽略")
    row = memory_service.change_status(db, row, MemoryStatus.IGNORED)
    return BaseResponse.success(data=memory_service.serialize(db, row))


@router.post("/{memory_id}/restore", summary="恢复记忆")
def restore_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    target = MemoryStatus.CANDIDATE if row.status == MemoryStatus.IGNORED else MemoryStatus.CONFIRMED
    if row.status not in {MemoryStatus.IGNORED, MemoryStatus.ARCHIVED}:
        raise HTTPException(status_code=400, detail="当前状态不能恢复")
    row = memory_service.change_status(db, row, target)
    return BaseResponse.success(data=memory_service.serialize(db, row))


@router.post("/{memory_id}/archive", summary="归档记忆")
def archive_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    if row.status != MemoryStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="只有已确认记忆可以归档")
    row = memory_service.change_status(db, row, MemoryStatus.ARCHIVED)
    return BaseResponse.success(data=memory_service.serialize(db, row))


@router.post("/{memory_id}/photos/add", summary="向记忆添加照片")
def add_memory_photos(
    memory_id: UUID,
    payload: MemoryPhotoChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    row = memory_service.add_photos(db, row, current_user.id, payload.photo_ids)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("/{memory_id}/photos/remove", summary="从记忆移除照片")
def remove_memory_photos(
    memory_id: UUID,
    payload: MemoryPhotoChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    row = memory_service.remove_photos(db, row, current_user.id, payload.photo_ids)
    return BaseResponse.success(data=memory_service.serialize(db, row, detail=True))


@router.post("/{memory_id}/split", summary="拆分记忆")
def split_memory(
    memory_id: UUID,
    payload: MemorySplitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = memory_service.split(db, current_user.id, memory_id, payload)
    return BaseResponse.success(data=[memory_service.serialize(db, row, detail=True) for row in rows])


@router.delete("/{memory_id}", summary="删除记忆")
def delete_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = memory_service.get_detail(db, memory_id, current_user.id)
    memory_service.change_status(db, row, MemoryStatus.DELETED)
    return BaseResponse.success(data={"deleted": True})
