from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    story: str | None = Field(default=None, max_length=50_000)
    photo_ids: list[UUID] = Field(min_length=1, max_length=5000)
    cover_photo_id: UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    place_names: list[str] = Field(default_factory=list, max_length=20)
    person_ids: list[UUID] = Field(default_factory=list, max_length=50)
    ticket_refs: list[dict[str, str]] = Field(default_factory=list, max_length=50)
    origin: Literal["manual", "album", "agent"] = "manual"

    @model_validator(mode="after")
    def validate_cover(self):
        if self.cover_photo_id and self.cover_photo_id not in self.photo_ids:
            raise ValueError("封面必须属于记忆照片")
        return self


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    story: str | None = Field(default=None, max_length=50_000)
    cover_photo_id: UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    place_names: list[str] | None = Field(default=None, max_length=20)
    person_ids: list[UUID] | None = Field(default=None, max_length=50)
    ticket_refs: list[dict[str, str]] | None = Field(default=None, max_length=50)


class MemoryPhotoChange(BaseModel):
    photo_ids: list[UUID] = Field(min_length=1, max_length=5000)


class MemoryDiscoverRequest(BaseModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    min_photos: int = Field(default=5, ge=3, le=50)
    max_candidates: int = Field(default=50, ge=1, le=200)


class MemoryStoryRequest(BaseModel):
    tone: str = Field(default="温暖、克制、真实", min_length=1, max_length=100)


class MemoryMergeRequest(BaseModel):
    memory_ids: list[UUID] = Field(min_length=2, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    story: str | None = Field(default=None, max_length=50_000)
    cover_photo_id: UUID | None = None


class MemorySplitPart(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    photo_ids: list[UUID] = Field(min_length=1, max_length=5000)


class MemorySplitRequest(BaseModel):
    parts: list[MemorySplitPart] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_unique_photos(self):
        all_ids = [photo_id for part in self.parts for photo_id in part.photo_ids]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("拆分后的照片不能重复")
        return self
