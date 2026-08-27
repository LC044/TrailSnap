"""Store full photo paths as TEXT while retaining the SQLite lookup index."""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0003"
down_revision = "sqlite_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_photos_file_path", table_name="photos")
    with op.batch_alter_table("photos") as batch_op:
        batch_op.alter_column(
            "file_path",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=False,
        )
    op.create_index("ix_photos_file_path", "photos", ["file_path"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM photos WHERE length(file_path) > 255 LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade: photos.file_path contains values longer than 255 characters")
    op.drop_index("ix_photos_file_path", table_name="photos")
    with op.batch_alter_table("photos") as batch_op:
        batch_op.alter_column(
            "file_path",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=False,
        )
    op.create_index("ix_photos_file_path", "photos", ["file_path"], unique=False)
