"""public requirement numbers and guest submissions

Revision ID: 9c73e1ab420d
Revises: 34a8c51d92f0
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9c73e1ab420d"
down_revision: Union[str, None] = "34a8c51d92f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("public_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("submitter_name", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("submitter_contact", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("anonymous_upload_token_hash", sa.String(length=64), nullable=True))
        batch_op.alter_column("created_by", existing_type=sa.String(length=36), nullable=True)

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM requirements ORDER BY created_at, id")).fetchall()
    for number, row in enumerate(rows, start=1):
        connection.execute(
            sa.text("UPDATE requirements SET public_number = :number WHERE id = :id"),
            {"number": number, "id": row[0]},
        )
    op.create_index("ix_requirements_public_number", "requirements", ["public_number"], unique=True)

    with op.batch_alter_table("requirement_attachments") as batch_op:
        batch_op.alter_column("uploaded_by", existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("requirement_attachments") as batch_op:
        batch_op.alter_column("uploaded_by", existing_type=sa.String(length=36), nullable=False)
    op.drop_index("ix_requirements_public_number", table_name="requirements")
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.alter_column("created_by", existing_type=sa.String(length=36), nullable=False)
        batch_op.drop_column("anonymous_upload_token_hash")
        batch_op.drop_column("submitter_contact")
        batch_op.drop_column("submitter_name")
        batch_op.drop_column("public_number")
