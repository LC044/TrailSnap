"""Add idempotency key for mobile gallery backup.

Revision ID: b1f8d2e4a603
Revises: 6d9f2a4c8e17
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op


revision = "b1f8d2e4a603"
down_revision = "6d9f2a4c8e17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("backup_key", sa.String(length=255), nullable=True))
    # A unique index is supported by both PostgreSQL and the desktop SQLite
    # runtime, unlike ALTER TABLE ADD CONSTRAINT on SQLite.
    op.create_index("uq_photos_owner_backup_key", "photos", ["owner_id", "backup_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_photos_owner_backup_key", table_name="photos")
    op.drop_column("photos", "backup_key")
