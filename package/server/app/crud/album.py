from typing import List, Optional, Union
import json
import logging
import time
from uuid import UUID

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, or_, text
from datetime import datetime

from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.face import Face
from app.db.models.image_vector import ImageVector
from app.db.models.user import User
from app.schemas import album as album_schemas
import numpy as np

logger = logging.getLogger("app.album")


def _postgresql_cte_hint(db: Session) -> str:
    """Materialize reused CTEs on PostgreSQL to avoid repeating their joins."""
    try:
        return "MATERIALIZED" if db.get_bind().dialect.name == "postgresql" else ""
    except Exception:
        return ""


def _decode_face_rect(value):
    """Decode JSON face rectangles for databases that return TEXT from raw SQL."""
    if value is None or isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else None
    except (TypeError, ValueError):
        return None


def _build_folder_condition(folders):
    """Build an OR filter for relative folder paths stored in album conditions.

    Folder paths come from the hierarchical ``/photos/folders`` endpoint and
    include the scan-root label (for example ``Photos/Trips``).  Photo paths
    may be absolute or relative and may use either path separator, so match a
    complete path segment after normalising separators in SQL.
    """
    if not isinstance(folders, list):
        return None

    normalized_folders = []
    for folder in folders:
        if not isinstance(folder, str):
            continue
        normalized = folder.strip().replace('\\', '/').strip('/')
        if normalized and normalized not in normalized_folders:
            normalized_folders.append(normalized)

    if not normalized_folders:
        return None

    def _escape_like(value: str) -> str:
        return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

    normalized_path = func.replace(Photo.file_path, '\\', '/')
    filters = []
    for folder in normalized_folders:
        escaped = _escape_like(folder)
        # The first form covers relative stored paths, while the second covers
        # absolute paths.  Both include all descendants of the chosen folder.
        filters.append(or_(
            normalized_path.like(escaped + '/%', escape='\\'),
            normalized_path.like('%/' + escaped + '/%', escape='\\'),
        ))
    return or_(*filters)


# Album CRUD
def _build_album_query(db: Session, album: Album):
    query = db.query(Photo).filter(Photo.is_deleted == False)
    
    # Ensure smart/conditional albums only see user's own photos
    if album.owner_id is not None:
        query = query.filter(Photo.owner_id == album.owner_id)

    if album.type == 'conditional' and album.condition:
        query = query.outerjoin(PhotoMetadata)
        cond = album.condition
        # Time Range
        if 'time_range' in cond:
            tr = cond['time_range']
            if tr.get('start'):
                try:
                    s = datetime.fromisoformat(tr['start'].replace('Z', '+00:00'))
                    query = query.filter(Photo.photo_time >= s)
                except:
                    pass
            if tr.get('end'):
                try:
                    e = datetime.fromisoformat(tr['end'].replace('Z', '+00:00'))
                    query = query.filter(Photo.photo_time <= e)
                except:
                    pass
        # Location
        if 'locations' in cond and isinstance(cond['locations'], list) and cond['locations']:
             loc_filters = []
             for loc in cond['locations']:
                 sub_filters = []
                 if loc.get('province'):
                     sub_filters.append(PhotoMetadata.province == loc['province'])
                 if loc.get('city'):
                     sub_filters.append(PhotoMetadata.city == loc['city'])
                 if loc.get('district'):
                     sub_filters.append(PhotoMetadata.district == loc['district'])
                 if sub_filters:
                     loc_filters.append(and_(*sub_filters))
             if loc_filters:
                 query = query.filter(or_(*loc_filters))

        # People
        if 'people' in cond and isinstance(cond['people'], list) and cond['people']:
             people_ids = cond['people']
             # Assuming people_ids are UUID strings
             query = query.join(Photo.faces).filter(Face.face_identity_id.in_(people_ids))

        # Folders (each selected folder includes all of its descendants)
        folder_filter = _build_folder_condition(cond.get('folders'))
        if folder_filter is not None:
             query = query.filter(folder_filter)

        # Deduplicate
        query = query.group_by(Photo.id)

    elif album.type == 'smart' and album.query_embedding is not None:
        # Vector Search
        query = query.join(ImageVector)
        
        # Cosine distance
        distance = ImageVector.embedding.cosine_distance(album.query_embedding)
        
        # Threshold Logic
        # user_threshold is similarity (0-1), where 1 is identical.
        # cosine_distance is distance (0-2), where 0 is identical.
        # distance = 1 - similarity (approx, for normalized vectors)
        # So: similarity > threshold  =>  (1 - distance) > threshold  =>  distance < (1 - threshold)
        
        user_threshold = album.threshold if album.threshold is not None else 0.25
        dist_threshold = 1.0 - user_threshold

        # Clamp distance threshold to avoid logical errors
        dist_threshold = max(0.0, min(1.0, dist_threshold))

        if db.bind.dialect.name == "sqlite":
            target = np.asarray(album.query_embedding, dtype=float)
            target_norm = np.linalg.norm(target)
            matching_ids = []
            for photo_id, embedding in query.with_entities(Photo.id, ImageVector.embedding).all():
                candidate = np.asarray(embedding, dtype=float)
                denominator = np.linalg.norm(candidate) * target_norm
                cosine_distance = 1.0 if denominator == 0 else 1.0 - float(np.dot(candidate, target) / denominator)
                if cosine_distance < dist_threshold:
                    matching_ids.append(photo_id)
            query = query.filter(Photo.id.in_(matching_ids)) if matching_ids else query.filter(False)
        else:
            query = query.filter(distance < dist_threshold)

    else:
        # Standard User Album
        query = query.join(Photo.albums).filter(Album.id == album.id)
    
    return query

