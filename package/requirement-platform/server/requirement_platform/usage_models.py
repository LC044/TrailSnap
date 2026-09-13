"""cc-switch 用量数据模型：设备、导入批次、请求明细、日聚合、供应商名称映射。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UsageDevice(Base):
    """一台导出 cc-switch 备份的设备（label 由导入者填写，如"办公本"）。"""

    __tablename__ = "usage_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    last_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageImport(Base):
    """一次 SQL 备份文件的导入记录，file_sha256 全局去重。"""

    __tablename__ = "usage_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("usage_devices.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    file_size: Mapped[int] = mapped_column(Integer)
    user_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_rows: Mapped[int] = mapped_column(Integer, default=0)
    detail_new: Mapped[int] = mapped_column(Integer, default=0)
    detail_dup: Mapped[int] = mapped_column(Integer, default=0)
    detail_aged_out: Mapped[int] = mapped_column(Integer, default=0)
    rollup_rows: Mapped[int] = mapped_column(Integer, default=0)
    rollup_upserted: Mapped[int] = mapped_column(Integer, default=0)
    date_min: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_max: Mapped[str | None] = mapped_column(String(10), nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class UsageProvider(Base):
    """provider_id（各设备内的 UUID）→ 展示名称，跨设备按 (device, provider_id) 唯一。"""

    __tablename__ = "usage_providers"
    __table_args__ = (UniqueConstraint("device_id", "provider_id", name="uq_usage_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("usage_devices.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[str] = mapped_column(String(80), index=True)
    app_type: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)


class UsageRequestLog(Base):
    """请求级明细，request_id 为 cc-switch 全局唯一 ID（跨设备去重键）。"""

    __tablename__ = "usage_request_logs"
    __table_args__ = (
        Index("ix_usage_logs_device_created", "device_id", "created_at"),
        Index("ix_usage_logs_created_date", "created_date"),
        Index("ix_usage_logs_model", "model"),
    )

    request_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("usage_devices.id", ondelete="CASCADE"), index=True)
    import_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_id: Mapped[str] = mapped_column(String(80))
    app_type: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(120))
    request_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_read_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_creation_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_source: Mapped[str] = mapped_column(String(24), default="proxy")
    created_at: Mapped[int] = mapped_column(Integer)  # epoch 秒
    created_date: Mapped[str] = mapped_column(String(10))  # Asia/Shanghai 日期，与 rollup 对齐


class UsageDailyRollup(Base):
    """日聚合，同设备同键 upsert（新值 request_count 更大者胜）。"""

    __tablename__ = "usage_daily_rollups"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "date", "app_type", "provider_id", "model", "request_model", "pricing_model",
            name="uq_usage_rollup",
        ),
        Index("ix_usage_rollups_date", "date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("usage_devices.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String(10))
    app_type: Mapped[str] = mapped_column(String(24))
    provider_id: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    request_model: Mapped[str] = mapped_column(String(120), default="")
    pricing_model: Mapped[str] = mapped_column(String(120), default="")
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
