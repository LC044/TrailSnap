from pydantic import BaseModel
from typing import List, Optional


class OverviewStats(BaseModel):
    total_distance_km: float
    province_count: int
    city_count: int
    scene_count: int
    travel_days: int
    farthest_place: Optional[str] = None
    farthest_distance_km: float
    has_location: bool


class AnnualTrendItem(BaseModel):
    year: int
    photo_count: int
    distance_km: float


class MonthlyRadarItem(BaseModel):
    month: int
    photo_count: int
    activity_score: int


class PlaceStats(BaseModel):
    name: str
    level: str
    photo_count: int
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    visit_count: int
    visit_dates: List[str] = []


class PlacesResponse(BaseModel):
    top_places: List[PlaceStats] = []
    revisits: List[PlaceStats] = []


class HeatmapItem(BaseModel):
    date: str
    count: int


class HeatmapRangeResponse(BaseModel):
    total_photos: int
    total_days: int
    data: List[HeatmapItem] = []
