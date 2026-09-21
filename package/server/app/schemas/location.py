from datetime import date, datetime
from typing import Optional, List, Union
from uuid import UUID

from pydantic import BaseModel, Field
from app.schemas.photo import Photo

class LocationBase(BaseModel):
    name: str
    level: str
    count: int

class LocationStatistics(BaseModel):
    province_count: int
    city_count: int
    district_count: int
    country_count: int

class Location(LocationBase):
    id: Optional[str] = None
    is_custom: Optional[bool] = None
    cover: Optional[Photo] = None

    class Config:
        from_attributes = True

class MapMarker(BaseModel):
    id: str
    lat: float
    lng: float

class LocationValue(BaseModel):
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

class LocationSearchItem(BaseModel):
    label: str
    value: LocationValue

class TimelineNode(BaseModel):
    type: str = "default"
    startDate: str
    endDate: str
    locationName: str
    level: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    photoCount: int = 0
    coverId: Optional[UUID] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    
class TimelineResponse(BaseModel):
    nodes: List[TimelineNode]
    total: int

class TrajectoryPoint(BaseModel):
    photoId: UUID
    capturedAt: datetime
    endAt: Optional[datetime] = None
    lat: float
    lng: float
    photoCount: int = 1
    coverId: Optional[UUID] = None
    locationName: str
    level: str = "city"

class TrajectoryResponse(BaseModel):
    points: List[TrajectoryPoint]
    totalPhotos: int
    sampled: bool = False


class TimeCompareYear(BaseModel):
    year: int
    photo_count: int
    first_date: datetime
    last_date: datetime
    cover: Photo


class TimeCompareVisit(BaseModel):
    date: date
    photo_count: int
    first_time: datetime
    last_time: datetime
    cover: Photo


class TimeCompareSummary(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    match_type: Optional[str] = None
    radius_m: Optional[int] = None
    visual_similarity: Optional[float] = None
    scene_id: Optional[UUID] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    city: Optional[str] = None
    source_photo_id: Optional[UUID] = None
    source_photo_year: Optional[int] = None
    years: List[TimeCompareYear] = Field(default_factory=list)
    visits: List[TimeCompareVisit] = Field(default_factory=list)
    first_photo: Optional[Photo] = None
    latest_photo: Optional[Photo] = None
