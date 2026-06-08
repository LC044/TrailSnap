from typing import Optional, List
from pydantic import BaseModel, Field


class NavItemRef(BaseModel):
    entity_type: str = Field(..., description="album | person | location | classification")
    entity_id: str = Field(..., description="UUID for album/person/classification; name string for location")


class ResolvedNavItem(BaseModel):
    entity_type: str
    entity_id: str
    name: str
    cover_photo_id: Optional[str] = None
    cover_photo_face_rect: Optional[List[float]] = None
    route_path: str
    photo_count: int = 0


class NavItemsUpdate(BaseModel):
    items: List[NavItemRef]


class NavItemsResponse(BaseModel):
    items: List[ResolvedNavItem]
