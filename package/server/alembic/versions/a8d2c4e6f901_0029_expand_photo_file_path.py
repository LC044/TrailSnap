"""Expand photo file paths and replace the unsafe B-tree index.

Revision ID: a8d2c4e6f901
Revises: 7c4e2a9f6b18
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a8d2c4e6f901"
down_revision: Union[str, None] = "7c4e2a9f6b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_photos_file_path", table_name="photos")
    op.alter_column(
        "photos",
        "file_path",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.create_index(
        "ix_photos_file_path",
        "photos",
        ["file_path"],
        unique=False,
        postgresql_using="hash",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM photos WHERE length(file_path) > 255 LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade: photos.file_path contains values longer than 255 characters")
    op.drop_index("ix_photos_file_path", table_name="photos")
    op.alter_column(
        "photos",
        "file_path",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.create_index("ix_photos_file_path", "photos", ["file_path"], unique=False)
