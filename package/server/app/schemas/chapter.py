from datetime import date
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChapterDiaryEntry(BaseModel):
    title: str = Field(default="", max_length=80)
    body: str = Field(default="", max_length=1000)
    source: Literal["user", "ai"] = "user"
    source_photo_ids: list[UUID] = Field(default_factory=list, max_length=12)
    source_memory_ids: list[UUID] = Field(default_factory=list, max_length=8)


class ChapterDefinition(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=1000)
    summary_source: Literal["user", "ai"] = "user"
    diary_entries: dict[str, ChapterDiaryEntry] | None = Field(default=None, max_length=301)
    start_date: date
    end_date: date | None = None
    cover_photo_id: UUID | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if not self.title.strip():
            raise ValueError("章节名称不能为空")
        for year in self.diary_entries or {}:
            if not year.isdigit() or not 1900 <= int(year) <= 2200 or year != str(int(year)):
                raise ValueError("日记年份无效")
        return self


class ChapterUpdate(ChapterDefinition):
    version: int = Field(ge=1)


class ChapterVersion(BaseModel):
    version: int = Field(ge=1)


class ChapterDiaryGenerate(BaseModel):
    scope: Literal["introduction", "year"] = "introduction"
    year: int | None = Field(default=None, ge=1900, le=2200)
    version: int = Field(ge=1)
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def valid_scope(self):
        if self.scope == "year" and self.year is None:
            raise ValueError("请选择日记年份")
        return self


class ChapterDiaryDraft(ChapterDiaryEntry):
    scope: Literal["introduction", "year"]
    year: int | None = None
    version: int
    photo_count: int


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


class ChapterDayCaption(BaseModel):
    caption: str = Field(max_length=1000)
    source: Literal["ai", "manual"] = "manual"


class ChapterDayPhoto(BaseModel):
    id: UUID
    filename: str
    photo_time: str
    file_type: str
    width: int | None = None
    height: int | None = None


class ChapterDay(BaseModel):
    day: date
    photo_count: int
    photos: list[ChapterDayPhoto]
    caption: str
    source: Literal["ai", "manual"] | None = None
    needs_generation: bool
    people: list[dict]
    places: list[str]
    tags: list[str]
    events: list[dict]


class ChapterDays(BaseModel):
    items: list[ChapterDay]
    total: int
    skip: int
    limit: int
