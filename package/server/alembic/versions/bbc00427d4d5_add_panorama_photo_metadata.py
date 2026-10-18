"""add panorama photo metadata

Revision ID: bbc00427d4d5
Revises: 4c8b8ca1eaac
Create Date: 2026-10-16 01:05:58.850762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbc00427d4d5'
down_revision: Union[str, None] = '4c8b8ca1eaac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("photos", sa.Column("panorama_projection", sa.String(32), nullable=True))
    op.add_column("photos", sa.Column("panorama_metadata", sa.JSON(), nullable=True))
    op.add_column("photos", sa.Column("panorama_detected", sa.JSON(), nullable=True))
    op.add_column("photos", sa.Column("panorama_override", sa.String(16), nullable=True))
    op.create_index("ix_photos_panorama_projection", "photos", ["panorama_projection"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_photos_panorama_projection", table_name="photos")
    with op.batch_alter_table("photos") as batch:
        for name in ("panorama_override", "panorama_detected", "panorama_metadata", "panorama_projection"):
            batch.drop_column(name)
