import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Index
from sqlalchemy.sql import text
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class NotificationType(str, enum.Enum):
    """通知类型枚举。新增通知种类时在此追加，前端按 type 分组展示。"""
    TASK = "TASK"          # 任务相关（目前仅 live 推送，不落库；预留）
    UPDATE = "UPDATE"      # 版本更新通知
    SYSTEM = "SYSTEM"      # 系统公告


class NotificationLevel(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class Notification(Base):
    """全局通知记录。落库以便跨设备同步与历史查询。

    task.* 事件不写本表（避免进度刷屏），仅通过 NotificationManager 内存推送
    驱动前端刷新；UPDATE/SYSTEM 等离散通知才落库。
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type = Column(String(32), nullable=False, default=NotificationType.SYSTEM.value)
    level = Column(String(16), nullable=False, default=NotificationLevel.INFO.value)
    title = Column(String(255), nullable=False)
    body = Column(JSON, nullable=True)
    ref_type = Column(String(32), nullable=True)   # 关联资源类型，如 'release' / 'task'
    ref_id = Column(String(64), nullable=True)     # 关联资源 ID
    read = Column(Boolean, default=False, server_default=text('false'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_notif_user_read", "user_id", "read"),
        Index("ix_notif_user_created", "user_id", "created_at"),
    )
