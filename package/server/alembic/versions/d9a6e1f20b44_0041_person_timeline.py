"""Add person story exclusions.

Revision ID: d9a6e1f20b44
Revises: c41a6d8e920f
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d9a6e1f20b44"
down_revision = "c41a6d8e920f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_timeline_hides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_person_timeline_hides_owner_id", "person_timeline_hides", ["owner_id"])
    op.create_index("ix_person_timeline_hides_scope", "person_timeline_hides", ["owner_id", "person_a_id", "person_b_id", "start_at", "end_at"])


def downgrade() -> None:
    op.drop_table("person_timeline_hides")
