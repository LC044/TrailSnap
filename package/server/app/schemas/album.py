from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, computed_field
from app.schemas.photo import Photo
from app.schemas.user import UserResponse

# Album Schemas
class AlbumBase(BaseModel):
    name: str
    description: Optional[str] = None
    type: str = "user"
    condition: Optional[Dict[str, Any]] = None
    threshold: Optional[float] = 0.25

class AlbumCreate(AlbumBase):
    shared_users: Optional[List[UUID]] = None

class AlbumUpdate(AlbumBase):
    name: Optional[str] = None
    description: Optional[str] = None
    shared_users: Optional[List[UUID]] = None

class Album(AlbumBase):
    id: UUID
    create_time: datetime
    cover: Optional[Photo] = None
    type: str = "user"
    condition: Optional[Dict[str, Any]] = None
    num_photos: int = 0
    threshold: Optional[float] = 0.25
    shared_users: List[UserResponse] = []

    class Config:
        from_attributes = True

class TimelineItem(BaseModel):
    year: int
    month: int
    day: int
    count: int

class TimelineStats(BaseModel):
    total_photos: int
    time_range: Optional[Dict[str, datetime]] = None
    timeline: List[TimelineItem] = []

class SmartAlbumRepresentative(BaseModel):
    entity_id: str
    name: str
    photo_id: Optional[UUID] = None
    face_rect: Optional[List[float]] = None
    photo_count: int = 0


class SmartAlbumSection(BaseModel):
    item_count: int = 0
    photo_count: int = 0
    representatives: List[SmartAlbumRepresentative] = Field(default_factory=list)


class SmartAlbumOverview(BaseModel):
    people: SmartAlbumSection = Field(default_factory=SmartAlbumSection)
    location: SmartAlbumSection = Field(default_factory=SmartAlbumSection)
    classification: SmartAlbumSection = Field(default_factory=SmartAlbumSection)
