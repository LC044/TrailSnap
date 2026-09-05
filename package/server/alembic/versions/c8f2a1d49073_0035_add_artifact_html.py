"""Add personalized HTML to AI artifacts.

Revision ID: c8f2a1d49073
Revises: a7e4c9d2f601
"""

import sqlalchemy as sa
from alembic import op

revision = "c8f2a1d49073"
down_revision = "a7e4c9d2f601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_artifacts", sa.Column("html_content", sa.Text(), nullable=True))
    op.add_column("ai_artifacts", sa.Column("html_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("ai_artifacts", "html_config")
    op.drop_column("ai_artifacts", "html_content")
