from fastapi import APIRouter, Depends, Query, Path, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from pydantic import BaseModel

from app.api import deps
from app.db.models import User
from app.dependencies import get_db, BaseResponse
from app.schemas import tag as schemas
from app.crud import tag as crud
from app.schemas import photo as photo_schemas

router = APIRouter()
from app.api.clip_classification import router as clip_router
router.include_router(clip_router, prefix='/clip')

class RemovePhotosRequest(BaseModel):
    photo_ids: List[UUID]

@router.get("", response_model=BaseResponse[List[schemas.TagStats]], summary="获取智能分类标签列表")
def get_tags(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取智能分类标签列表，包含每个标签的封面图片和照片数量。
    """
    data = crud.get_tags_with_stats(db, current_user.id, skip, limit)
    return BaseResponse(data=data)

@router.get("/{path:path}/photos", response_model=BaseResponse[List[photo_schemas.Photo]], summary="获取分类照片列表")
def get_tag_photos(
    # path=True 声明：匹配剩余的全部路径（支持包含/）
    tag_id: UUID | None = None,
    path: str = Path(..., description="标签名称（支持多级/包含/）", path=True),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # 注意：参数名从name改为path，传给crud层即可
    photos = crud.get_photos_by_tag_name(db, current_user.id, path, skip, limit, **({"tag_id": tag_id} if tag_id else {}))
    return BaseResponse(data=photos)

@router.post("/{path:path}/remove-photos", summary="从分类中移除照片")
def remove_photos_from_tag(
    payload: RemovePhotosRequest = Body(..., description="要移除的照片列表"),
    tag_id: UUID | None = None,
    path: str = Path(..., description="标签名称（支持多级/包含/）", path=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    将指定的照片从某个智能分类标签中移除。
    
    - **path**: 标签名称
    - **payload.photo_ids**: 照片ID列表
    """
    count = crud.remove_photos_from_tag(db, current_user.id, path, payload.photo_ids, **({"tag_id": tag_id} if tag_id else {}))
    if count == 0:
        raise HTTPException(status_code=404, detail="Tag not found or no photos removed")
    
    # 触发相册更新
    from app.crud.album import trigger_conditional_albums_update
    trigger_conditional_albums_update(db, current_user.id, payload.photo_ids)
    
    return {"status": "success", "count": count}

class SetCoverRequest(BaseModel):
    photo_id: UUID

@router.post("/{path:path}/cover", summary="设置分类封面")
def set_tag_cover(
    payload: SetCoverRequest = Body(..., description="封面照片ID"),
    tag_id: UUID | None = None,
    path: str = Path(..., description="标签名称（支持多级/包含/）", path=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    设置分类的封面照片。
    
    - **path**: 标签名称
    - **payload.photo_id**: 照片ID
    """
    success = crud.set_tag_cover(db, current_user.id, path, payload.photo_id, **({"tag_id": tag_id} if tag_id else {}))
    if not success:
        return BaseResponse(
            code=404,
            msg="Tag or photo not found"
        )
    return BaseResponse(
        msg = 'success'
    )
