"""github import and requirement attachments

Revision ID: 34a8c51d92f0
Revises: 80c617bd95e3
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "34a8c51d92f0"
down_revision: Union[str, None] = "80c617bd95e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("log_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=16), nullable=False, server_default="platform"))
        batch_op.create_index("ix_requirements_source", ["source"], unique=False)
    op.create_table(
        "requirement_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index("ix_requirement_attachments_requirement_id", "requirement_attachments", ["requirement_id"])
    op.create_index("ix_requirement_attachments_uploaded_by", "requirement_attachments", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_requirement_attachments_uploaded_by", table_name="requirement_attachments")
    op.drop_index("ix_requirement_attachments_requirement_id", table_name="requirement_attachments")
    op.drop_table("requirement_attachments")
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_index("ix_requirements_source")
        batch_op.drop_column("source")
        batch_op.drop_column("log_text")
