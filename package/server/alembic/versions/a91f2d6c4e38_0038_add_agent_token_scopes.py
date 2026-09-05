"""Add least-privilege scopes to Agent Tokens.

Revision ID: a91f2d6c4e38
Revises: f32ad910c441
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "a91f2d6c4e38"
down_revision = "f32ad910c441"
branch_labels = None
depends_on = None

DEFAULT_READ_SCOPES = ["photos:read", "albums:read", "people:read"]


def upgrade() -> None:
    op.add_column(
        "agent_tokens",
        sa.Column(
            "scopes",
            sa.JSON(),
            server_default=sa.text(f"'{json.dumps(DEFAULT_READ_SCOPES)}'::json"),
            nullable=False,
        ),
    )
    op.alter_column("agent_tokens", "scopes", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_tokens", "scopes")
