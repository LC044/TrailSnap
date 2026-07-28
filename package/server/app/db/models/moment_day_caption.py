from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base


class MomentDayCaption(Base):
    """朋友圈视图 · 按日聚合的文案。

    - `user_id + scope_type + scope_id + day` 唯一，为未来拓展到相册维度预留 scope。
    - MVP 阶段服务端只写 `scope_type='all'`, `scope_id=NULL`。
    - `source`: 'ai' 表示 AI 直出未改动；'manual' 表示用户手动编辑/输入。
    - `photo_count`: 生成时用于组素材的照片数，只用于展示与 debug。
    """

    __tablename__ = "moment_day_captions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(16), nullable=False, default="all", server_default="all")
    scope_id = Column(String(64), nullable=True)
    day = Column(Date, nullable=False, index=True)
    caption = Column(Text, nullable=False)
    source = Column(String(16), nullable=False, default="ai", server_default="ai")
    model_name = Column(String(64), nullable=True)
    photo_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "scope_type", "scope_id", "day", name="uq_moment_day_caption_user_scope_day"),
    )
