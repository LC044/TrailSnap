"""add railway station coordinates

Revision ID: railway_sqlite_0001
Revises:
Create Date: 2026-10-23 15:19:29.496554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'railway_sqlite_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('station')}
    if 'latitude' not in existing:
        op.add_column('station', sa.Column('latitude', sa.DECIMAL(precision=10, scale=7), nullable=True, comment='纬度，缺失时为空'))
    if 'longitude' not in existing:
        op.add_column('station', sa.Column('longitude', sa.DECIMAL(precision=10, scale=7), nullable=True, comment='经度，缺失时为空'))
    if 'coordinate_source' not in existing:
        op.add_column('station', sa.Column('coordinate_source', sa.String(length=32), nullable=True, comment='坐标来源：12306/tianditu/manual'))
    if 'coordinate_system' not in existing:
        op.add_column('station', sa.Column('coordinate_system', sa.String(length=16), nullable=True, comment='坐标参考系，未确认时为unknown'))
    if 'coordinates_updated_at' not in existing:
        op.add_column('station', sa.Column('coordinates_updated_at', sa.DateTime(timezone=True), nullable=True))
    if 'coordinate_status' not in existing:
        op.add_column('station', sa.Column('coordinate_status', sa.String(length=24), nullable=True, comment='坐标补齐状态'))
    if 'coordinate_lookup_at' not in existing:
        op.add_column('station', sa.Column('coordinate_lookup_at', sa.DateTime(timezone=True), nullable=True))
    if 'coordinate_retry_after' not in existing:
        op.add_column('station', sa.Column('coordinate_retry_after', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('station')}
    if 'coordinate_retry_after' in existing:
        op.drop_column('station', 'coordinate_retry_after')
    if 'coordinate_lookup_at' in existing:
        op.drop_column('station', 'coordinate_lookup_at')
    if 'coordinate_status' in existing:
        op.drop_column('station', 'coordinate_status')
    if 'coordinates_updated_at' in existing:
        op.drop_column('station', 'coordinates_updated_at')
    if 'coordinate_system' in existing:
        op.drop_column('station', 'coordinate_system')
    if 'coordinate_source' in existing:
        op.drop_column('station', 'coordinate_source')
    if 'longitude' in existing:
        op.drop_column('station', 'longitude')
    if 'latitude' in existing:
        op.drop_column('station', 'latitude')
