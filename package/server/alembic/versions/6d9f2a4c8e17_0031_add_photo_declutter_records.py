"""Add durable photo declutter decisions.

Revision ID: 6d9f2a4c8e17
Revises: f4b7c1d9e203
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

from app.db.types import UUID


revision = "6d9f2a4c8e17"
down_revision = "f4b7c1d9e203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_declutter_records",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("photo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('keep', 'delete')", name="ck_photo_declutter_decision"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "photo_id", name="uq_photo_declutter_owner_photo"),
    )
    op.create_index("ix_photo_declutter_records_owner_id", "photo_declutter_records", ["owner_id"])
    op.create_index("ix_photo_declutter_records_photo_id", "photo_declutter_records", ["photo_id"])
    op.create_index("ix_photo_declutter_owner_decision", "photo_declutter_records", ["owner_id", "decision"])


def downgrade() -> None:
    op.drop_table("photo_declutter_records")
