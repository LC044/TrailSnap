"""github oauth, mcp tokens and requirement soft delete

Revision ID: 7b4d1f6a20c1
Revises: e2a3b299195e
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b4d1f6a20c1"
down_revision: Union[str, None] = "e2a3b299195e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("delete_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key("fk_requirements_deleted_by_users", "users", ["deleted_by"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_requirements_deleted_at", ["deleted_at"], unique=False)

    op.create_table(
        "github_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("github_user_id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("user_id"), sa.UniqueConstraint("github_user_id"),
    )
    op.create_index("ix_github_identities_user_id", "github_identities", ["user_id"])
    op.create_index("ix_github_identities_github_user_id", "github_identities", ["github_user_id"])
    op.create_index("ix_github_identities_login", "github_identities", ["login"])

    op.create_table(
        "oauth_login_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_oauth_login_grants_code_hash", "oauth_login_grants", ["code_hash"])
    op.create_index("ix_oauth_login_grants_user_id", "oauth_login_grants", ["user_id"])

    op.create_table(
        "agent_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_agent_tokens_token_prefix", "agent_tokens", ["token_prefix"])
    op.create_index("ix_agent_tokens_token_hash", "agent_tokens", ["token_hash"])
    op.create_index("ix_agent_tokens_created_by", "agent_tokens", ["created_by"])


def downgrade() -> None:
    op.drop_table("agent_tokens")
    op.drop_table("oauth_login_grants")
    op.drop_table("github_identities")
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_index("ix_requirements_deleted_at")
        batch_op.drop_constraint("fk_requirements_deleted_by_users", type_="foreignkey")
        batch_op.drop_column("delete_reason")
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")
