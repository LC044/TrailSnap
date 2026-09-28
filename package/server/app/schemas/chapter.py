from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ChapterDefinition(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=1000)
    start_date: date
    end_date: date | None = None
    cover_photo_id: UUID | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if not self.title.strip():
            raise ValueError("章节名称不能为空")
        return self


class ChapterUpdate(ChapterDefinition):
    version: int = Field(ge=1)


class ChapterVersion(BaseModel):
    version: int = Field(ge=1)


class ChapterPreview(BaseModel):
    start_date: date
    end_date: date | None = None
    chapter_id: UUID | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class ChapterMerge(ChapterDefinition):
    chapter_ids: list[UUID] = Field(min_length=2, max_length=10)
    versions: dict[UUID, int]


class ChapterSplit(BaseModel):
    split_date: date
    first_title: str = Field(min_length=1, max_length=80)
    second_title: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)
