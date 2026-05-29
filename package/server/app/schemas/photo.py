from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, computed_field
from app.db.models.photo import FileType
# from app.schemas.metadata import PhotoMetadata
from app.schemas.image_description import ImageDescription

# Photo Schemas
class PhotoBase(BaseModel):
    file_type: FileType
    size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    filename: Optional[str] = None
    photo_time: Optional[datetime] = None
    md5: Optional[str] = Field(default=None, exclude=True)

class PhotoCreate(PhotoBase):
    pass

class PhotoUpdate(BaseModel):
    filename: Optional[str] = None
    photo_time: Optional[datetime] = None
    modify_original_file: Optional[bool] = False

class Photo(PhotoBase):
    id: UUID
    file_path: str = Field(exclude=True)
    upload_time: datetime = Field(exclude=True)

    class Config:
        from_attributes = True

class RecyclePhoto(Photo):
    deleted_at: datetime

class PhotoGroup(BaseModel):
    date: str
    items: List[Photo]

class BatchPhotoUpdate(BaseModel):
    photo_ids: List[UUID]
    album_id: Optional[UUID] = None # For adding to album
    action: str # 'add_to_album', 'remove_from_album', 'delete'

class BatchPhotoDelete(BaseModel):
    photo_ids: List[UUID]

class BatchPhotoTransfer(BaseModel):
    photo_ids: List[UUID]
    target_path: str
    action: str # 'move' or 'copy'

class PhotoCreateItem(BaseModel):
    photo: PhotoCreate
    file_path: str
    photo_id: UUID

class BatchPhotoCreate(BaseModel):
    items: List[PhotoCreateItem]

class SimilarPhoto(BaseModel):
    id: str
    filename: Optional[str] = None
    photo_time: Optional[datetime] = None
    score: float
    thumbnail_path: str
    src: str
