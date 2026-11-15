"""Frozen, data-only queue operations for the first CLIP classification upgrade."""

from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


SOURCE = "clip_classification_upgrade_v1"
NAMESPACE = UUID("f86c6ab0-f197-455e-a0ba-b6e2c7d67ba4")


def queue_clip_classification(connection):
    ids = PGUUID(as_uuid=False) if connection.dialect.name == "postgresql" else sa.String(36)
    photos = sa.table("photos", sa.column("owner_id", ids),
                      sa.column("is_deleted", sa.Boolean), sa.column("file_type", sa.String))
    tasks = sa.table("tasks", sa.column("id", ids), sa.column("owner_id", ids),
                     sa.column("type", sa.String), sa.column("status", sa.String),
                     sa.column("priority", sa.Integer), sa.column("payload", sa.JSON),
                     sa.column("attempt_count", sa.Integer), sa.column("total_items", sa.Integer),
                     sa.column("processed_items", sa.Integer), sa.column("created_at", sa.DateTime),
                     sa.column("updated_at", sa.DateTime))
    owners = connection.execute(sa.select(photos.c.owner_id).where(
        photos.c.is_deleted.is_(False), photos.c.file_type != "video",
        photos.c.owner_id.is_not(None)).distinct()).scalars().all()
    for owner_id in owners:
        task_id = str(uuid5(NAMESPACE, str(owner_id)))
        insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
        connection.execute(insert(tasks).values(
            id=task_id, owner_id=str(owner_id), type="CLASSIFY_IMAGE_CLIP", status="pending",
            priority=8, payload={"source": SOURCE, "wait_for_embeddings": True},
            attempt_count=0, total_items=0, processed_items=0,
            created_at=sa.func.now(), updated_at=sa.func.now()).on_conflict_do_nothing(index_elements=["id"]))


def remove_clip_classification(connection):
    tasks = sa.table("tasks", sa.column("type", sa.String), sa.column("status", sa.String),
                     sa.column("payload", sa.JSON))
    connection.execute(tasks.delete().where(
        tasks.c.type == "CLASSIFY_IMAGE_CLIP", tasks.c.status == "pending",
        tasks.c.payload["source"].as_string() == SOURCE))
