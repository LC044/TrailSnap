"""Add persistent appearance clusters without rewriting existing face vectors."""
from alembic import op
import sqlalchemy as sa
from app.db.types import UUID, VECTOR

revision = "face_clusters_pg_0023"
down_revision = "face_lists_pg_0022"
branch_labels = None
depends_on = None


def _enqueue_initialization():
    """Persist one initialization request per legacy library in this migration."""
    import uuid

    bind = op.get_bind()
    photos = sa.table("photos", sa.column("id", UUID()),
                      sa.column("owner_id", UUID()), sa.column("is_deleted", sa.Boolean()))
    faces = sa.table("faces", sa.column("photo_id", UUID()), sa.column("is_deleted", sa.Boolean()))
    tasks = sa.table(
        "tasks", sa.column("id", UUID()), sa.column("owner_id", UUID()),
        sa.column("type", sa.String()), sa.column("status", sa.String()),
        sa.column("payload", sa.JSON()), sa.column("priority", sa.Integer()),
        sa.column("total_items", sa.Integer()), sa.column("processed_items", sa.Integer()),
        sa.column("attempt_count", sa.Integer()), sa.column("created_at", sa.DateTime()),
    )
    owners = bind.execute(sa.select(photos.c.owner_id).select_from(
        photos.join(faces, faces.c.photo_id == photos.c.id),
    ).where(photos.c.owner_id.isnot(None), photos.c.is_deleted.is_(False),
            faces.c.is_deleted.is_(False)).distinct()).scalars().all()
    for owner_id in owners:
        existing = bind.execute(sa.select(tasks.c.id, tasks.c.payload).where(
            tasks.c.owner_id == owner_id, tasks.c.type == "CLUSTER_FACES",
            tasks.c.status == "pending",
        ).order_by(tasks.c.created_at.desc(), tasks.c.id.desc()).limit(1)).first()
        payload = dict(existing.payload or {}) if existing else {}
        payload.update(owner_id=str(owner_id), auto=False)
        if existing:
            bind.execute(tasks.update().where(tasks.c.id == existing.id).values(payload=payload))
        else:
            bind.execute(tasks.insert().values(
                id=uuid.uuid4(), owner_id=owner_id, type="CLUSTER_FACES",
                status="pending", priority=6, payload=payload,
                total_items=0, processed_items=0, attempt_count=0,
            ))

def upgrade():
    op.create_table(
        "face_clusters",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("owner_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_id", UUID(), sa.ForeignKey("face_identities.id", ondelete="SET NULL")),
        sa.Column("center", VECTOR(512), nullable=False),
        sa.Column("vector_sum", VECTOR(512), nullable=False),
        sa.Column("anchor_face_id", sa.Integer(), sa.ForeignKey("faces.id", ondelete="SET NULL")),
        sa.Column("face_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_face_clusters_owner_identity", "face_clusters", ["owner_id", "identity_id", "id"])
    op.create_index("ix_face_clusters_owner_status", "face_clusters", ["owner_id", "status", "id"])
    op.add_column("faces", sa.Column("face_cluster_id", UUID(), nullable=True))
    op.create_foreign_key("fk_faces_cluster", "faces", "face_clusters", ["face_cluster_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_faces_cluster_photo", "faces", ["face_cluster_id", "photo_id"])
    op.create_index("ix_faces_unclustered", "faces", ["id", "photo_id"],
                    sqlite_where=sa.text("face_cluster_id IS NULL AND is_deleted = false AND face_feature IS NOT NULL"),
                    postgresql_where=sa.text("face_cluster_id IS NULL AND is_deleted = false AND face_feature IS NOT NULL"))
    _enqueue_initialization()


def downgrade():
    op.drop_index("ix_faces_unclustered", table_name="faces")
    op.drop_index("ix_faces_cluster_photo", table_name="faces")
    op.drop_constraint("fk_faces_cluster", "faces", type_="foreignkey")
    op.drop_column("faces", "face_cluster_id")
    op.drop_table("face_clusters")
