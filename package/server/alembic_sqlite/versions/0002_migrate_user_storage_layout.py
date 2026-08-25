"""Migrate the legacy mixed user storage layout for SQLite.

Revision ID: sqlite_0002
Revises: sqlite_0001
Create Date: 2026-08-25 00:00:00.000000
"""

from alembic import op

from app.service.migrations.user_storage_v1 import run


revision = "sqlite_0002"
down_revision = "sqlite_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run(op.get_bind())


def downgrade() -> None:
    # See the PostgreSQL revision: coalescing isolated user directories is not
    # safe to automate and database downgrade does not require it.
    pass
