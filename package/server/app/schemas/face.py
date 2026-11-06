from typing import Optional, List, Any, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.photo import Photo


# Face Schemas
class PhotoFace(BaseModel):
    id: int
    photo_id: UUID
    face_rect: Optional[List[float]] = None
    identity_id: Optional[UUID] = None
    identity_name: Optional[str] = None


class AssignPhotoFace(BaseModel):
    identity_id: Optional[UUID] = Field(..., description="人物ID；null表示移除此脸归属")


class SimilarFaceCandidate(PhotoFace):
    photo_time: Optional[datetime] = None
    similarity: float
    manually_confirmed: bool
    review_token: str


class SimilarFacesResult(BaseModel):
    reference: SimilarFaceCandidate
    items: List[SimilarFaceCandidate]
    face_count: int
    photo_count: int
    has_more: bool


class SimilarFaceSelection(BaseModel):
    face_id: int = Field(gt=0)
    review_token: str = Field(min_length=1, max_length=4096)


class AssignSimilarFaces(BaseModel):
    identity_id: Optional[UUID] = Field(..., description="目标人物ID；null表示释放为未标记人脸")
    selections: List[SimilarFaceSelection] = Field(min_length=1, max_length=500)


class UndoFaceAssignment(BaseModel):
    undo_token: str = Field(min_length=1, max_length=200000)


class BatchFaceAssignmentResult(BaseModel):
    face_count: int
    photo_ids: List[UUID]
    undo_token: Optional[str] = None


SimilarFaceScope = Literal["all", "current", "current_low", "other", "unassigned"]
SimilarFaceMatch = Literal["strict", "balanced", "broad"]


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
    # extra="forbid"：合并入口的字段一旦被前后端版本错配（旧 schema 不认识新字段），
    # 必须显式 422 报错，而不是静默丢弃 identity_name 让合并结果退回“未命名”
    model_config = ConfigDict(extra="forbid")
    source_ids: List[UUID] = Field(..., description="源人物ID列表")
    target_id: UUID = Field(..., description="目标人物ID")
    identity_name: Optional[str] = Field(None, min_length=1, max_length=500, description="合并后人物名称")

    @field_validator("identity_name", mode="before")
    @classmethod
    def trim_identity_name(cls, value):
        return value.strip() if isinstance(value, str) else value

class RemovePhotosRequest(BaseModel):
    photo_ids: List[UUID] = Field(..., description="要移除的照片ID列表")

class SetCoverRequest(BaseModel):
    photo_id: UUID = Field(..., description="设置为封面的照片ID")

class AddPhotosToIdentityRequest(BaseModel):
    photo_ids: List[UUID] = Field(..., description="要添加的照片ID列表")


class FaceRescanApplyRequest(BaseModel):
    add_face_ids: List[int] = Field(default_factory=list, description="确认新增或改归属的人脸ID")
    remove_face_ids: List[int] = Field(default_factory=list, description="确认从当前人物移出的人脸ID")


class GroupAlbumIdentity(BaseModel):
    identity_id: UUID = Field(..., description="人物ID")
    identity_name: Optional[str] = Field(None, description="人物名称")


class GroupAlbumItem(BaseModel):
    """合影组合相册：一组经常同框出现的“可展示人物”及其共同照片。

    与“个人”栏口径一致：组合成员都满足单人展示阈值（照片数 >= min_photos）；
    photo_count 是同时包含全部成员的照片数。
    """
    identities: List[GroupAlbumIdentity] = Field(default_factory=list, description="组合成员")
    photo_count: int = Field(0, description="组合合影照片数")
    cover: Photo = Field(..., description="封面照片（组合内最新一张）")