import threading

def _update_album_photo_count(db: Session, album_id: UUID):
    album = db.query(Album).filter(Album.id == album_id).first()
    if album:
        query = _build_album_query(db, album)
        count = query.count()
        album.num_photos = count
        db.add(album)
        db.commit()


def update_album_photo_counts(db: Session, album_ids) -> int:
    """Recount several albums inside a single transaction.

    ``_update_album_photo_count`` commits on every call. When a bulk delete
    touches dozens of albums that becomes dozens of fsyncs plus dozens of
    ``SELECT`` round trips for the album rows, which is a large part of why
    purging a big selection appears to hang. Here the album rows are fetched
    once and a single commit closes the whole batch.

    Returns the number of albums whose counter was refreshed.
    """
    unique_ids = list(dict.fromkeys(album_ids or []))
    if not unique_ids:
        return 0

    albums = db.query(Album).filter(Album.id.in_(unique_ids)).all()
    if not albums:
        return 0

    for album in albums:
        album.num_photos = _build_album_query(db, album).count()
        db.add(album)
    db.commit()
    return len(albums)

def trigger_conditional_albums_update(db: Session, user_id: UUID, photo_ids: List[UUID] = None):
    """
    Trigger update for all conditional/smart albums for a given user.
    If photo_ids is provided, only those photos will be checked and updated, 
    making it much more efficient than a full scan.
    """
    albums = db.query(Album).filter(
        Album.owner_id == user_id,
        Album.type.in_(['conditional', 'smart'])
    ).all()
    
    if not albums:
        return
        
    if photo_ids is not None:
        if not photo_ids:
            return
            
        for album in albums:
            # Check which of the given photos match the album condition
            if len(photo_ids) == 1:
                photo_id = photo_ids[0]
                matching_query = _build_album_query(db, album).filter(Photo.id == photo_id)
            else:
                matching_query = _build_album_query(db, album).filter(Photo.id.in_(photo_ids))
            matching_photos = matching_query.all()
            matching_photo_ids = {p.id for p in matching_photos}
            
            # Current association for these photos and this album
            existing_relations = db.query(AlbumPhoto).filter(
                AlbumPhoto.album_id == album.id,
                AlbumPhoto.photo_id.in_(photo_ids)
            ).all()
            existing_photo_ids = {r.photo_id for r in existing_relations}
            
            to_add = matching_photo_ids - existing_photo_ids
            to_remove = existing_photo_ids - matching_photo_ids
            
            if to_add:
                new_relations = [
                    AlbumPhoto(album_id=album.id, photo_id=pid)
                    for pid in to_add
                ]
                db.add_all(new_relations)
                
            if to_remove:
                db.query(AlbumPhoto).filter(
                    AlbumPhoto.album_id == album.id,
                    AlbumPhoto.photo_id.in_(to_remove)
                ).delete(synchronize_session=False)
                
            if to_add or to_remove:
                db.commit()
                _update_album_photo_count(db, album.id)
                
                # Update cover if needed
                if not album.cover_id or (album.cover_id in to_remove):
                    first_photo = _build_album_query(db, album).order_by(Photo.photo_time.asc()).first()
                    album.cover_id = first_photo.id if first_photo else None
                    db.add(album)
                    db.commit()
    else:
        # Fallback to full async scan if no photo_ids provided
        from app.db.models.task import TaskType
        from app.service.task_worker import TaskWorker
        for album in albums:
            TaskWorker.get_instance().add_task(
                db, 
                TaskType.SCAN_ALBUM, 
                payload={'album_id': str(album.id)},
                owner_id=user_id
            )

