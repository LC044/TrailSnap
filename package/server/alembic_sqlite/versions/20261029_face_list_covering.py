"""Cover face list counts without reading embedding rows."""
from alembic import op

revision = "face_lists_sqlite_0022"
down_revision = "e205c1a0b002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_faces_photo_identity", "faces", ["photo_id", "face_identity_id"])
    op.execute("ANALYZE ix_faces_photo_identity")


def downgrade():
    op.drop_index("ix_faces_photo_identity", table_name="faces")
