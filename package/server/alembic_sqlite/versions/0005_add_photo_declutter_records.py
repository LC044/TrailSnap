"""Add durable photo declutter decisions to SQLite.

Revision ID: sqlite_0005
Revises: sqlite_0004
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

from app.db.types import UUID


revision = "sqlite_0005"
down_revision = "sqlite_0004"
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