def get_album(db: Session, album_id: UUID, user_id: UUID = None):
    query = db.query(Album).options(joinedload(Album.cover)).filter(Album.id == album_id)
    if user_id is not None:
        query = query.filter(or_(Album.owner_id == user_id, Album.shared_users.any(id=user_id)))
    return query.first()

def get_albums_by_photo_id(db: Session, photo_id: UUID):
    return db.query(Album).join(Album.photos).filter(Photo.id == photo_id).all()

def get_albums(db: Session, skip: int = 0, limit: int = 100, user_id: UUID = None):
    query = db.query(Album).options(joinedload(Album.cover))
    if user_id is not None:
        query = query.filter(or_(Album.owner_id == user_id, Album.shared_users.any(id=user_id)))
    return query.offset(skip).limit(limit).all()

def create_album(db: Session, album: album_schemas.AlbumCreate, query_embedding: Optional[List[float]] = None, user_id: UUID = None):
    db_album = Album(
        name=album.name, 
        description=album.description,
        type=album.type,
        condition=album.condition,
        query_embedding=query_embedding,
        threshold=album.threshold,
        owner_id=user_id
    )
    
    if album.shared_users:
        users = db.query(User).filter(User.id.in_(album.shared_users)).all()
        db_album.shared_users = users

    db.add(db_album)
    db.commit()
    db.refresh(db_album)
    
    return db_album

def delete_album(db: Session, album_id: UUID):
    db_album = get_album(db, album_id)
    if db_album:
        db.delete(db_album)
        db.commit()
    return db_album

def update_album(db: Session, album_id: UUID, album: Union[album_schemas.AlbumUpdate, album_schemas.AlbumCreate], query_embedding: Optional[List[float]] = None):
    db_album = get_album(db, album_id)
    if db_album:
        if album.name:
            db_album.name = album.name
        if album.description is not None:
            db_album.description = album.description
        if album.condition is not None:
            db_album.condition = album.condition
        if album.threshold is not None:
            db_album.threshold = album.threshold
        if query_embedding is not None:
            db_album.query_embedding = query_embedding

        # Handle shared_users
        shared_users_ids = getattr(album, 'shared_users', None)
        if shared_users_ids is not None:
            if not shared_users_ids:
                db_album.shared_users = []
            else:
                users = db.query(User).filter(User.id.in_(shared_users_ids)).all()
                db_album.shared_users = users

        db.commit()
        db.refresh(db_album)

        return db_album

    return db_album


# Photo CRUD

