"""Validated inputs for scoped, preview-first toolbox operations."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MediaScope(BaseModel):
    source: Literal["albums", "folders", "filter", "selected", "all"]
    album_ids: list[UUID] = Field(default_factory=list, max_length=100)
    folders: list[str] = Field(default_factory=list, max_length=100)
    include_children: bool = True
    photo_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    excluded_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    start_date: date | None = None
    end_date: date | None = None
    upload_time_fallback: bool = False
    media_type: Literal["image", "video", "all"] = "image"

    @model_validator(mode="after")
    def validate_source(self):
        required = {"albums": self.album_ids, "folders": self.folders, "selected": self.photo_ids}
        if self.source in required and not required[self.source]:
            raise ValueError("请明确选择处理范围")
        if self.source == "filter" and not self.start_date and not self.end_date:
            raise ValueError("条件筛选至少需要指定日期")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class OrganizeRule(BaseModel):
    strategy: Literal["time", "location", "person", "category"] = "time"
    granularity: Literal["year", "month", "day", "province", "city", "district",
                         "province_city", "city_district", "province_city_district"] = "month"
    nested: bool = True
    groups: list[str] | None = None

    @model_validator(mode="after")
    def validate_rule(self):
        if self.groups == []:
            raise ValueError("指定分组至少需要选择一项")
        if self.strategy == "time" and self.granularity not in {"year", "month", "day"}:
            raise ValueError("日期粒度无效")
        if self.strategy == "location" and self.granularity in {"year", "month", "day"}:
            raise ValueError("地点粒度无效")
        return self


class ToolConfig(BaseModel):
    kind: Literal["organize", "rename", "album", "cleanup", "metadata"]
    action: Literal["move", "copy"] | None = None
    target: str = ""
    layout: Literal["rebuild", "preserve"] = "rebuild"
    rules: list[OrganizeRule] = Field(default_factory=lambda: [OrganizeRule()], min_length=1, max_length=3)
    missing: Literal["skip", "placeholder", "upload"] = "skip"
    multi_group: Literal["skip", "first", "all"] = "skip"
    template: str = Field(default="IMG_{date}_{time}", min_length=1, max_length=240)
    start_index: int = Field(default=1, ge=1, le=1000000)
    reset_index: bool = False
    descending: bool = False
    album_prefix: str = Field(default="", max_length=40)
    cleanup_mode: Literal["duplicate", "similar", "quality"] = "duplicate"
    compare_all: bool = False
    similarity: float = Field(default=0.95, ge=0.8, le=1)
    quality_max: float = Field(default=40, ge=0, le=200)
    time_mode: Literal["none", "auto", "custom"] = "auto"
    custom_time: str | None = None
    make: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    only_missing_metadata: bool = True

    @model_validator(mode="after")
    def validate_operation(self):
        if self.kind == "organize" and (not self.target or not self.action):
            raise ValueError("请选择目标目录和移动/复制方式")
        if self.multi_group == "all" and self.kind == "organize" and self.action != "copy":
            raise ValueError("多个分组分别生成文件仅支持复制")
        if self.kind == "metadata":
            if self.time_mode == "none" and not self.make and not self.model:
                raise ValueError("请至少设置一项拍摄信息")
            if self.time_mode == "custom":
                from datetime import datetime
                if not self.custom_time:
                    raise ValueError("请选择指定时间")
                datetime.fromisoformat(self.custom_time)
        return self


class PlanRequest(BaseModel):
    scope: MediaScope
    config: ToolConfig


class ExecuteRequest(BaseModel):
    version: int
    confirmed: bool = False
    selected_items: list[int] | None = Field(default=None, max_length=10000)


class ToolPreset(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=30)
    config: ToolConfig


class ToolboxPreferences(BaseModel):
    version: int = 0
    presets: list[ToolPreset] = Field(default_factory=list, max_length=20)
    default_rename_id: str | None = None
    recent: list[ToolConfig] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_presets(self):
        if len({p.id for p in self.presets}) != len(self.presets):
            raise ValueError("模板标识重复")
        if len({p.name for p in self.presets}) != len(self.presets):
            raise ValueError("模板名称重复")
        if self.default_rename_id and not any(
            p.id == self.default_rename_id and p.config.kind == "rename" for p in self.presets
        ):
            raise ValueError("默认命名模板不存在")
        return self
