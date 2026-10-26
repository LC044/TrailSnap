"""Data-only, frozen queue payload shared by the two embedding migrations."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID


TASK_ID = '205c1a0b-0001-4000-8000-000000000001'


def queue_chinese_clip_rebuild(connection):
    ids = PGUUID(as_uuid=False) if connection.dialect.name == 'postgresql' else sa.String(36)
    tasks = sa.table('tasks', sa.column('id', ids), sa.column('type', sa.String),
                     sa.column('status', sa.String), sa.column('priority', sa.Integer),
                     sa.column('payload', sa.JSON), sa.column('attempt_count', sa.Integer),
                     sa.column('total_items', sa.Integer), sa.column('processed_items', sa.Integer),
                     sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime))
    vectors = sa.table('image_vectors', sa.column('photo_id'))
    if connection.execute(sa.select(vectors.c.photo_id).limit(1)).first() is None:
        return
    if connection.execute(sa.select(tasks.c.id).where(tasks.c.id == TASK_ID)).first():
        return
    connection.execute(tasks.insert().values(
        id=TASK_ID, type='IMAGE_EMBEDDING', status='pending', priority=8,
        payload={'force': True, 'model': 'chinese-clip-ViT-B-16',
                 'source': 'chinese_clip_upgrade_v1'},
        attempt_count=0, total_items=0, processed_items=0,
        created_at=sa.func.now(), updated_at=sa.func.now(),
    ))


def remove_chinese_clip_rebuild(connection):
    ids = PGUUID(as_uuid=False) if connection.dialect.name == 'postgresql' else sa.String(36)
    tasks = sa.table('tasks', sa.column('id', ids), sa.column('status', sa.String))
    connection.execute(tasks.delete().where(tasks.c.id == TASK_ID, tasks.c.status == 'pending'))
