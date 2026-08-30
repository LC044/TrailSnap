from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.metadata import PhotoDetail


Decision = Literal["keep", "delete"]


class SwipeFilterStats(BaseModel):
    processed: int
    remaining: int
    total: int
    kept: int
    deleted: int


class SwipeFilterBatch(BaseModel):
    photos: List[PhotoDetail]
    stats: SwipeFilterStats


class SwipeFilterDecisionItem(BaseModel):
    photo_id: UUID
    decision: Decision


class SwipeFilterDecisionRequest(BaseModel):
    items: List[SwipeFilterDecisionItem] = Field(min_length=1, max_length=100)


class SwipeFilterDecisionResult(BaseModel):
    updated: int


class SwipeFilterUndoResult(BaseModel):
    undone: bool


class SwipeFilterResetResult(BaseModel):
    reset: int