def batch_update_album_association(db: Session, photo_ids: List[UUID], album_id: UUID, action: str, user_id: UUID = None):
    """
    批量更新照片与相册的关联关系，支持添加、移除或删除操作。
    优化点：
    1. 使用 joinedload 预加载 albums，避免 N+1 查询
    2. 使用集合操作批量处理关联关系，减少逐条判断
    3. 仅在必要时更新相册封面
    4. 使用 bulk 操作减少 commit 次数
    """
    if not photo_ids:
        return 0

    # 预加载照片及其关联的相册，避免后续 N+1 查询
    query = (
        db.query(Photo)
        .options(joinedload(Photo.albums))
        .filter(Photo.id.in_(photo_ids))
    )
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
        
    photos = query.all()
    if not photos:
        return 0

    album = None
    if album_id:
        album = get_album(db, album_id, user_id=user_id)
        if not album:
            return 0

    count = 0

    if action == 'add_to_album' and album:
        # 使用集合差集快速找出未关联的照片
        photos_to_add = [p for p in photos if album not in p.albums]
        for photo in photos_to_add:
            photo.albums.append(album)
        count = len(photos_to_add)
        # 仅在相册无封面且新增照片时设置封面
        if not album.cover_id and photos_to_add:
            album.cover_id = photos_to_add[0].id
            db.add(album)

    elif action == 'remove_from_album' and album:
        # 使用集合交集快速找出已关联的照片
        photos_to_remove = [p for p in photos if album in p.albums]
        for photo in photos_to_remove:
            photo.albums.remove(album)
        count = len(photos_to_remove)

    elif action == 'delete':
        # 由 batch_delete_photos_db 处理，此处仅保持一致接口
        pass

    # 批量提交所有变更
    if count > 0:
        db.add_all(photos)  # 确保关联变更被追踪
        db.commit()
        if album_id:
            _update_album_photo_count(db, album_id)

    return count

# Metadata CRUD


def _smart_people_section(db: Session, owner_id: UUID, representative_limit: int) -> album_schemas.SmartAlbumSection:
    """Build the people summary in a single database round trip."""
    query = text(
        f"""
        WITH valid_faces AS {_postgresql_cte_hint(db)} (
            SELECT
                fi.id AS identity_id,
                fi.identity_name,
                f.id AS face_id,
                f.photo_id,
                f.face_rect,
                (f.id = fi.default_face_id) AS is_default_face
            FROM faces f
            JOIN face_identities fi ON fi.id = f.face_identity_id
            JOIN photos p ON p.id = f.photo_id
            WHERE f.face_identity_id IS NOT NULL
              AND fi.owner_id = :owner_id
              AND fi.is_deleted = false
              AND fi.is_hidden = false
              AND f.is_deleted = false
              AND p.owner_id = :owner_id
              AND p.is_deleted = false
        ),
        face_stats AS (
            SELECT identity_id, COUNT(DISTINCT photo_id) AS photo_count
            FROM valid_faces
            GROUP BY identity_id
        ),
        overall_stats AS (
            SELECT
                COUNT(DISTINCT identity_id) AS item_count,
                COUNT(DISTINCT photo_id) AS photo_count
            FROM valid_faces
        ),
        top_identities AS (
            SELECT identity_id, photo_count
            FROM face_stats
            ORDER BY photo_count DESC, identity_id ASC
            LIMIT :representative_limit
        ),
        ranked_faces AS (
            SELECT
                vf.*,
                ROW_NUMBER() OVER (
                    PARTITION BY vf.identity_id
                    ORDER BY vf.is_default_face DESC, vf.face_id ASC
                ) AS face_rank
            FROM valid_faces vf
            WHERE vf.identity_id IN (SELECT identity_id FROM top_identities)
        )
        SELECT
            ti.identity_id,
            rf.identity_name,
            rf.photo_id,
            rf.face_rect,
            ti.photo_count,
            os.item_count,
            os.photo_count AS total_photo_count
        FROM top_identities ti
        JOIN ranked_faces rf
          ON rf.identity_id = ti.identity_id
         AND rf.face_rank = 1
        CROSS JOIN overall_stats os
        ORDER BY ti.photo_count DESC, ti.identity_id ASC
        """
    )
    rows = db.execute(query, {
        "owner_id": str(owner_id),
        "representative_limit": representative_limit,
    }).mappings().all()

    if not rows:
        return album_schemas.SmartAlbumSection()

    first = rows[0]
    representatives = [
        album_schemas.SmartAlbumRepresentative(
            entity_id=str(row["identity_id"]),
            name=row["identity_name"] or "未命名",
            photo_id=row["photo_id"],
            face_rect=_decode_face_rect(row["face_rect"]),
            photo_count=int(row["photo_count"] or 0),
        )
        for row in rows
        if row["photo_id"] is not None
    ]
    return album_schemas.SmartAlbumSection(
        item_count=int(first["item_count"] or 0),
        photo_count=int(first["total_photo_count"] or 0),
        representatives=representatives,
    )


