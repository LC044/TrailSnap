"""optimize photo lists, task statistics and location summaries

Revision ID: b54833411649
Revises: portable_sqlite_0020
Create Date: 2026-10-20 21:31:52.437166
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b54833411649'
down_revision: Union[str, Sequence[str], None] = 'portable_sqlite_0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_photos_owner_deleted_time_id', 'photos',
                    ['owner_id', 'is_deleted', 'photo_time', 'id'], if_not_exists=True)
    op.create_index('ix_tasks_pending_error_type', 'tasks', ['type', 'status'],
                    sqlite_where=sa.text("status = 'pending' AND error IS NOT NULL"), if_not_exists=True)
    op.create_index('ix_photo_metadata_location_summary', 'photo_metadata',
                    ['photo_id', 'province', 'city', 'district', 'country',
                     'scene_id', 'latitude', 'longitude'], if_not_exists=True)
    for index in ('ix_photos_owner_deleted_time_id', 'ix_tasks_type_status',
                  'ix_tasks_type_status_priority_created', 'ix_tasks_status_priority_created',
                  'ix_tasks_pending_error_type', 'ix_photo_metadata_location_summary'):
        op.execute(f'ANALYZE {index}')


def downgrade() -> None:
    op.drop_index('ix_photo_metadata_location_summary', table_name='photo_metadata')
    op.drop_index('ix_tasks_pending_error_type', table_name='tasks')
    op.drop_index('ix_photos_owner_deleted_time_id', table_name='photos')
