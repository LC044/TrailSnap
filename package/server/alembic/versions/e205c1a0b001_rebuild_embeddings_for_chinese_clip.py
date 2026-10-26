"""rebuild embeddings for Chinese CLIP

Revision ID: e205c1a0b001
Revises: 3b51634972a4
Create Date: 2026-10-26 23:44:04.068804

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e205c1a0b001'
down_revision: Union[str, None] = '3b51634972a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from app.db.embedding_upgrade import queue_chinese_clip_rebuild
    queue_chinese_clip_rebuild(op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    from app.db.embedding_upgrade import remove_chinese_clip_rebuild
    remove_chinese_clip_rebuild(op.get_bind())
