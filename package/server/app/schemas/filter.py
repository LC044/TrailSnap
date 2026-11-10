from typing import List, Optional
from pydantic import BaseModel, Field

class FilterPersonOption(BaseModel):
    id: str
    name: str
    photo_count: int = 0
    photo_id: Optional[str] = None
    face_rect: Optional[List[float]] = None


class FilterOptions(BaseModel):
    years: List[int]
    cities: List[str]
    makes: List[str]
    models: List[str]
    image_types: List[str]
    file_types: List[str]
    people: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)

    person_options: List[FilterPersonOption] = Field(default_factory=list)
