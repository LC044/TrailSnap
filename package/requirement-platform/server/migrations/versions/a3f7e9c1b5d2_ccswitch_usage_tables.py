"""cc-switch usage tables

Revision ID: a3f7e9c1b5d2
Revises: c4d8a91e7b32
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3f7e9c1b5d2"
down_revision: Union[str, None] = "c4d8a91e7b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_import_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_usage_devices_label", "usage_devices", ["label"], unique=True)

    op.create_table(
        "usage_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("usage_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("user_version", sa.Integer(), nullable=True),
        sa.Column("detail_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail_dup", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail_aged_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rollup_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rollup_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_min", sa.String(10), nullable=True),
        sa.Column("date_max", sa.String(10), nullable=True),
        sa.Column("imported_by", sa.String(36), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_usage_imports_device_id", "usage_imports", ["device_id"])
    op.create_index("ix_usage_imports_file_sha256", "usage_imports", ["file_sha256"], unique=True)

    op.create_table(
        "usage_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("usage_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("app_type", sa.String(24), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=True),
        sa.UniqueConstraint("device_id", "provider_id", name="uq_usage_provider"),
    )
    op.create_index("ix_usage_providers_device_id", "usage_providers", ["device_id"])
    op.create_index("ix_usage_providers_provider_id", "usage_providers", ["provider_id"])

    op.create_table(
        "usage_request_logs",
        sa.Column("request_id", sa.String(120), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("usage_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_id", sa.String(36), nullable=True),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("app_type", sa.String(24), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("request_model", sa.String(120), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("output_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_read_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_creation_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("data_source", sa.String(24), nullable=False, server_default="proxy"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("created_date", sa.String(10), nullable=False),
    )
    op.create_index("ix_usage_logs_device_created", "usage_request_logs", ["device_id", "created_at"])
    op.create_index("ix_usage_logs_created_date", "usage_request_logs", ["created_date"])
    op.create_index("ix_usage_logs_device_id", "usage_request_logs", ["device_id"])
    op.create_index("ix_usage_logs_model", "usage_request_logs", ["model"])

    op.create_table(
        "usage_daily_rollups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("usage_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("app_type", sa.String(24), nullable=False),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("request_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("pricing_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "device_id", "date", "app_type", "provider_id", "model", "request_model", "pricing_model",
            name="uq_usage_rollup",
        ),
    )
    op.create_index("ix_usage_rollups_date", "usage_daily_rollups", ["date"])
    op.create_index("ix_usage_rollups_device_id", "usage_daily_rollups", ["device_id"])


def downgrade() -> None:
    op.drop_table("usage_daily_rollups")
    op.drop_table("usage_request_logs")
    op.drop_table("usage_providers")
    op.drop_table("usage_imports")
    op.drop_table("usage_devices")
