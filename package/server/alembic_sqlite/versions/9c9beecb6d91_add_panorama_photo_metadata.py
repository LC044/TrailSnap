"""add panorama photo metadata

Revision ID: 9c9beecb6d91
Revises: b0b9b9a3a2c0
Create Date: 2026-10-16 01:06:00.218047
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c9beecb6d91'
down_revision: Union[str, Sequence[str], None] = 'b0b9b9a3a2c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("panorama_projection", sa.String(32), nullable=True))
    op.add_column("photos", sa.Column("panorama_metadata", sa.JSON(), nullable=True))
    op.add_column("photos", sa.Column("panorama_detected", sa.JSON(), nullable=True))
    op.add_column("photos", sa.Column("panorama_override", sa.String(16), nullable=True))
    op.create_index("ix_photos_panorama_projection", "photos", ["panorama_projection"])


def downgrade() -> None:
    op.drop_index("ix_photos_panorama_projection", table_name="photos")
    with op.batch_alter_table("photos") as batch:
        for name in ("panorama_override", "panorama_detected", "panorama_metadata", "panorama_projection"):
            batch.drop_column(name)
