"""Add mobile backup idempotency key to SQLite.

Revision ID: sqlite_0006
Revises: sqlite_0005
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0006"
down_revision = "sqlite_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("backup_key", sa.String(length=255), nullable=True))
    op.create_index("uq_photos_owner_backup_key", "photos", ["owner_id", "backup_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_photos_owner_backup_key", table_name="photos")
    op.drop_column("photos", "backup_key")
