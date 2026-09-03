from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, computed_field
from app.db.models.photo import FileType
# from app.schemas.metadata import PhotoMetadata
from app.schemas.image_description import ImageDescription

# Photo Schemas

class BatchDownloadRequest(BaseModel):
    photo_ids: List[UUID]


class PhotoBase(BaseModel):
    file_type: FileType
    size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    filename: Optional[str] = Field(default=None, max_length=255)
    photo_time: Optional[datetime] = None
    md5: Optional[str] = Field(default=None, exclude=True)

class PhotoCreate(PhotoBase):
    pass

class PhotoUpdate(BaseModel):
    filename: Optional[str] = Field(default=None, max_length=255)
    photo_time: Optional[datetime] = None
    modify_original_file: Optional[bool] = False

class Photo(PhotoBase):
    id: UUID
    file_path: str = Field(exclude=True)
    upload_time: datetime = Field(exclude=True)

    class Config:
        from_attributes = True

class RecyclePhoto(Photo):
    # Optional on purpose. The column is nullable, so a single row with
    # is_deleted=True but no timestamp (legacy data, a manual SQL fix, or a future
    # soft-delete path that forgets to stamp it) would otherwise fail
    # response_model validation and take the *entire* recycle-bin listing down
    # with a 500. The UI already falls back to the full retention window when this
    # is absent.
    deleted_at: Optional[datetime] = None

class PhotoGroup(BaseModel):
    date: str
    items: List[Photo]

class BatchPhotoUpdate(BaseModel):
    photo_ids: List[UUID]
    album_id: Optional[UUID] = None # For adding to album
    action: str # 'add_to_album', 'remove_from_album', 'delete'

class BatchPhotoDelete(BaseModel):
    photo_ids: List[UUID]

class RecycleBinPurge(BaseModel):
    """Payload for the recycle-bin purge endpoint.

    ``photo_ids = None`` means "everything currently in my bin". That distinction
    is what lets the UI offer a real "empty recycle bin" action: the client no
    longer has to page through the whole bin just to collect ids it would
    immediately send back.
    """
    photo_ids: Optional[List[UUID]] = None

class RecycleBinStats(BaseModel):
    total: int
    retention_days: int

class BatchPhotoTransfer(BaseModel):
    photo_ids: List[UUID]
    target_path: str
    action: str # 'move' or 'copy'

class BatchPhotoDataUpdate(BaseModel):
    photo_ids: List[UUID]
    photo_time: Optional[datetime] = None
    description: Optional[str] = None
    # Add other fields as needed

class BatchPhotoTagsUpdate(BaseModel):
    photo_ids: List[UUID]
    action: str # 'add' or 'remove'
    tags: List[str]

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