def _smart_location_section(db: Session, owner_id: UUID, representative_limit: int) -> album_schemas.SmartAlbumSection:
    """Build the city-level location summary in a single database round trip."""
    query = text(
        f"""
        WITH valid_locations AS {_postgresql_cte_hint(db)} (
            SELECT
                p.id AS photo_id,
                pm.city AS location_name,
                p.photo_time,
                p.upload_time
            FROM photos p
            JOIN photo_metadata pm ON pm.photo_id = p.id
            WHERE p.owner_id = :owner_id
              AND p.is_deleted = false
              AND pm.city IS NOT NULL
              AND pm.city <> ''
        ),
        city_stats AS (
            SELECT location_name, COUNT(photo_id) AS photo_count
            FROM valid_locations
            GROUP BY location_name
        ),
        overall_stats AS (
            SELECT
                COUNT(DISTINCT location_name) AS item_count,
                COUNT(DISTINCT photo_id) AS photo_count
            FROM valid_locations
        ),
        top_cities AS (
            SELECT location_name, photo_count
            FROM city_stats
            ORDER BY photo_count DESC, location_name ASC
            LIMIT :representative_limit
        ),
        ranked_photos AS (
            SELECT
                vl.*,
                ROW_NUMBER() OVER (
                    PARTITION BY vl.location_name
                    ORDER BY
                        CASE WHEN vl.photo_time IS NULL THEN 1 ELSE 0 END,
                        vl.photo_time DESC,
                        vl.upload_time DESC,
                        vl.photo_id ASC
                ) AS photo_rank
            FROM valid_locations vl
            WHERE vl.location_name IN (SELECT location_name FROM top_cities)
        )
        SELECT
            tc.location_name,
            rp.photo_id,
            tc.photo_count,
            os.item_count,
            os.photo_count AS total_photo_count
        FROM top_cities tc
        JOIN ranked_photos rp
          ON rp.location_name = tc.location_name
         AND rp.photo_rank = 1
        CROSS JOIN overall_stats os
        ORDER BY tc.photo_count DESC, tc.location_name ASC
        """
    )
    rows = db.execute(query, {
        "owner_id": str(owner_id),
        "representative_limit": representative_limit,
    }).mappings().all()

    if not rows:
        return album_schemas.SmartAlbumSection()

    first = rows[0]
    representatives = [
        album_schemas.SmartAlbumRepresentative(
            entity_id=row["location_name"],
            name=row["location_name"],
            photo_id=row["photo_id"],
            photo_count=int(row["photo_count"] or 0),
        )
        for row in rows
        if row["photo_id"] is not None
    ]
    return album_schemas.SmartAlbumSection(
        item_count=int(first["item_count"] or 0),
        photo_count=int(first["total_photo_count"] or 0),
        representatives=representatives,
    )


