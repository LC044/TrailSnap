"""One ownership-aware scope resolver shared by all toolbox tools."""
import os
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face
from app.db.models.photo import Photo, FileType
from app.db.models.storage_root import StorageRoot
from app.schemas.toolbox import MediaScope
from app.service.storage_paths import root_path
from app.service.user_storage import configured_storage_base, get_user_root


def canonical(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def is_below(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([canonical(path), canonical(root)]) == canonical(root)
    except (ValueError, OSError):
        return False


def owned_roots(db, user) -> list[str]:
    settings = user.settings or {}
    roots = [os.path.join(get_user_root(user.id, configured_storage_base(settings)), "uploads")]
    roots.extend((settings.get("storage") or {}).get("external_directories") or [])
    for record in db.query(StorageRoot).filter(StorageRoot.owner_id == user.id):
        roots.append(str(root_path({"kind": record.kind, "location": record.location})))
    return list(dict.fromkeys(canonical(p) for p in roots if p))


def allowed_directory(db, user, path: str) -> str:
    if not path or not Path(path).is_absolute() or not any(is_below(path, r) for r in owned_roots(db, user)):
        raise ValueError("目录不属于当前用户的已配置存储，或路径越界")
    return canonical(path)


def resolve_browser_folder(db, user, parent: str) -> str:
    """A display label cannot silently select one of two same-named roots."""
    from app.utils.path import get_user_roots
    parts = parent.replace("\\", "/").split("/")
    if not parent or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("请选择明确的文件夹，不支持全部或上级路径")
    roots = [root for root in get_user_roots(user.id, db) if os.path.basename(root) == parts[0]]
    if len(roots) != 1:
        raise ValueError("目录名称不唯一或已失效，请在工具箱选择实际目录")
    path = allowed_directory(db, user, os.path.join(roots[0], *parts[1:]))
    if not os.path.isdir(path):
        raise ValueError("原文件夹已不存在")
    return path


def scope_query(db, user, scope: MediaScope):
    query = db.query(Photo).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False))
    if scope.source == "albums":
        albums = db.query(Album).filter(Album.id.in_(scope.album_ids), Album.owner_id == user.id,
                                       Album.type == "user").all()
        if len(albums) != len(set(scope.album_ids)):
            raise ValueError("相册不存在、无权限或不支持动态相册")
        query = query.filter(Photo.id.in_(db.query(AlbumPhoto.photo_id).filter(AlbumPhoto.album_id.in_(scope.album_ids))))
    elif scope.source == "selected":
        owned = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.id.in_(scope.photo_ids)).count()
        if owned != len(set(scope.photo_ids)):
            raise ValueError("所选影像已不可用或无权限")
        query = query.filter(Photo.id.in_(scope.photo_ids))
    if scope.excluded_ids:
        query = query.filter(Photo.id.notin_(scope.excluded_ids))
    if scope.media_type != "all":
        query = query.filter(Photo.file_type == FileType(scope.media_type))
    date_column = func.coalesce(Photo.photo_time, Photo.upload_time) if scope.upload_time_fallback else Photo.photo_time
    if scope.start_date:
        query = query.filter(date_column >= datetime.combine(scope.start_date, time.min))
    if scope.end_date:
        query = query.filter(date_column < datetime.combine(scope.end_date, time.min) + timedelta(days=1))
    return query


def iter_scope(db, user, scope: MediaScope, *, relations=False):
    folders = [allowed_directory(db, user, p) for p in scope.folders] if scope.source == "folders" else []
    query = scope_query(db, user, scope).order_by(Photo.id)
    if relations:
        query = query.options(selectinload(Photo.metadata_info), selectinload(Photo.tags),
                              selectinload(Photo.faces).selectinload(Face.identity),
                              selectinload(Photo.image_description))
    for photo in query.yield_per(250):
        if folders:
            try:
                path = photo.file_path
                if not path or not any(
                    is_below(path, root) if scope.include_children else canonical(os.path.dirname(path)) == root
                    for root in folders
                ):
                    continue
            except (ValueError, OSError):
                continue
        yield photo


def scope_preview(db, user, scope: MediaScope, offset=0, limit=40):
    count, rows = 0, []
    for photo in iter_scope(db, user, scope):
        if offset <= count < offset + limit:
            rows.append({"id": str(photo.id), "filename": photo.filename,
                         "photo_time": photo.photo_time, "file_type": getattr(photo.file_type, "value", photo.file_type)})
        count += 1
    return {"total": count, "items": rows}
