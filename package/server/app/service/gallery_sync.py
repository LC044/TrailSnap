"""Database boundaries shared by gallery removal, scanning and import completion."""
from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Callable, Iterable
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session

from app.db.models.photo import Photo
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User
from app.service.user_storage import configured_storage_base, get_user_root, legacy_storage_base


def path_key(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def contains(root: str, path: str) -> bool:
    if not root or not path:
        return False
    root, path = path_key(root), path_key(path)
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def lock_user(db: Session, owner_id: UUID | str) -> User:
    """Serialize config changes and import commits, including across processes.

    An UPDATE also takes a writer lock on SQLite, where SELECT FOR UPDATE is
    ignored. Callers retain it until their transaction commits or rolls back.
    Read settings directly from the DB, bypassing the process-local config cache.
    """
    owner_id = UUID(str(owner_id))
    db.query(User).filter(User.id == owner_id).update({User.id: User.id}, synchronize_session=False)
    user = db.query(User).populate_existing().filter(User.id == owner_id).one()
    return user


def external_roots(user: User) -> list[str]:
    return list(((user.settings or {}).get('storage') or {}).get('external_directories') or [])


def managed_roots(user: User) -> list[str]:
    settings = user.settings or {}
    return [get_user_root(user.id, configured_storage_base(settings)),
            os.path.join(legacy_storage_base(settings), 'uploads')]


def import_allowed(user: User, path: str) -> bool:
    return any(contains(root, path) for root in external_roots(user) + managed_roots(user))


def owned_path_tasks(db: Session, owner_id: UUID) -> Query:
    """Include legacy tasks whose owner lives only in their JSON payload."""
    return db.query(Task).filter(
        or_(Task.owner_id == owner_id, and_(
            Task.owner_id.is_(None), Task.payload['user_id'].as_string() == str(owner_id))),
        Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.FAILED]),
    )


def cancel_path_tasks(db: Session, owner_id: UUID, predicate: Callable[[str], bool]) -> int:
    count = 0
    for task in owned_path_tasks(db, owner_id).all():
        path = (task.payload or {}).get('file_path')
        if path and predicate(path):
            task.status = TaskStatus.CANCELLED
            task.error = '照片来源已移除或文件已失效'
            count += 1
    db.flush()
    return count


def delete_index(db: Session, owner_id: UUID, photos: Iterable[Photo]) -> int:
    """Reuse cascade/album/thumbnail cleanup, never remove original media."""
    from app.crud.photo import batch_delete_photos_db
    from app.db.models.index_log import IndexLog
    photos = list(photos)
    if not photos:
        return 0
    for photo in photos:
        db.add(IndexLog(action='deleted', file_path=photo.file_path, photo_id=photo.id, owner_id=owner_id))
    return batch_delete_photos_db(db, [photo.id for photo in photos], is_delete_file=False, user_id=owner_id)


def remove_gallery(db: Session, owner_id: UUID, raw_path: str) -> dict:
    if not isinstance(raw_path, str) or not raw_path.strip() or '\x00' in raw_path:
        raise ValueError('请提供有效的文件夹绝对路径')
    raw_path = os.path.expanduser(raw_path.strip())
    if not os.path.isabs(raw_path):
        raise ValueError('请提供文件夹绝对路径')
    path = path_key(raw_path)
    if Path(path).parent == Path(path):
        raise ValueError('不能移除磁盘根目录')
    user = lock_user(db, owner_id)
    roots = external_roots(user)
    remaining = [root for root in roots if path_key(root) != path]
    if any(contains(path, root) or contains(root, path) for root in managed_roots(user) + remaining):
        raise ValueError('该路径与主存储或其他已添加文件夹重叠，请移除准确的图库目录')

    # Persist the removal before slow, chunked cleanup. Retrying still cleans
    # rows even when this directory is no longer present in the settings.
    from app.core.config_manager import config_manager
    settings = dict(user.settings or {})
    settings['storage'] = dict(settings.get('storage') or {}, external_directories=remaining)
    cancel_path_tasks(db, user.id, lambda candidate: contains(path, candidate))
    config_manager.update_user_config(user.id, settings, db)
    photos = db.query(Photo).filter(Photo.owner_id == user.id).all()
    deleted = delete_index(db, user.id, (p for p in photos if contains(path, p.file_path)))
    db.commit()
    return {'external': remaining, 'deleted_photos': deleted}
