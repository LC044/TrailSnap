"""add managed AI connections, models and task routes

Revision ID: e7a1b3d5f920
Revises: d6f8a2c4e910
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e7a1b3d5f920"
down_revision: Union[str, None] = "d6f8a2c4e910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("api_base", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_key_hint", sa.String(16), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_connections_enabled", "ai_connections", ["enabled"])
    op.create_table(
        "ai_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("ai_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("supports_json_mode", sa.Boolean(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "model_name", name="uq_ai_connection_model"),
    )
    op.create_index("ix_ai_models_connection_id", "ai_models", ["connection_id"])
    op.create_index("ix_ai_models_enabled", "ai_models", ["enabled"])
    op.create_table(
        "ai_task_routes",
        sa.Column("task_type", sa.String(80), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("model_ids", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_task_routes")
    op.drop_table("ai_models")
    op.drop_table("ai_connections")
