"""The bounded map payload. Counts always describe the full selected year."""

from datetime import datetime
from pydantic import BaseModel, Field


class FootprintSummary(BaseModel):
    photo_count: int = 0
    gps_photo_count: int = 0
    province_count: int = 0
    city_count: int = 0
    country_count: int = 0
    visit_count: int = 0


class FootprintCity(BaseModel):
    id: str
    name: str
    province: str
    country: str
    lat: float
    lng: float
    photo_count: int
    visit_count: int
    cover_id: str
    first_at: datetime | None
    last_at: datetime | None


class FootprintRoute(BaseModel):
    id: str
    # A route is a connection between photographed places, not a transport track.
    from_: tuple[float, float] = Field(alias="from")
    to: tuple[float, float]
    from_name: str
    to_name: str
    start_at: datetime
    end_at: datetime
    photo_count: int


class FootprintYear(BaseModel):
    year: int
    photo_count: int
    city_count: int


class FootprintResponse(BaseModel):
    years: list[int]
    summary: FootprintSummary
    cities: list[FootprintCity]
    routes: list[FootprintRoute]
    timeline: list[FootprintYear]
    sampled: bool = False
