from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.photo import Photo


# Face Schemas
class FaceBase(BaseModel):
    face_rect: Optional[List[float]] = None
    face_confidence: Optional[float] = None
    recognize_confidence: Optional[float] = None
    face_feature: Optional[Any] = None

class FaceCreate(FaceBase):
    photo_id: UUID
    face_identity_id: Optional[UUID] = None

class FaceUpdate(FaceBase):
    face_identity_id: Optional[UUID] = None

# FaceIdentity Schemas
class FaceIdentityBase(BaseModel):
    identity_name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

class FaceIdentityCreate(FaceIdentityBase):
    pass

class FaceIdentityUpdate(FaceIdentityBase):
    default_face_id: Optional[int] = None
    is_hidden: Optional[bool] = None

class CoverPhotoInfo(BaseModel):
    photo_id: UUID = Field(..., description="封面照片ID")
    width: Optional[int] = Field(None, description="照片宽度")
    height: Optional[int] = Field(None, description="照片高度")
    face_rect: Optional[List[float]] = Field(None, description="人脸位置坐标 [x1, y1, x2, y2]")
    face_confidence: Optional[float] = Field(None, description="人脸检测置信度")
    recognize_confidence: Optional[float] = Field(None, description="人脸聚类置信度")

class FaceIdentitySchema(BaseModel):
    id: UUID = Field(..., description="人物ID")
    identity_name: Optional[str] = Field(None, description="人物名称")
    description: Optional[str] = Field(None, description="人物描述")
    tags: Optional[List[str]] = Field(None, description="人物标签")
    default_face_id: Optional[int] = Field(None, description="默认封面人脸ID")
    face_count: Optional[int] = Field(0, description="照片数量")
    cover_photo: Optional[CoverPhotoInfo] = Field(None, description="封面照片信息")
    cover: Optional[Photo] = Field(None, description="封面照片")
    is_hidden: Optional[bool] = Field(False, description="是否隐藏")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True

class MergeRequest(BaseModel):
    source_ids: List[UUID] = Field(..., description="源人物ID列表")
    target_id: UUID = Field(..., description="目标人物ID")

class RemovePhotosRequest(BaseModel):
    photo_ids: List[UUID] = Field(..., description="要移除的照片ID列表")

class SetCoverRequest(BaseModel):
    photo_id: UUID = Field(..., description="设置为封面的照片ID")

class AddPhotosToIdentityRequest(BaseModel):
    photo_ids: List[UUID] = Field(..., description="要添加的照片ID列表")


class FaceRescanApplyRequest(BaseModel):
    add_face_ids: List[int] = Field(default_factory=list, description="确认新增或改归属的人脸ID")
    remove_face_ids: List[int] = Field(default_factory=list, description="确认从当前人物移出的人脸ID")
