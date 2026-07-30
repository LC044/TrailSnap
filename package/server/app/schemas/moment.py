from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MomentDayCaption(BaseModel):
    """朋友圈日文案响应模型。"""

    id: int
    user_id: UUID
    scope_type: str = "all"
    scope_id: Optional[str] = None
    day: date
    caption: str
    source: str = "ai"
    model_name: Optional[str] = None
    photo_count: int = 0
    # 预留评论能力（本期只读取，不接受写入；写入由未来评论 API 维护）
    comment_count: int = 0
    last_commented_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MomentDayCaptionUpsert(BaseModel):
    """用户手动保存/编辑文案的请求体。"""

    caption: str = Field(..., min_length=1, max_length=1000)


class MomentDayCaptionGenerateRequest(BaseModel):
    """请求 AI 生成某日文案。"""

    day: date = Field(..., description="用户本地时区下的日期，格式 YYYY-MM-DD")
    timezone: str = Field(default="UTC", description="IANA 时区名，例如 Asia/Shanghai")
    scope_type: str = Field(default="all")
    scope_id: Optional[str] = Field(default=None)
    style: Optional[str] = Field(default=None, description="可选文案风格：日常/幽默/诗意/自嘲 等")
    force: bool = Field(default=False, description="即使已有文案也重新生成")
    stream: bool = Field(default=True, description="是否走 SSE 流式返回")
    connection_id: Optional[str] = None
    model_name: Optional[str] = None


class MomentDayLocationItem(BaseModel):
    """朋友圈日位置里的单个位置条目。"""

    name: str
    level: str = Field(default="unknown", description="scene / city / district / province")
    count: int = 0


class MomentDayLocations(BaseModel):
    """按天聚合的位置数据（不落库，实时从 photo_metadata 计算）。"""

    day: date
    primary: str = Field(..., description="首选展示的位置名，等于 locations[0].name")
    level: str = Field(default="unknown")
    locations: List[MomentDayLocationItem] = Field(default_factory=list)


class MomentHighlightPhoto(BaseModel):
    """朋友圈精选中的单张照片（只暴露前端渲染需要的最小字段）。"""

    id: UUID
    photo_time: Optional[datetime] = None
    score: float = 0.0
    group_size: int = Field(
        default=1,
        description="该精选照片所代表的 burst 组内实际照片总数（含被去重掉的），供 UI 提示",
    )

    class Config:
        from_attributes = True


class MomentDayHighlights(BaseModel):
    """按天聚合的朋友圈精选照片（实时计算不落库）。``photos`` 顺序即展示顺序。"""

    day: date
    photos: List[MomentHighlightPhoto] = Field(default_factory=list)
    total_candidates: int = Field(
        default=0,
        description="参与精选池的候选总数（不含视频/未 embedding 的照片）",
    )
