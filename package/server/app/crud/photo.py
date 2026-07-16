#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2026/3/8 21:05
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-photo.py
@Description : 
"""
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.crud import face as crud_face
from app.crud.album import get_album, _build_album_query, _update_album_photo_count
from app.crud.cluster import remove_photo_from_clusters
from app.crud.search_vector import POSITIVE_SENTIMENT_VECTOR
from app.db.models import Photo, PhotoMetadata, ImageVector, Album, Face, PhotoTag, ImageDescription, Scene
from app.db.models.photo import FileType, ImageType
from app.schemas import photo as photo_schemas
from app.schemas.metadata import PhotoMetadataUpdate
from app.service import storage
from app.utils.exif import extract_metadata


def batch_create_photos(db: Session, photos_data: List[dict], user_id: Optional[UUID] = None):
    """
    Batch create photos and metadata.
    photos_data: List of dicts containing:
        - photo: PhotoCreate schema
        - metadata: PhotoMetadataCreate schema (optional)
        - photo_id: UUID
        - file_path: str
    """
    if not photos_data:
        return 0

    try:
        # 兜底去重：过滤掉数据库中已存在的 (owner_id, file_path)，避免并发扫描
        # 或历史重复任务导致同一文件被多次入库。
        incoming_paths = [item['file_path'] for item in photos_data if item.get('file_path')]
        if incoming_paths:
            existing_query = db.query(Photo.file_path).filter(
                Photo.file_path.in_(incoming_paths)
            )
            if user_id is not None:
                existing_query = existing_query.filter(Photo.owner_id == user_id)
            existing_paths = {row[0] for row in existing_query.all()}

            # 同一批次内也需要去重（比如多个 PROCESS_BASIC 并发时打包了同一文件）
            seen_in_batch = set()
            deduped = []
            for item in photos_data:
                fp = item.get('file_path')
                if not fp:
                    continue
                if fp in existing_paths or fp in seen_in_batch:
                    continue
                seen_in_batch.add(fp)
                deduped.append(item)

            skipped = len(photos_data) - len(deduped)
            if skipped > 0:
                import logging
                logging.info(
                    f"batch_create_photos: skipped {skipped} duplicate file_path(s) for user={user_id}"
                )
            photos_data = deduped

        if not photos_data:
            return 0

        photos = []
        metadatas = []

        for item in photos_data:
            p_schema = item['photo']
            m_schema = item.get('metadata')
            photo_id = item['photo_id']
            file_path = item['file_path']

            photo = Photo(
                id=photo_id,
                filename=p_schema.filename,
                photo_time=p_schema.photo_time,
                file_path=file_path,
                file_type=p_schema.file_type,
                size=p_schema.size,
                width=p_schema.width,
                height=p_schema.height,
                duration=p_schema.duration,
                owner_id=user_id
            )
            photos.append(photo)

            if m_schema:
                meta = PhotoMetadata(
                    photo_id=photo_id,
                    exif_info=m_schema.exif_info,
                    # Other fields from schema if any
                )
                metadatas.append(meta)

        db.bulk_save_objects(photos)
        if metadatas:
            db.bulk_save_objects(metadatas)

        db.commit()
        
        if user_id:
            from app.crud.album import trigger_conditional_albums_update
            trigger_conditional_albums_update(db, user_id, [p.id for p in photos])
            
        return len(photos)
    except Exception as e:
        db.rollback()
        raise e


def update_photo_metadata(db: Session, photo_id: UUID, metadata: PhotoMetadataUpdate, user_id: UUID = None):
    db_metadata = get_photo_metadata(db, photo_id, user_id)
    if not db_metadata:
        # Check if photo exists and owned by user before creating metadata
        photo = get_photo(db, photo_id)
        if not photo:
            return None
        if user_id is not None and photo.owner_id != user_id:
            return None

        db_metadata = PhotoMetadata(photo_id=photo_id)
        db.add(db_metadata)

    update_data = metadata.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_metadata, key, value)

    db.add(db_metadata)
    db.commit()
    db.refresh(db_metadata)
    
    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [photo_id])
        
    return db_metadata


def get_photo_metadata(db: Session, photo_id: UUID, user_id: UUID = None):
    query = db.query(PhotoMetadata).join(Photo).filter(PhotoMetadata.photo_id == photo_id)
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
    return query.first()


def save_and_create_photo(db: Session, file_path: str, file_name: str, album_id: Optional[UUID], photo_id: UUID, user_id: UUID = None):
    # Determine file type
    ext = os.path.splitext(file_name)[1]
    file_type = FileType.image
    if ext.lower() in ['.mp4', '.mov', '.avi']:
        file_type = FileType.video

    storage.generate_thumbnail(user_id, file_path, photo_id)

    # Get Metadata
    size = storage.get_file_size(file_path)
    width, height, duration = storage.get_image_dimensions(file_path)

    extracted_meta = extract_metadata(file_path, file_name, extract_location_details=False)

    # Create Schema for DB
    photo_create = photo_schemas.PhotoCreate(
        file_type=file_type,
        size=size,
        width=width,
        height=height,
        duration=duration,
        filename=file_name,
        photo_time=extracted_meta["photo_time"]
    )

    return create_photo(db, photo_create, album_id, file_path, photo_id=photo_id, user_id=user_id)


def get_photos(db: Session, album_id: UUID, skip: int = 0, limit: int = 100, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, user_id: UUID = None):
    # Retrieve album details first
    album = get_album(db, album_id, user_id)
    if not album:
        return []

    query = _build_album_query(db, album)

    # Ordering
    if album.type == 'smart' and album.query_embedding is not None:
        # Order by similarity
        distance = ImageVector.embedding.cosine_distance(album.query_embedding)
        query = query.order_by(distance)
    else:
        # Default order by time
        query = query.order_by(Photo.photo_time.desc())

    # Common filters (start_time, end_time from args)
    if start_time:
        query = query.filter(Photo.photo_time >= start_time)
    if end_time:
        query = query.filter(Photo.photo_time <= end_time)

    # Optimization for user albums
    if album.type == 'user':
        query = query.options(joinedload(Photo.albums))

    if limit == 0:
        return query.offset(skip).all()
    return query.offset(skip).limit(limit).all()


def get_photos_by_time(db: Session, owner_id: UUID, skip: int = 0, limit: int = 100, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None):
    query = db.query(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
    if start_time:
        query = query.filter(Photo.photo_time >= start_time)
    if end_time:
        query = query.filter(Photo.photo_time <= end_time)
    # 按拍摄时间倒序
    query = query.order_by(Photo.photo_time.desc())
    if limit == 0:
        # 不限制数量，返回所有照片
        return query.offset(skip).all()
    return query.offset(skip).limit(limit).all()


def get_filter_options(db: Session, user_id: UUID):
    # Optimize: Fetch all distinct combinations in a single query
    results = db.query(
        func.extract('year', Photo.photo_time).label('year'),
        PhotoMetadata.city,
        PhotoMetadata.make,
        PhotoMetadata.model
    ).outerjoin(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == user_id
    ).distinct().all()

    years_set = set()
    cities_set = set()
    makes_set = set()
    models_set = set()

    for r in results:
        if r.year is not None:
            years_set.add(int(r.year))
        if r.city:
            cities_set.add(r.city)
        if r.make:
            makes_set.add(r.make)
        if r.model:
            models_set.add(r.model)

    # Image Types
    image_types = [t.value for t in ImageType]

    # File Types
    file_types = [t.value for t in FileType]

    return {
        "years": sorted(list(years_set), reverse=True),
        "cities": sorted(list(cities_set)),
        "makes": sorted(list(makes_set)),
        "models": sorted(list(models_set)),
        "image_types": image_types,
        "file_types": file_types
    }


def _build_photo_filter_query(
    db: Session,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    years: Optional[List[int]] = None,
    city: Optional[str] = None,
    cities: Optional[List[str]] = None,
    scene: Optional[str] = None,
    scenes: Optional[List[str]] = None,
    province: Optional[str] = None,
    provinces: Optional[List[str]] = None,
    country: Optional[str] = None,
    countries: Optional[List[str]] = None,
    make: Optional[str] = None,
    makes: Optional[List[str]] = None,
    model: Optional[str] = None,
    models: Optional[List[str]] = None,
    image_type: Optional[str] = None,
    image_types: Optional[List[str]] = None,
    file_type: Optional[str] = None,
    file_types: Optional[List[str]] = None,
    tag: Optional[str] = None,
    album_id: Optional[UUID] = None,
    album_ids: Optional[List[UUID]] = None,
    face_id: Optional[UUID] = None,
    face_ids: Optional[List[UUID]] = None,
    tag_id: Optional[UUID] = None,
    tag_ids: Optional[List[UUID]] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lng_min: Optional[float] = None,
    lng_max: Optional[float] = None,
    radius: Optional[float] = None,
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
    ids: Optional[List[UUID]] = None,
    order_by: Optional[str] = None,
    folder: Optional[str] = None,
    folder_direct: bool = False,
    folder_roots: Optional[List[str]] = None,
    user_id: UUID = None,
    is_deleted: bool = False
):
    # 先筛选 Photo，减少后续连表的数据量
    photo_query = db.query(Photo.id).filter(Photo.is_deleted == is_deleted)

    if user_id is not None:
        photo_query = photo_query.filter(Photo.owner_id == user_id)

    # Filter by IDs if provided
    if ids:
        photo_query = photo_query.filter(Photo.id.in_(ids))

    # Folder Filter：按文件夹路径匹配。
    # 支持形态：
    #   - 绝对路径（以 / 开头）：按原始路径前缀匹配（兼容旧调用）。
    #   - 相对路径（层级树浏览，如 "旅游/景点"）：匹配任意根目录下该相对路径。
    # folder_direct=True 时只匹配「本层直属」照片（不含更深子目录）。
    from sqlalchemy import or_ as _or
    def _esc(s):
        return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    norm_expr = func.replace(Photo.file_path, '\\', '/')

    if folder and folder.strip():
        f = folder.strip().replace('\\', '/').rstrip('/')
        esc = _esc(f)
        if f.startswith('/'):
            base_pat = esc + '/%'
            photo_query = photo_query.filter(norm_expr.like(base_pat, escape='\\'))
            if folder_direct:
                photo_query = photo_query.filter(~norm_expr.like(esc + '/%/%', escape='\\'))
        else:
            # 相对路径：前面必须紧跟 /（避免 "b旅游" 误命中 "旅游"）
            photo_query = photo_query.filter(norm_expr.like('%/' + esc + '/%', escape='\\'))
            if folder_direct:
                photo_query = photo_query.filter(~norm_expr.like('%/' + esc + '/%/%', escape='\\'))
    elif folder_direct and folder_roots:
        # 根层直属：浏览模型下每个扫描根都作为一个顶层文件夹，因此归属到任一扫描根
        # 的照片都属于对应根文件夹，根层本身只保留「无法归属到任何扫描根」的孤儿照片。
        for r in folder_roots:
            if not r:
                continue
            rn = r.replace('\\', '/').rstrip('/')
            esc = _esc(rn)
            photo_query = photo_query.filter(~norm_expr.like(esc + '/%', escape='\\'))

    # 时间范围过滤（Photo 表）
    if start_time or end_time:
        if not start_time:
            start_time = datetime.min
        if not end_time:
            end_time = datetime.max
        photo_query = photo_query.filter(Photo.photo_time >= start_time, Photo.photo_time <= end_time)

    # Years Filter
    if years:
        photo_query = photo_query.filter(func.extract('year', Photo.photo_time).in_(years))

    # Image Types Filter
    if image_types:
        photo_query = photo_query.filter(Photo.image_type.in_(image_types))
    elif image_type:
        photo_query = photo_query.filter(Photo.image_type == image_type)

    # File Types Filter
    if file_types:
        photo_query = photo_query.filter(Photo.file_type.in_(file_types))
    elif file_type:
        photo_query = photo_query.filter(Photo.file_type == file_type)

    needs_distinct = False

    # 如果指定 album_id / album_ids，先过滤出该相册下的 photo_id
    if album_ids:
        photo_query = photo_query.join(Photo.albums).filter(Album.id.in_(album_ids))
        needs_distinct = True
    elif album_id is not None:
        photo_query = photo_query.join(Photo.albums).filter(Album.id == album_id)
        needs_distinct = True

    # Face Identity Filter
    if face_ids:
        photo_query = photo_query.join(Photo.faces).filter(Face.face_identity_id.in_(face_ids))
        needs_distinct = True
    elif face_id is not None:
        photo_query = photo_query.join(Photo.faces).filter(Face.face_identity_id == face_id)
        needs_distinct = True

    # Tag ID Filter
    if tag_ids:
        photo_query = photo_query.join(Photo.tags).filter(PhotoTag.id.in_(tag_ids))
        needs_distinct = True
    elif tag_id is not None:
        photo_query = photo_query.join(Photo.tags).filter(PhotoTag.id == tag_id)
        needs_distinct = True

    # Tag Name Filter (if tag string provided)
    if tag is not None and tag.strip():
        photo_query = photo_query.join(Photo.tags).filter(PhotoTag.tag_name.ilike(f"%{tag.strip()}%"))
        needs_distinct = True

    if needs_distinct:
        photo_query = photo_query.distinct()

    has_metadata_filters = (
        (city and city.strip()) or cities or
        (scene and scene.strip()) or scenes or
        province or provinces or country or countries or
        (make and make.strip()) or makes or
        (model and model.strip()) or models or
        lat_min or lat_max or lng_min or lng_max or radius or center_lat or center_lng
    )

    if has_metadata_filters:
        # 得到候选 photo_id 子查询
        photo_subquery = photo_query.subquery()

        # 主查询：仅对候选照片做连表与剩余过滤
        query = (
            db.query(Photo)
            .join(photo_subquery, Photo.id == photo_subquery.c.id)
            .outerjoin(PhotoMetadata)
        )

        # 地理位置与标签过滤（PhotoMetadata 表）
        if cities:
            query = query.filter(PhotoMetadata.city.in_(cities))
        elif city is not None and city.strip():
            query = query.filter(PhotoMetadata.city.ilike(f"%{city.strip()}%"))

        if scenes:
            query = query.filter(PhotoMetadata.scene.has(Scene.name.in_(scenes)))
        elif scene is not None and scene.strip():
            query = query.filter(PhotoMetadata.scene.has(Scene.name.ilike(f"%{scene.strip()}%")))

        if provinces:
            query = query.filter(PhotoMetadata.province.in_(provinces))
        elif province:
            query = query.filter(PhotoMetadata.province.ilike(f"%{province.strip()}%"))

        if countries:
            query = query.filter(PhotoMetadata.country.in_(countries))
        elif country:
            query = query.filter(PhotoMetadata.country.ilike(f"%{country.strip()}%"))

        # Camera Make/Model Filters
        if makes:
            query = query.filter(PhotoMetadata.make.in_(makes))
        elif make and make.strip():
            query = query.filter(PhotoMetadata.make.ilike(f"%{make.strip()}%"))

        if models:
            query = query.filter(PhotoMetadata.model.in_(models))
        elif model and model.strip():
            query = query.filter(PhotoMetadata.model.ilike(f"%{model.strip()}%"))

        if lat_min is not None:
            query = query.filter(PhotoMetadata.latitude >= lat_min)
        if lat_max is not None:
            query = query.filter(PhotoMetadata.latitude <= lat_max)
        if lng_min is not None:
            query = query.filter(PhotoMetadata.longitude >= lng_min)
        if lng_max is not None:
            query = query.filter(PhotoMetadata.longitude <= lng_max)

        if radius is not None and center_lat is not None and center_lng is not None:
            distance_expr = 6371 * func.acos(
                func.cos(func.radians(PhotoMetadata.latitude)) *
                func.cos(func.radians(center_lat)) *
                func.cos(func.radians(PhotoMetadata.longitude) - func.radians(center_lng)) +
                func.sin(func.radians(PhotoMetadata.latitude)) *
                func.sin(func.radians(center_lat))
            )
            query = query.filter(distance_expr <= radius)
        if order_by == 'quality_score':
            query = query.outerjoin(
                ImageDescription, Photo.id == ImageDescription.photo_id
            ).order_by(
                ImageDescription.quality_score.desc().nulls_last()
            )
        elif order_by == 'memory_score':
            query = query.outerjoin(
                ImageDescription, Photo.id == ImageDescription.photo_id
            ).order_by(
                ImageDescription.memory_score.desc().nulls_last()
            )
        return query
    else:
        # 得到候选 photo_id 子查询
        photo_subquery = photo_query.subquery()

        # 主查询：仅对候选照片做连表与剩余过滤
        query = (
            db.query(Photo)
            .join(photo_subquery, Photo.id == photo_subquery.c.id)
        )
        return query


def get_all_photos(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    years: Optional[List[int]] = None,
    city: Optional[str] = None,
    cities: Optional[List[str]] = None,
    scene: Optional[str] = None,
    scenes: Optional[List[str]] = None,
    province: Optional[str] = None,
    provinces: Optional[List[str]] = None,
    country: Optional[str] = None,
    countries: Optional[List[str]] = None,
    make: Optional[str] = None,
    makes: Optional[List[str]] = None,
    model: Optional[str] = None,
    models: Optional[List[str]] = None,
    image_type: Optional[str] = None,
    image_types: Optional[List[str]] = None,
    file_type: Optional[str] = None,
    file_types: Optional[List[str]] = None,
    tag: Optional[str] = None,
    album_id: Optional[UUID] = None,
    album_ids: Optional[List[UUID]] = None,
    face_id: Optional[UUID] = None,
    face_ids: Optional[List[UUID]] = None,
    tag_id: Optional[UUID] = None,
    tag_ids: Optional[List[UUID]] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lng_min: Optional[float] = None,
    lng_max: Optional[float] = None,
    radius: Optional[float] = None,
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
    ids: Optional[List[UUID]] = None,
    order_by: Optional[str] = None,
    folder: Optional[str] = None,
    folder_direct: bool = False,
    folder_roots: Optional[List[str]] = None,
    user_id: UUID = None
):
    query = _build_photo_filter_query(
        db=db,
        start_time=start_time,
        end_time=end_time,
        years=years,
        city=city,
        cities=cities,
        scene=scene,
        scenes=scenes,
        province=province,
        provinces=provinces,
        country=country,
        countries=countries,
        make=make,
        makes=makes,
        model=model,
        models=models,
        image_type=image_type,
        image_types=image_types,
        file_type=file_type,
        file_types=file_types,
        tag=tag,
        album_id=album_id,
        album_ids=album_ids,
        face_id=face_id,
        face_ids=face_ids,
        tag_id=tag_id,
        tag_ids=tag_ids,
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
        radius=radius,
        center_lat=center_lat,
        center_lng=center_lng,
        ids=ids,
        order_by=order_by,
        folder=folder,
        folder_direct=folder_direct,
        folder_roots=folder_roots,
        user_id=user_id
    )

    # Optimization for user albums / eager load albums
    query = query.options(joinedload(Photo.albums))
    if not order_by or order_by == 'photo_time':
        # 按拍摄时间倒序
        query = query.order_by(Photo.photo_time.desc())
    return query.offset(skip).limit(limit).all()


def get_timeline_stats(
    db: Session,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    years: Optional[List[int]] = None,
    city: Optional[str] = None,
    cities: Optional[List[str]] = None,
    scene: Optional[str] = None,
    scenes: Optional[List[str]] = None,
    province: Optional[str] = None,
    provinces: Optional[List[str]] = None,
    country: Optional[str] = None,
    countries: Optional[List[str]] = None,
    make: Optional[str] = None,
    makes: Optional[List[str]] = None,
    model: Optional[str] = None,
    models: Optional[List[str]] = None,
    image_type: Optional[str] = None,
    image_types: Optional[List[str]] = None,
    file_type: Optional[str] = None,
    file_types: Optional[List[str]] = None,
    tag: Optional[str] = None,
    album_id: Optional[UUID] = None,
    album_ids: Optional[List[UUID]] = None,
    face_id: Optional[UUID] = None,
    face_ids: Optional[List[UUID]] = None,
    tag_id: Optional[UUID] = None,
    tag_ids: Optional[List[UUID]] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lng_min: Optional[float] = None,
    lng_max: Optional[float] = None,
    radius: Optional[float] = None,
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
    ids: Optional[List[UUID]] = None,
    folder: Optional[str] = None,
    folder_direct: bool = False,
    folder_roots: Optional[List[str]] = None,
    user_id: UUID = None
):
    query = _build_photo_filter_query(
        db=db,
        start_time=start_time,
        end_time=end_time,
        years=years,
        city=city,
        cities=cities,
        scene=scene,
        scenes=scenes,
        province=province,
        provinces=provinces,
        country=country,
        countries=countries,
        make=make,
        makes=makes,
        model=model,
        models=models,
        image_type=image_type,
        image_types=image_types,
        file_type=file_type,
        file_types=file_types,
        tag=tag,
        album_id=album_id,
        album_ids=album_ids,
        face_id=face_id,
        face_ids=face_ids,
        tag_id=tag_id,
        tag_ids=tag_ids,
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
        radius=radius,
        center_lat=center_lat,
        center_lng=center_lng,
        ids=ids,
        folder=folder,
        folder_direct=folder_direct,
        folder_roots=folder_roots,
        user_id=user_id
    )

    # 总数
    total = query.count()

    if total == 0:
        return {
            'total_photos': 0,
            'time_range': None,
            'timeline': []
        }

    # 按年-月-日分组
    # 使用 extract 保证跨数据库兼容性
    timeline_query = query.with_entities(
        func.extract('year', Photo.photo_time).label('year'),
        func.extract('month', Photo.photo_time).label('month'),
        func.extract('day', Photo.photo_time).label('day'),
        func.count(Photo.id).label('count')
    ).group_by(
        func.extract('year', Photo.photo_time),
        func.extract('month', Photo.photo_time),
        func.extract('day', Photo.photo_time)
    ).order_by(
        func.extract('year', Photo.photo_time).desc(),
        func.extract('month', Photo.photo_time).desc(),
        func.extract('day', Photo.photo_time).desc()
    ).all()

    timeline = []
    min_time = None
    max_time = None
    for y, m, d, c in timeline_query:
        if y is not None and m is not None and d is not None:
            timeline.append({
                'year': int(y),
                'month': int(m),
                'day': int(d),
                'count': c
            })
            dt = datetime(int(y), int(m), int(d))
            if min_time is None or dt < min_time:
                min_time = dt
            if max_time is None or dt > max_time:
                max_time = dt

    return {
        'total_photos': total,
        'time_range': {
            'start': min_time.isoformat() if min_time else None,
            'end': max_time.isoformat() if max_time else None
        },
        'timeline': timeline
    }


def get_photo(db: Session, photo_id: UUID, include_deleted: bool = False):
    query = db.query(Photo).filter(Photo.id == photo_id)
    if not include_deleted:
        query = query.filter(Photo.is_deleted == False)
    return query.first()


def create_photo(db: Session, photo: photo_schemas.PhotoCreate, album_id: Optional[UUID], file_path: str, photo_id: Optional[UUID] = None, user_id: UUID = None):
    db_photo = Photo(
        id=photo_id,
        file_path=file_path,
        file_type=photo.file_type,
        size=photo.size,
        width=photo.width,
        height=photo.height,
        duration=photo.duration,
        filename=photo.filename,
        photo_time=photo.photo_time or datetime.now(),
        owner_id=user_id
    )

    if album_id:
        album = get_album(db, album_id, user_id)
        if album:
            db_photo.albums.append(album)
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)

    if album_id:
        _update_album_photo_count(db, album_id)

    db.commit()

    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [db_photo.id])

    return db_photo


import os
import traceback

def update_photo(db: Session, photo_id: UUID, photo_update: photo_schemas.PhotoUpdate, user_id: UUID = None):
    db_photo = get_photo(db, photo_id)
    if db_photo:
        if user_id is not None and db_photo.owner_id != user_id:
            return None

        file_path = db_photo.file_path

        if photo_update.modify_original_file and os.path.exists(file_path):
            try:
                if photo_update.photo_time is not None:
                    timestamp = photo_update.photo_time.timestamp()
                    os.utime(file_path, (timestamp, timestamp))

                # 修改文件名
                if photo_update.filename is not None and photo_update.filename != db_photo.filename:
                    dirname = os.path.dirname(file_path)
                    _, ext = os.path.splitext(file_path)
                    new_filename = photo_update.filename
                    if not new_filename.lower().endswith(ext.lower()):
                        new_filename += ext
                    
                    new_file_path = os.path.join(dirname, new_filename)
                    if not os.path.exists(new_file_path):
                        os.rename(file_path, new_file_path)
                        db_photo.file_path = new_file_path
                        # 更新 filename 为带后缀的实际文件名
                        photo_update.filename = new_filename
            except Exception as e:
                print(f"Failed to modify original file: {e}")
                traceback.print_exc()

        if photo_update.filename is not None:
            db_photo.filename = photo_update.filename
        if photo_update.photo_time is not None:
            db_photo.photo_time = photo_update.photo_time
        db.commit()
        db.refresh(db_photo)
        if user_id:
            from app.crud.album import trigger_conditional_albums_update
            trigger_conditional_albums_update(db, user_id, [photo_id])
    return db_photo


def replace_photo_file(db: Session, db_photo: Photo, new_file_path: str, user_id: UUID):
    old_file_path = db_photo.file_path

    # Delete old file if different from new
    if old_file_path != new_file_path and os.path.exists(old_file_path):
        try:
            os.remove(old_file_path)
        except Exception as e:
            logging.getLogger("app.crud.photo").warning(f"Failed to delete old file {old_file_path}: {e}")

    # Update file path and filename
    new_filename = os.path.basename(new_file_path)
    db_photo.file_path = new_file_path
    db_photo.filename = new_filename

    # Delete old thumbnails and regenerate
    storage.delete_thumbnails(user_id, db_photo.id)
    storage.generate_thumbnail(user_id, new_file_path, db_photo.id)

    # Update dimensions and size
    width, height, _ = storage.get_image_dimensions(new_file_path)
    size = storage.get_file_size(new_file_path)
    if width is not None:
        db_photo.width = width
    if height is not None:
        db_photo.height = height
    if size is not None:
        db_photo.size = size

    db.commit()
    db.refresh(db_photo)

    # Trigger re-processing tasks (face, OCR, description may be stale)
    from app.service.task_manager import TaskManager
    from app.db.models.task import TaskType
    TaskManager.get_instance().add_tasks(db, [
        {'type': TaskType.RECOGNIZE_FACE, 'payload': {'photo_id': str(db_photo.id), 'file_path': new_file_path, 'user_id': str(user_id)}},
        {'type': TaskType.OCR, 'payload': {'photo_id': str(db_photo.id), 'file_path': new_file_path, 'user_id': str(user_id)}},
        {'type': TaskType.VISUAL_DESCRIPTION, 'payload': {'photo_id': str(db_photo.id), 'file_path': new_file_path, 'user_id': str(user_id)}},
    ])

    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [db_photo.id])

    return db_photo


def get_photos_by_ids(db: Session, photo_ids: List[UUID], user_id: UUID = None, include_deleted: bool = False):
    query = db.query(Photo).filter(Photo.id.in_(photo_ids))
    if not include_deleted:
        query = query.filter(Photo.is_deleted == False)
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
    return query.all()


def delete_photo(db: Session, photo_id: UUID, is_delete_file = False, user_id: UUID = None):
    db_photo = get_photo(db, photo_id)
    if db_photo:
        if user_id is not None and db_photo.owner_id != user_id:
            return None
        affected_album_ids = [album.id for album in db_photo.albums]
        if is_delete_file:
            storage.delete_file(user_id, db_photo.file_path, db_photo.id, db_photo.file_type == FileType.live_photo)
        else:
            storage.delete_thumbnails(user_id, db_photo.id)
        for album_id in affected_album_ids:
            _update_album_photo_count(db, album_id)
            
        remove_photo_from_clusters(db, db_photo.id)
        
        db.delete(db_photo)
        db.commit()
    return db_photo


def batch_soft_delete_photos(db: Session, photo_ids: List[UUID], user_id: UUID = None):
    query = db.query(Photo).options(joinedload(Photo.albums)).filter(Photo.id.in_(photo_ids))
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
    
    photos = query.all()
    count = len(photos)
    
    for photo in photos:
        photo.is_deleted = True
        photo.deleted_at = datetime.now()
        
    db.commit()
    
    # Update album counts
    affected_album_ids = set()
    for photo in photos:
        for album in photo.albums:
            affected_album_ids.add(album.id)
            
    for album_id in affected_album_ids:
        _update_album_photo_count(db, album_id)
        
    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [])
        
    return count

def restore_photos(db: Session, photo_ids: List[UUID], user_id: UUID = None):
    query = db.query(Photo).options(joinedload(Photo.albums)).filter(Photo.id.in_(photo_ids), Photo.is_deleted == True)
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
        
    photos = query.all()
    count = len(photos)
    
    for photo in photos:
        photo.is_deleted = False
        photo.deleted_at = None
        
    db.commit()
    
    # Update album counts
    affected_album_ids = set()
    for photo in photos:
        for album in photo.albums:
            affected_album_ids.add(album.id)
            
    for album_id in affected_album_ids:
        _update_album_photo_count(db, album_id)
        
    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [])
        
    return count

def get_recycle_bin_photos(db: Session, user_id: UUID, skip: int = 0, limit: int = 100):
    query = db.query(Photo).filter(Photo.owner_id == user_id, Photo.is_deleted == True)
    query = query.order_by(Photo.deleted_at.desc())
    if limit == 0:
        return query.offset(skip).all()
    return query.offset(skip).limit(limit).all()

def batch_delete_photos_db(db: Session, photo_ids: List[UUID], is_delete_file = False, user_id: UUID = None):
    # Get photos with albums to know which albums to update
    query = db.query(Photo).options(joinedload(Photo.albums), joinedload(Photo.faces)).filter(Photo.id.in_(photo_ids))
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)

    photos = query.all()
    affected_album_ids = set()
    for photo in photos:
        for album in photo.albums:
            affected_album_ids.add(album.id)

        # Handle face deletion dependencies
        for face in photo.faces:
            crud_face.handle_face_deletion_dependency(db, face)

    count = len(photos)
    for photo in photos:
        print(photo.file_path, photo.file_type, photo.file_type == FileType.live_photo)
        if is_delete_file:
            storage.delete_file(user_id, photo.file_path, photo.id, photo.file_type == FileType.live_photo)
        else:
            storage.delete_thumbnails(user_id, photo.id)
            
        remove_photo_from_clusters(db, photo.id)
        
        db.delete(photo)
    db.commit()

    # Update counts
    for album_id in affected_album_ids:
        _update_album_photo_count(db, album_id)

    if user_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user_id, [])

    return count


def get_on_this_day_photos(db: Session, user_id: UUID, month: int, day: int, year: int, limit: int = 10):
    """
    获取“那年今日”的照片：
    1. 过滤：同月同日，排除截图，排除当年
    2. 排序：AI 评分 (memory_score + quality_score) -> 向量相似度 (POSITIVE_SENTIMENT_VECTOR) -> 时间倒序
    3. 去重：去除相似度高的照片，相似照片只返回一张
    """
    import numpy as np

    # 排序 1: AI 评分 (memory_score + quality_score)
    ai_score = func.coalesce(ImageDescription.memory_score, 0) + func.coalesce(ImageDescription.quality_score, 0)
    
    # 在 SQLAlchemy 中查询多列并且包含 list/numpy.ndarray 类型时，.all() 会尝试对结果去重（如果是 tuple 的话）
    # 但如果包含 numpy.ndarray 就会报 unhashable type 错误，所以不能直接 select 两列
    # 这里我们只查询 Photo 对象，然后遍历时通过 photo.image_vector (或手动 join 出来的字段) 获取 embedding
    
    photo_query = db.query(Photo).options(
        joinedload(Photo.metadata_info),
        joinedload(Photo.image_description),
        # 不能用 joinedload ImageVector，因为我们只想要 embedding 并且上面外连接了，
        # 为了避免 hash 问题，我们直接用外连接然后在后面查询中只选 Photo。
        # 实际上在 Photo 对象上没有直接映射 image_vector，如果有，可以直接加载。
        # 我们修改查询：只选择 Photo 对象，但是保留 outerjoin 以便排序
    ).outerjoin(ImageDescription).outerjoin(ImageVector).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        func.extract('month', Photo.photo_time) == month,
        func.extract('day', Photo.photo_time) == day,
        func.extract('year', Photo.photo_time) != year,
        Photo.image_type != ImageType.SCREENSHOT,
        Photo.file_type != FileType.video
    )
    
    # 重新应用排序
    if POSITIVE_SENTIMENT_VECTOR.embedding:
        distance = ImageVector.embedding.cosine_distance(POSITIVE_SENTIMENT_VECTOR.embedding)
        photo_query = photo_query.order_by(ai_score.desc(), distance.asc(), Photo.photo_time.desc())
    else:
        photo_query = photo_query.order_by(ai_score.desc(), Photo.photo_time.desc())

    # 获取更多候选照片
    candidates = photo_query.limit(limit * 5).all()

    # 如果需要用到 embedding 进行去重，我们需要额外查询这批照片的 embeddings
    candidate_ids = [photo.id for photo in candidates]
    
    embeddings_map = {}
    if candidate_ids:
        # 只取 photo_id + embedding 两列，避免拉回整行 ORM 对象（含其他大列）
        vector_rows = db.query(
            ImageVector.photo_id, ImageVector.embedding
        ).filter(ImageVector.photo_id.in_(candidate_ids)).all()
        embeddings_map = {pid: emb for pid, emb in vector_rows}

    def cosine_similarity(vec1, vec2):
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    result_photos = []
    selected_embeddings = []

    for photo in candidates:
        if len(result_photos) >= limit:
            break
            
        embedding = embeddings_map.get(photo.id)
        is_similar = False
        
        if embedding is not None:
            for sel_emb in selected_embeddings:
                if sel_emb is not None:
                    sim = cosine_similarity(embedding, sel_emb)
                    if sim > 0.90:  # 相似度大于0.9认为是相似照片
                        is_similar = True
                        break
        
        if not is_similar:
            result_photos.append(photo)
            selected_embeddings.append(embedding)

    return result_photos

def get_random_photos(db: Session, user_id: UUID, limit: int = 10):
    query = db.query(Photo).options(
        joinedload(Photo.metadata_info),
        joinedload(Photo.image_description)
    ).filter(Photo.owner_id == user_id, Photo.is_deleted == False)
    query = query.order_by(func.random())
    return query.limit(limit).all()
