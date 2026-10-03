"""Validated inputs for daily-frame operations."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CalendarSettings(BaseModel):
    timezone: str = Field(min_length=1, max_length=80)


class FrameSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_id: UUID
    mode: Literal["still", "motion"] = "still"
    start_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    caption: str = Field(default="", max_length=30)
    version: int = Field(default=0, ge=0)

    @field_validator("caption")
    @classmethod
    def one_line(cls, value: str) -> str:
        return " ".join(value.split())


class FrameVersion(BaseModel):
    version: int = Field(ge=1)


class BatchSelection(FrameSelection):
    day: date


class BatchFill(BaseModel):
    items: list[BatchSelection] = Field(min_length=1, max_length=31)


class FilmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    title: str = Field(default="一日一帧", min_length=1, max_length=40)
    orientation: Literal["portrait", "landscape"] = "portrait"
    fit: Literal["contain", "cover"] = "contain"
    show_date: bool = True
    show_caption: bool = True
    background: str = "#111827"
    skip_invalid: bool = False

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写影片标题")
        return value

    @field_validator("background")
    @classmethod
    def valid_color(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("背景必须是六位十六进制颜色")
        return value.lower()


class FilmCreate(FilmSettings):
    fingerprint: str = Field(min_length=64, max_length=64)
    is_preview: bool = False
