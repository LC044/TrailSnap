"""toolbox preview plans

Revision ID: toolbox_sqlite_0024
Revises: face_clusters_sqlite_0023
Create Date: 2026-11-06 22:19:12.537824
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'toolbox_sqlite_0024'
down_revision: Union[str, Sequence[str], None] = 'face_clusters_sqlite_0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "toolbox_plans",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("owner_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("task_id", sa.CHAR(36), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
    )
    op.create_index("ix_toolbox_plans_owner_created", "toolbox_plans", ["owner_id", "created_at"])
    op.create_table(
        "toolbox_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.CHAR(36), sa.ForeignKey("toolbox_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("photo_id", sa.CHAR(36), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.JSON(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    op.create_index("ix_toolbox_items_plan_status", "toolbox_plan_items", ["plan_id", "status", "id"])
    op.create_index("ix_toolbox_items_photo", "toolbox_plan_items", ["photo_id"])


def downgrade() -> None:
    op.drop_table("toolbox_plan_items")
    op.drop_table("toolbox_plans")
