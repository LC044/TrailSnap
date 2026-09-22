"""Add first-class memory events and associations (SQLite).

Revision ID: sqlite_0014
Revises: sqlite_0013
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0014"
down_revision = "sqlite_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("origin", sa.String(6), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("title_source", sa.String(16), nullable=False, server_default="system"),
        sa.Column("story", sa.Text()),
        sa.Column("story_source", sa.String(16), nullable=False, server_default="system"),
        sa.Column("cover_photo_id", sa.String(36), sa.ForeignKey("photos.id", ondelete="SET NULL")),
        sa.Column("cover_source", sa.String(16), nullable=False, server_default="system"),
        sa.Column("start_time", sa.DateTime()),
        sa.Column("end_time", sa.DateTime()),
        sa.Column("time_source", sa.String(16), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float()),
        sa.Column("algorithm_version", sa.String(32)),
        sa.Column("candidate_fingerprint", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("ignored_at", sa.DateTime()),
        sa.Column("story_generation_status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("story_generation_started_at", sa.DateTime()),
        sa.Column("story_generation_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime()),
        sa.UniqueConstraint("owner_id", "candidate_fingerprint", name="uq_memories_owner_fingerprint"),
    )
    for name, columns in (
        ("ix_memories_owner_id", ["owner_id"]),
        ("ix_memories_status", ["status"]),
        ("ix_memories_start_time", ["start_time"]),
        ("ix_memories_owner_status_start", ["owner_id", "status", "start_time"]),
        ("ix_memories_owner_updated", ["owner_id", "updated_at"]),
    ):
        op.create_index(name, "memories", columns)

    op.create_table(
        "memory_photos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("source", sa.String(24), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("memory_id", "photo_id", name="uq_memory_photo"),
    )
    op.create_index("ix_memory_photos_memory_id", "memory_photos", ["memory_id"])
    op.create_index("ix_memory_photos_photo_id", "memory_photos", ["photo_id"])

    op.create_table(
        "memory_people",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("face_identity_id", sa.String(36), sa.ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("memory_id", "face_identity_id", name="uq_memory_person"),
    )
    op.create_index("ix_memory_people_memory_id", "memory_people", ["memory_id"])

    op.create_table(
        "memory_places",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("scenes.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.String(24), nullable=False, server_default="city"),
        sa.Column("source", sa.String(24), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_memory_places_memory_id", "memory_places", ["memory_id"])

    op.create_table(
        "memory_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("memory_id", "ticket_type", "ticket_id", name="uq_memory_ticket"),
    )
    op.create_index("ix_memory_tickets_memory_id", "memory_tickets", ["memory_id"])

    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", sa.String(24), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_evidence_memory_id", "memory_evidence", ["memory_id"])

    op.create_table(
        "memory_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("memory_id", "related_memory_id", "relation_type", name="uq_memory_relation"),
    )
    op.create_index("ix_memory_relations_memory_id", "memory_relations", ["memory_id"])
    op.create_index("ix_memory_relations_related_memory_id", "memory_relations", ["related_memory_id"])


def downgrade() -> None:
    for table in (
        "memory_relations", "memory_evidence", "memory_tickets", "memory_places",
        "memory_people", "memory_photos", "memories",
    ):
        op.drop_table(table)
