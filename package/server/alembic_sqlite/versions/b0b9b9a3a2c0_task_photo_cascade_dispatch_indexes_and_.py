"""task photo cascade dispatch indexes and auto vacuum

Revision ID: b0b9b9a3a2c0
Revises: de268f1b37fe
Create Date: 2026-10-11 21:19:08.354903
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b0b9b9a3a2c0'
down_revision: Union[str, Sequence[str], None] = 'de268f1b37fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_photo_links() -> None:
    # Page by primary key, keeping migration memory bounded even for large
    # libraries. UUID normalization also supports legacy hex-only payload IDs.
    import uuid
    bind = op.get_bind()
    uuid_type = sa.CHAR(36) if bind.dialect.name == "sqlite" else sa.UUID()
    tasks = sa.table("tasks", sa.column("id", uuid_type),
                     sa.column("payload", sa.JSON()), sa.column("photo_id", uuid_type))
    photos = sa.table("photos", sa.column("id", uuid_type))
    last_id = None
    while True:
        query = sa.select(tasks.c.id, tasks.c.payload).order_by(tasks.c.id).limit(1000)
        if last_id is not None:
            query = query.where(tasks.c.id > last_id)
        rows = bind.execute(query).all()
        if not rows:
            break
        last_id = rows[-1].id
        links, invalid = [], []
        for task_id, payload in rows:
            value = payload.get("photo_id") if isinstance(payload, dict) else None
            if value is None:
                continue
            try:
                photo_id = uuid.UUID(str(value))
                if bind.dialect.name == "sqlite":
                    photo_id = str(photo_id)
                links.append((task_id, photo_id))
            except (ValueError, TypeError, AttributeError):
                invalid.append(task_id)
        existing = set(bind.execute(sa.select(photos.c.id).where(
            photos.c.id.in_([photo_id for _, photo_id in links]))).scalars()) if links else set()
        updates = [{"task_key": task_id, "photo_key": photo_id}
                   for task_id, photo_id in links if photo_id in existing]
        if updates:
            bind.execute(sa.update(tasks).where(tasks.c.id == sa.bindparam("task_key"))
                         .values(photo_id=sa.bindparam("photo_key")), updates)
        orphan_ids = invalid + [task_id for task_id, photo_id in links if photo_id not in existing]
        if orphan_ids:
            bind.execute(sa.delete(tasks).where(tasks.c.id.in_(orphan_ids)))


def _create_dispatch_indexes() -> None:
    op.drop_index("ix_tasks_status_priority_created", table_name="tasks")
    op.create_index("ix_tasks_status_priority_created", "tasks",
                    ["status", sa.text("priority DESC"), sa.text("created_at ASC")])
    op.create_index("ix_tasks_type_status_priority_created", "tasks",
                    ["type", "status", sa.text("priority DESC"), sa.text("created_at ASC")])
    op.create_index("ix_tasks_photo_id", "tasks", ["photo_id"])


def _drop_dispatch_indexes() -> None:
    op.drop_index("ix_tasks_photo_id", table_name="tasks")
    op.drop_index("ix_tasks_type_status_priority_created", table_name="tasks")
    op.drop_index("ix_tasks_status_priority_created", table_name="tasks")
    op.create_index("ix_tasks_status_priority_created", "tasks", ["status", "priority", "created_at"])


def upgrade() -> None:
    # SQLite supports adding a nullable REFERENCES column directly; this avoids
    # copying the entire tasks table merely to add a foreign key.
    op.execute("ALTER TABLE tasks ADD COLUMN photo_id CHAR(36) REFERENCES photos(id) ON DELETE CASCADE")
    _backfill_photo_links()
    _create_dispatch_indexes()
    # FULL takes effect on existing files only after VACUUM. Do this once, before
    # the desktop server starts accepting work, never inside a transaction.
    with op.get_context().autocommit_block():
        op.execute("PRAGMA auto_vacuum=FULL")
        op.execute("VACUUM")
        op.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def downgrade() -> None:
    _drop_dispatch_indexes()
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("photo_id")
    # Retain the safe file-maintenance mode on a schema downgrade.
