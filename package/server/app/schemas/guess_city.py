from pydantic import BaseModel
from typing import List, Optional

class CityCoordinate(BaseModel):
    city: str
    latitude: float
    longitude: float

class GuessRequest(BaseModel):
    photo_id: str
    guess_city: str

class GuessResult(BaseModel):
    correct: bool
    actual_city: str
    distance_km: float
    bearing: float
    direction: str
