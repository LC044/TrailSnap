from pydantic import BaseModel
from typing import List, Optional

from app.schemas.face import FaceIdentitySchema


class DashboardCard(BaseModel):
    total_media: int
    today_new: int
    storage_used: str

class DashboardFace(BaseModel):
    total_identified: int
    top_faces: List[FaceIdentitySchema]
    pending_faces_count: int
    unidentified_photos_count: int

class ContentDetail(BaseModel):
    total: int
    sub_1_label: str
    sub_1_count: int
    sub_2_label: str
    sub_2_count: int

class DashboardContentStats(BaseModel):
    photos: ContentDetail
    videos: ContentDetail
    scenery_count: int
    food_count: int

class DashboardTimeChartItem(BaseModel):
    year: int
    count: int
    percentage: float
    color: str

class DashboardTime(BaseModel):
    current_year_percentage: int
    chart_data: List[DashboardTimeChartItem]
    monthly_peak: str

class HeatmapItem(BaseModel):
    date: str
    count: int

class HeatmapResponse(BaseModel):
    total_photos: int
    total_days: int
    max_consecutive_days: int
    data: List[HeatmapItem]
    available_years: List[int]

class EmotionCalendarItem(BaseModel):
    date: str
    photo_count: int
    dominant_color: Optional[str] = None
    brightness: Optional[float] = None
    saturation: Optional[float] = None
    top_categories: List[str] = []
    emotion_hint: Optional[str] = None

class EmotionCalendarResponse(BaseModel):
    total_photos: int
    total_days: int
    data: List[EmotionCalendarItem]
    available_years: List[int]

class DashboardResponse(BaseModel):
    card: DashboardCard
    face: DashboardFace
    content: DashboardContentStats
    time: DashboardTime
