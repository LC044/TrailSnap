"""Add owner-scoped life chapters.

Revision ID: a7c133000001
Revises: 5d30ac3c5d2a
"""

from alembic import op
import sqlalchemy as sa
from app.db.types import UUID

revision = "a7c133000001"
down_revision = "5d30ac3c5d2a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "life_chapters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("cover_photo_id", UUID(as_uuid=True), sa.ForeignKey("photos.id", ondelete="SET NULL")),
        sa.Column("candidate_fingerprint", sa.String(64)),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
        sa.UniqueConstraint("owner_id", "candidate_fingerprint", name="uq_life_chapter_candidate"),
    )
    op.create_index("ix_life_chapters_owner_id", "life_chapters", ["owner_id"])
    op.create_index("ix_life_chapters_owner_status_start", "life_chapters", ["owner_id", "status", "start_date"])


def downgrade():
    op.drop_index("ix_life_chapters_owner_status_start", table_name="life_chapters")
    op.drop_index("ix_life_chapters_owner_id", table_name="life_chapters")
    op.drop_table("life_chapters")
