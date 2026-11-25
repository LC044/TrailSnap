"""Resumable cleanup of media indexed under a detached external directory."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud.album import trigger_conditional_albums_update, update_album_photo_counts
from app.crud.photo import DELETE_CHUNK_SIZE, _remove_photo_files, delete_photo_chunk
from app.db.models.index_log import IndexLog
from app.db.models.photo import Photo
from app.db.models.task import Task, TaskStatus, TaskType
from app.service.gallery_sync import (
    cancel_path_tasks,
    contains_key,
    ensure_removable,
    external_roots,
    lock_user,
    managed_roots,
    path_key,
)
from app.service.task_runtime import run_in_executor_owned
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory


def clean_thumbnails(owner_id, photo_ids):
    _remove_photo_files(owner_id, [(None, UUID(str(photo_id)), False, False) for photo_id in photo_ids])


def cleanup_gallery(db: Session, task_id: UUID) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        return {}
    owner_id, root = task.owner_id, task.payload['path']
    saved = task.result or {}
    album_ids = set(saved.get('album_ids', []))
    pending_thumbnails = saved.get('thumbnail_ids', [])

    def is_under_root(path: str | None) -> bool:
        return bool(path) and contains_key(root, path_key(path))

    def lock_cleanup():
        user = lock_user(db, owner_id)
        current = db.query(Task).populate_existing().filter(Task.id == task_id).with_for_update().one_or_none()
        if current is None or current.status != TaskStatus.PROCESSING:
            db.rollback()
            return None
        ensure_removable(root, external_roots(user) + managed_roots(user))
        return current

    if not lock_cleanup():
        return {}
    cancel_path_tasks(db, owner_id, is_under_root)
    db.commit()
    clean_thumbnails(owner_id, pending_thumbnails)

    photo_paths = dict(db.query(Photo.id, Photo.file_path).filter(Photo.owner_id == owner_id).all())
    db.commit()
    photo_ids = [photo_id for photo_id, path in photo_paths.items() if is_under_root(path)]

    task = lock_cleanup()
    if not task:
        return {}
    task.total_items = (task.processed_items or 0) + len(photo_ids)
    db.commit()

    for offset in range(0, len(photo_ids), DELETE_CHUNK_SIZE):
        task = lock_cleanup()
        if not task:
            return {}
        rows = db.query(Photo.id, Photo.file_path).filter(
            Photo.owner_id == owner_id, Photo.id.in_(photo_ids[offset:offset + DELETE_CHUNK_SIZE])
        ).with_for_update().all()
        rows = [(photo_id, path) for photo_id, path in rows
                if path == photo_paths[photo_id] or is_under_root(path)]
        if not rows:
            db.commit()
            continue
        batch_ids = [photo_id for photo_id, _ in rows]
        album_ids.update(str(album_id) for album_id in delete_photo_chunk(db, batch_ids))
        db.add_all(IndexLog(action='deleted', file_path=path, photo_id=photo_id, owner_id=owner_id)
                   for photo_id, path in rows)
        task.processed_items = (task.processed_items or 0) + len(batch_ids)
        task.result = {'album_ids': sorted(album_ids), 'thumbnail_ids': [str(photo_id) for photo_id in batch_ids]}
        db.commit()
        clean_thumbnails(owner_id, batch_ids)

    task = lock_cleanup()
    if not task:
        return {}
    deleted = task.processed_items or 0
    task.total_items = deleted
    update_album_photo_counts(db, [UUID(album_id) for album_id in album_ids])
    trigger_conditional_albums_update(db, owner_id, [])
    db.commit()
    return {'deleted_photos': deleted}


def run_gallery_removal(bind, task_id: UUID) -> dict:
    if bind.dialect.name != 'sqlite':
        with Session(bind) as db:
            return cleanup_gallery(db, task_id)

    # Hold one connection across commits so the cache is warm across batches.
    with bind.connect() as connection:
        previous_size = connection.exec_driver_sql('PRAGMA cache_size').scalar_one()
        try:
            connection.exec_driver_sql('PRAGMA cache_size=-65536')
            connection.commit()
            with Session(connection) as db:
                return cleanup_gallery(db, task_id)
        finally:
            try:
                connection.rollback()
                connection.exec_driver_sql(f'PRAGMA cache_size={int(previous_size)}')
                connection.exec_driver_sql('PRAGMA shrink_memory')
            except Exception:
                connection.invalidate()
                raise


@TaskStrategyFactory.register(TaskType.REMOVE_GALLERY)
class GalleryRemovalStrategy(BaseTaskStrategy):
    @property
    def resource_key(self) -> str:
        return 'gallery_removal'

    @property
    def timeout(self) -> int:
        return 24 * 60 * 60

    async def process(self, worker, task: Task, db: Session):
        return await run_in_executor_owned(None, run_gallery_removal, db.get_bind(), task.id)
