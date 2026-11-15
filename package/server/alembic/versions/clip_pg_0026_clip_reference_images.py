"""clip_reference_images

Revision ID: clip_pg_0026
Revises: clip_pg_0025
Create Date: 2026-11-15 19:00:48.702481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'clip_pg_0026'
down_revision: Union[str, None] = 'clip_pg_0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clip_rule_revisions', sa.Column('reference_images', sa.JSON(),
                  server_default='[]', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clip_rule_revisions', 'reference_images')
