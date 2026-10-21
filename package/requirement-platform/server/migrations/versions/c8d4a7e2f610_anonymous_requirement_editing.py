"""Add independent anonymous editing and retry receipts."""
from alembic import op
import sqlalchemy as sa

revision = "c8d4a7e2f610"
down_revision = "1f6c9a2d4e70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirement_supplements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requirement_supplements_requirement_id", "requirement_supplements", ["requirement_id"])
    with op.batch_alter_table("requirements") as batch:
        batch.add_column(sa.Column("anonymous_edit_token_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("anonymous_submission_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("anonymous_creation_token_hash", sa.String(64), nullable=True))
        batch.create_unique_constraint("uq_requirements_anonymous_edit_token", ["anonymous_edit_token_hash"])
        batch.create_unique_constraint("uq_requirements_anonymous_creation_token", ["anonymous_creation_token_hash"])
    with op.batch_alter_table("requirement_revisions") as batch:
        batch.alter_column("editor_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM requirement_revisions WHERE editor_id IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade while anonymous revision history exists; preserve or archive it first.")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM requirement_supplements")).scalar():
        raise RuntimeError("Cannot downgrade while supplement history exists; preserve or archive it first.")
    op.drop_table("requirement_supplements")
    with op.batch_alter_table("requirement_revisions") as batch:
        batch.alter_column("editor_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("requirements") as batch:
        batch.drop_constraint("uq_requirements_anonymous_edit_token", type_="unique")
        batch.drop_constraint("uq_requirements_anonymous_creation_token", type_="unique")
        batch.drop_column("anonymous_creation_token_hash")
        batch.drop_column("anonymous_submission_hash")
        batch.drop_column("anonymous_edit_token_hash")