def _smart_classification_section(db: Session, owner_id: UUID, representative_limit: int) -> album_schemas.SmartAlbumSection:
    """Build the AI-classification summary in a single database round trip."""
    query = text(
        f"""
        WITH valid_relations AS {_postgresql_cte_hint(db)} (
            SELECT
                ptr.tag_id,
                ptr.photo_id,
                ptr.created_at,
                ptr.id AS relation_id
            FROM photo_tag_relations ptr
            JOIN photo_tags pt ON pt.id = ptr.tag_id
            JOIN photos p ON p.id = ptr.photo_id
            WHERE pt.owner_id = :owner_id
              AND pt.is_deleted = false
              AND p.owner_id = :owner_id
              AND p.is_deleted = false
              AND ptr.is_deleted = false
        ),
        tag_stats AS (
            SELECT tag_id, COUNT(DISTINCT photo_id) AS photo_count
            FROM valid_relations
            GROUP BY tag_id
        ),
        overall_stats AS (
            SELECT
                COUNT(DISTINCT tag_id) AS item_count,
                COUNT(DISTINCT photo_id) AS photo_count
            FROM valid_relations
        ),
        top_tags AS (
            SELECT
                pt.id AS tag_id,
                pt.tag_name,
                pt.cover_id,
                ts.photo_count
            FROM photo_tags pt
            JOIN tag_stats ts ON ts.tag_id = pt.id
            WHERE pt.owner_id = :owner_id
              AND pt.is_deleted = false
            ORDER BY ts.photo_count DESC, pt.id ASC
            LIMIT :representative_limit
        ),
        ranked_relations AS (
            SELECT
                vr.*,
                ROW_NUMBER() OVER (
                    PARTITION BY vr.tag_id
                    ORDER BY vr.created_at DESC, vr.relation_id DESC
                ) AS relation_rank
            FROM valid_relations vr
            WHERE vr.tag_id IN (SELECT tag_id FROM top_tags)
        ),
        explicit_covers AS (
            SELECT tt.tag_id, p.id AS photo_id
            FROM top_tags tt
            JOIN photos p ON p.id = tt.cover_id
            WHERE p.owner_id = :owner_id
              AND p.is_deleted = false
        ),
        fallback_covers AS (
            SELECT rr.tag_id, rr.photo_id
            FROM ranked_relations rr
            WHERE rr.relation_rank = 1
        )
        SELECT
            tt.tag_id,
            tt.tag_name,
            COALESCE(ec.photo_id, fc.photo_id) AS photo_id,
            tt.photo_count,
            os.item_count,
            os.photo_count AS total_photo_count
        FROM top_tags tt
        LEFT JOIN explicit_covers ec ON ec.tag_id = tt.tag_id
        LEFT JOIN fallback_covers fc ON fc.tag_id = tt.tag_id
        CROSS JOIN overall_stats os
        ORDER BY tt.photo_count DESC, tt.tag_id ASC
        """
    )
    rows = db.execute(query, {
        "owner_id": str(owner_id),
        "representative_limit": representative_limit,
    }).mappings().all()

    if not rows:
        return album_schemas.SmartAlbumSection()

    first = rows[0]
    representatives = [
        album_schemas.SmartAlbumRepresentative(
            entity_id=str(row["tag_id"]),
            name=row["tag_name"],
            photo_id=row["photo_id"],
            photo_count=int(row["photo_count"] or 0),
        )
        for row in rows
        if row["photo_id"] is not None
    ]
    return album_schemas.SmartAlbumSection(
        item_count=int(first["item_count"] or 0),
        photo_count=int(first["total_photo_count"] or 0),
        representatives=representatives,
    )


def get_smart_album_overview(db: Session, owner_id: UUID, representative_limit: int = 4) -> album_schemas.SmartAlbumOverview:
    """Return counts and representative covers for the three built-in smart albums."""
    started_at = time.perf_counter()
    section_timings: dict[str, float] = {}

    def timed_section(name: str, builder) -> album_schemas.SmartAlbumSection:
        section_started_at = time.perf_counter()
        result = builder()
        section_timings[name] = (time.perf_counter() - section_started_at) * 1000
        return result

    overview = album_schemas.SmartAlbumOverview(
        people=timed_section("people", lambda: _smart_people_section(db, owner_id, representative_limit)),
        location=timed_section("location", lambda: _smart_location_section(db, owner_id, representative_limit)),
        classification=timed_section("classification", lambda: _smart_classification_section(db, owner_id, representative_limit)),
    )
    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "Smart album overview generated user_id=%s duration_ms=%.1f people_ms=%.1f location_ms=%.1f classification_ms=%.1f",
        owner_id,
        duration_ms,
        section_timings.get("people", 0),
        section_timings.get("location", 0),
        section_timings.get("classification", 0),
    )
    return overview
