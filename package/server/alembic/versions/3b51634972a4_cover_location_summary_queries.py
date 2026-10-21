"""optimize photo lists, task statistics and location summaries

Revision ID: 3b51634972a4
Revises: portable_0020
Create Date: 2026-10-20 21:31:52.603194

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b51634972a4'
down_revision: Union[str, None] = 'portable_0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intermediate local builds already created some of these indexes.
    op.create_index('ix_photos_owner_deleted_time_id', 'photos',
                    ['owner_id', 'is_deleted', 'photo_time', 'id'], if_not_exists=True)
    op.create_index('ix_tasks_pending_error_type', 'tasks', ['type', 'status'],
                    postgresql_where=sa.text("status = 'pending' AND error IS NOT NULL"), if_not_exists=True)
    op.create_index('ix_photo_metadata_location_summary', 'photo_metadata',
                    ['photo_id', 'province', 'city', 'district', 'country',
                     'scene_id', 'latitude', 'longitude'], if_not_exists=True)


def downgrade() -> None:
    op.drop_index('ix_photo_metadata_location_summary', table_name='photo_metadata')
    op.drop_index('ix_tasks_pending_error_type', table_name='tasks')
    op.drop_index('ix_photos_owner_deleted_time_id', table_name='photos')
