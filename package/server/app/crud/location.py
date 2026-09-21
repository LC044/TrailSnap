from sqlalchemy.orm import Session, joinedload, contains_eager
from uuid import UUID
from sqlalchemy import and_, func, desc, extract, case, or_
from math import asin, ceil, cos, radians, sin, sqrt
from datetime import date
import numpy as np
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.image_vector import ImageVector
from app.db.models.scene import Scene
from app.db.sql import as_date_string, date_only


TIME_COMPARE_RADIUS_M = 200
TIME_COMPARE_SCENE_DISTANCE_M = 500
TIME_COMPARE_VISUAL_WEIGHT = 0.90
TIME_COMPARE_DISTANCE_WEIGHT = 0.1
TIME_COMPARE_TIME_WEIGHT = 0.15
TIME_COMPARE_MIN_VISUAL_SIMILARITY = 0.45


def _valid_coordinates(latitude, longitude):
    if latitude is None or longitude is None:
        return False
    latitude = float(latitude)
    longitude = float(longitude)
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def _nearby_time_compare_rows(
    db: Session,
    owner_id: UUID,
    latitude,
    longitude,
    radius_m: int = TIME_COMPARE_RADIUS_M,
    year: int = None,
    visit_date: date = None,
):
    """Fetch owner photos within an exact GPS radius using an indexed bounding box first."""
    if not _valid_coordinates(latitude, longitude):
        return []

    center_lat = float(latitude)
    center_lng = float(longitude)
    radius_km = radius_m / 1000
    lat_delta = radius_km / 111.32
    lng_scale = max(abs(cos(radians(center_lat))), 0.01)
    lng_delta = radius_km / (111.32 * lng_scale)

    query = db.query(Photo, PhotoMetadata).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == owner_id,
        Photo.is_deleted == False,
        Photo.photo_time.isnot(None),
        Photo.file_type != FileType.video,
        PhotoMetadata.latitude.between(center_lat - lat_delta, center_lat + lat_delta),
        PhotoMetadata.longitude.between(center_lng - lng_delta, center_lng + lng_delta),
    )
    if year is not None:
        query = query.filter(extract('year', Photo.photo_time) == year)
    if visit_date is not None:
        query = query.filter(func.date(Photo.photo_time) == visit_date.isoformat())

    candidates = query.order_by(Photo.photo_time.asc(), Photo.id.asc()).all()
    return [
        (photo, metadata)
        for photo, metadata in candidates
        if _haversine_km(
            center_lat,
            center_lng,
            float(metadata.latitude),
            float(metadata.longitude),
        ) <= radius_km
    ]


def _cosine_similarity(left, right):
    if left is None or right is None:
        return None
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    if denominator == 0:
        return None
    return max(0.0, min(1.0, float(np.dot(left, right) / denominator)))


def _photo_orientation(photo):
    if not photo.width or not photo.height:
        return None
    ratio = photo.width / photo.height
    if ratio > 1.1:
        return "landscape"
    if ratio < 0.9:
        return "portrait"
    return "square"


def _orientation_compatible(left_photo, right_photo):
    left = _photo_orientation(left_photo)
    right = _photo_orientation(right_photo)
    return left is None or right is None or left == right


def _comparison_score(
    reference_photo,
    reference_metadata,
    candidate_photo,
    candidate_metadata,
    reference_embedding=None,
    candidate_embedding=None,
    distance_limit_m: int = TIME_COMPARE_RADIUS_M,
):
    """Rank comparison value: matching view first, then proximity and time span."""
    similarity = _cosine_similarity(reference_embedding, candidate_embedding)
    if _valid_coordinates(reference_metadata.latitude, reference_metadata.longitude) and _valid_coordinates(
        candidate_metadata.latitude, candidate_metadata.longitude
    ):
        distance_m = _haversine_km(
            float(reference_metadata.latitude),
            float(reference_metadata.longitude),
            float(candidate_metadata.latitude),
            float(candidate_metadata.longitude),
        ) * 1000
        distance_score = max(0.0, 1.0 - distance_m / max(distance_limit_m, 1))
    else:
        distance_score = 0.5

    days = abs((candidate_photo.photo_time - reference_photo.photo_time).total_seconds()) / 86400
    time_score = min(days / 180, 1.0)
    if similarity is None:
        # Missing embeddings must not make an otherwise useful GPS match vanish.
        return 0.55 * distance_score + 0.45 * time_score
    return (
        TIME_COMPARE_VISUAL_WEIGHT * similarity
        + TIME_COMPARE_DISTANCE_WEIGHT * distance_score
        + TIME_COMPARE_TIME_WEIGHT * time_score
    )


def _embedding_map(db: Session, photo_ids):
    if not photo_ids:
        return {}
    return dict(db.query(ImageVector.photo_id, ImageVector.embedding).filter(
        ImageVector.photo_id.in_(photo_ids)
    ).all())


def _rank_rows_for_reference(db: Session, rows, reference_row, distance_limit_m=TIME_COMPARE_RADIUS_M):
    if not reference_row:
        return rows
    reference_photo, reference_metadata = reference_row
    rows = [row for row in rows if _orientation_compatible(reference_photo, row[0])]
    embeddings = _embedding_map(db, [reference_photo.id, *[photo.id for photo, _ in rows]])
    return sorted(
        rows,
        key=lambda row: (
            _comparison_score(
                reference_photo,
                reference_metadata,
                row[0],
                row[1],
                embeddings.get(reference_photo.id),
                embeddings.get(row[0].id),
                distance_limit_m,
            ),
            row[0].photo_time,
        ),
        reverse=True,
    )


def _recommended_pair(db: Session, rows, source_row=None, distance_limit_m=TIME_COMPARE_RADIUS_M):
    if len({photo.photo_time.date() for photo, _ in rows}) < 2:
        return None, None

    if source_row:
        source_photo = source_row[0]
        candidates = [
            row for row in rows
            if row[0].photo_time.date() != source_photo.photo_time.date()
            and _orientation_compatible(source_photo, row[0])
        ]
        ranked = _rank_rows_for_reference(db, candidates, source_row, distance_limit_m)
        if not ranked:
            return None, None
        partner = ranked[0][0]
        return (partner, source_photo) if partner.photo_time < source_photo.photo_time else (source_photo, partner)

    # Without an anchor, find the strongest cross-year pair. Keep the search
    # bounded for very large Scenes while retaining every year and both ends.
    if len(rows) > 200:
        rows_by_year = {}
        for row in rows:
            rows_by_year.setdefault(row[0].photo_time.year, []).append(row)
        quota = max(1, 200 // len(rows_by_year))
        sampled = []
        for year_rows in rows_by_year.values():
            if len(year_rows) <= quota:
                sampled.extend(year_rows)
                continue
            step = len(year_rows) / quota
            sampled.extend(year_rows[min(int(index * step), len(year_rows) - 1)] for index in range(quota))
        rows = sampled[:200]
    embeddings = _embedding_map(db, [photo.id for photo, _ in rows])
    best = None
    for index, left_row in enumerate(rows):
        for right_row in rows[index + 1:]:
            if left_row[0].photo_time.date() == right_row[0].photo_time.date():
                continue
            if not _orientation_compatible(left_row[0], right_row[0]):
                continue
            score = _comparison_score(
                left_row[0], left_row[1], right_row[0], right_row[1],
                embeddings.get(left_row[0].id), embeddings.get(right_row[0].id),
                distance_limit_m,
            )
            if best is None or score > best[0]:
                best = (score, left_row[0], right_row[0])
    if not best:
        return None, None
    earlier, later = best[1], best[2]
    return (earlier, later) if earlier.photo_time <= later.photo_time else (later, earlier)


def _pair_visual_similarity(db: Session, left_photo, right_photo):
    if not left_photo or not right_photo:
        return None
    embeddings = _embedding_map(db, [left_photo.id, right_photo.id])
    return _cosine_similarity(embeddings.get(left_photo.id), embeddings.get(right_photo.id))


def _visible_scene(db: Session, owner_id: UUID, scene_id: UUID):
    return db.query(Scene).filter(
        Scene.id == scene_id,
        or_(Scene.owner_id == owner_id, Scene.owner_id.is_(None)),
    ).first()


def get_time_compare_summary(
    db: Session,
    owner_id: UUID,
    scene_id: UUID = None,
    photo_id: UUID = None,
):
    """Return a Scene comparison, or a GPS-nearby comparison for an unassigned photo."""
    source_photo = None
    source_metadata = None
    if photo_id:
        source_row = db.query(Photo, PhotoMetadata).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        ).filter(
            Photo.id == photo_id,
            Photo.owner_id == owner_id,
            Photo.is_deleted == False,
        ).first()
        if not source_row:
            return None
        source_photo, source_metadata = source_row
        # A canonical Scene always wins. GPS proximity is only the fallback for
        # photos that have not been assigned to a Scene.
        scene_id = source_metadata.scene_id

    if not scene_id and not source_photo:
        return None

    scene = None
    match_type = "scene"
    radius_m = None
    if scene_id:
        scene = _visible_scene(db, owner_id, scene_id)
        if not scene:
            return None
        scene_rows = db.query(Photo, PhotoMetadata).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        ).filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted == False,
            Photo.photo_time.isnot(None),
            Photo.file_type != FileType.video,
            PhotoMetadata.scene_id == scene.id,
        ).order_by(Photo.photo_time.asc(), Photo.id.asc()).all()
        rows = scene_rows
    else:
        match_type = "nearby_gps"
        radius_m = TIME_COMPARE_RADIUS_M
        if not _valid_coordinates(source_metadata.latitude, source_metadata.longitude):
            return {
                "eligible": False,
                "reason": "precise_location_required",
                "match_type": match_type,
                "source_photo_id": source_photo.id,
                "source_photo_year": source_photo.photo_time.year if source_photo.photo_time else None,
                "years": [],
            }
        rows = _nearby_time_compare_rows(
            db,
            owner_id,
            source_metadata.latitude,
            source_metadata.longitude,
            radius_m,
        )

    grouped = {}
    city = None
    for photo, metadata in rows:
        city = city or metadata.city
        grouped.setdefault(photo.photo_time.year, []).append(photo)

    years = []
    for year in sorted(grouped):
        photos = grouped[year]
        years.append({
            "year": year,
            "photo_count": len(photos),
            "first_date": photos[0].photo_time,
            "last_date": photos[-1].photo_time,
            "cover": photos[-1],
        })

    visits = []
    visits_grouped = {}
    for photo, _ in rows:
        visits_grouped.setdefault(photo.photo_time.date(), []).append(photo)
    for captured_date in sorted(visits_grouped):
        photos = visits_grouped[captured_date]
        visits.append({
            "date": captured_date,
            "photo_count": len(photos),
            "first_time": photos[0].photo_time,
            "last_time": photos[-1].photo_time,
            "cover": photos[-1],
        })

    recommended_earlier, recommended_later = _recommended_pair(
        db,
        rows,
        (source_photo, source_metadata) if source_photo else None,
        radius_m or TIME_COMPARE_SCENE_DISTANCE_M,
    )
    visual_similarity = _pair_visual_similarity(db, recommended_earlier, recommended_later)
    eligible = len(visits) >= 2 and recommended_earlier is not None and recommended_later is not None
    reason = None if eligible else "multiple_visits_required"
    if len(visits) >= 2 and (recommended_earlier is None or recommended_later is None):
        reason = "orientation_match_required"
    if eligible and visual_similarity is not None and visual_similarity < TIME_COMPARE_MIN_VISUAL_SIMILARITY:
        eligible = False
        reason = "similar_view_required"
    return {
        "eligible": eligible,
        "reason": reason,
        "match_type": match_type,
        "radius_m": radius_m,
        "visual_similarity": visual_similarity,
        "scene_id": scene.id if scene else None,
        "location_name": scene.name if scene else f"{source_metadata.district or source_metadata.city or '照片位置'}附近",
        "location_address": scene.address if scene else None,
        "city": city,
        "source_photo_id": source_photo.id if source_photo else None,
        "source_photo_year": source_photo.photo_time.year if source_photo and source_photo.photo_time else None,
        "years": years,
        "visits": visits,
        "first_photo": recommended_earlier,
        "latest_photo": recommended_later,
    }


def get_time_compare_photos(
    db: Session,
    owner_id: UUID,
    scene_id: UUID = None,
    year: int = None,
    skip: int = 0,
    limit: int = 100,
    photo_id: UUID = None,
    reference_photo_id: UUID = None,
    radius_m: int = TIME_COMPARE_RADIUS_M,
    visit_date: date = None,
):
    reference_row = None
    if reference_photo_id:
        reference_row = db.query(Photo, PhotoMetadata).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        ).filter(
            Photo.id == reference_photo_id,
            Photo.owner_id == owner_id,
            Photo.is_deleted == False,
        ).first()

    if scene_id:
        scene = _visible_scene(db, owner_id, scene_id)
        if not scene:
            return None
        rows = db.query(Photo, PhotoMetadata).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        ).filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted == False,
            Photo.photo_time.isnot(None),
            Photo.file_type != FileType.video,
            PhotoMetadata.scene_id == scene.id,
        ).order_by(Photo.photo_time.asc(), Photo.id.asc()).all()
        if visit_date is not None:
            rows = [row for row in rows if row[0].photo_time.date() == visit_date]
        elif year is not None:
            rows = [row for row in rows if row[0].photo_time.year == year]
        rows = _rank_rows_for_reference(db, rows, reference_row, TIME_COMPARE_SCENE_DISTANCE_M)
        return [photo for photo, _ in rows][skip:skip + limit]

    if not photo_id:
        return None
    source = db.query(Photo, PhotoMetadata).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.id == photo_id,
        Photo.owner_id == owner_id,
        Photo.is_deleted == False,
    ).first()
    if not source:
        return None
    _, metadata = source
    if not _valid_coordinates(metadata.latitude, metadata.longitude):
        return []
    rows = _nearby_time_compare_rows(
        db,
        owner_id,
        metadata.latitude,
        metadata.longitude,
        radius_m,
        year,
        visit_date,
    )
    rows = _rank_rows_for_reference(db, rows, reference_row or source, radius_m)
    return [photo for photo, _ in rows][skip:skip + limit]

def get_location_years(db: Session, owner_id: UUID):
    has_location = or_(
        and_(PhotoMetadata.latitude.isnot(None), PhotoMetadata.longitude.isnot(None)),
        and_(PhotoMetadata.country.isnot(None), PhotoMetadata.country != ''),
        and_(PhotoMetadata.province.isnot(None), PhotoMetadata.province != ''),
        and_(PhotoMetadata.city.isnot(None), PhotoMetadata.city != ''),
        and_(PhotoMetadata.district.isnot(None), PhotoMetadata.district != ''),
        PhotoMetadata.scene_id.isnot(None),
    )
    years = db.query(extract('year', Photo.photo_time))\
        .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
        .filter(
            Photo.photo_time.isnot(None),
            Photo.is_deleted == False,
            Photo.owner_id == owner_id,
            has_location,
        )\
        .distinct()\
        .order_by(desc(extract('year', Photo.photo_time)))\
        .all()
    return [int(y[0]) for y in years if y[0] is not None]

def get_locations(db: Session, owner_id: UUID, level: str = 'city', skip: int = 0, limit: int = 100, start_date: str = None, end_date: str = None):
    is_scene = False
    if level == 'city':
        group_col = PhotoMetadata.city
    elif level == 'province':
        group_col = PhotoMetadata.province
    elif level == 'district':
        group_col = PhotoMetadata.district
    elif level == 'scene':
        group_col = Scene.name
        is_scene = True
    else:
        return []

    # Group by location and count
    if is_scene:
        query = db.query(
            Scene.name,
            Scene.id,
            Scene.is_custom,
            func.count(Photo.id).label('count')
        ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False).outerjoin(
            PhotoMetadata, Scene.id == PhotoMetadata.scene_id
        ).outerjoin(
            Photo, Photo.id == PhotoMetadata.photo_id
        )
    else:
        query = db.query(
            group_col,
            func.count(Photo.id).label('count')
        ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        )

    # if is_scene:
    #     query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if is_scene:
        # For scenes, we don't filter out None/empty names if they are defined in the Scene table
        pass
    else:
        query = query.filter(
            group_col.is_not(None),
            group_col != ''
        )

    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    if is_scene:
        query = query.group_by(Scene.name, Scene.id, Scene.is_custom)
    else:
        query = query.group_by(group_col)
    
    query = query.order_by(
        desc('count')
    ).offset(skip).limit(limit)

    results = query.all()

    if not results:
        return []

    # Get list of location names from current page results
    names = [r[0] for r in results]

    # Batch fetch cover photos using DISTINCT ON to avoid N+1 queries
    # Optimized for PostgreSQL
    cover_query = db.query(
        Photo,
        group_col
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    )

    if is_scene:
        cover_query = cover_query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if start_date:
        cover_query = cover_query.filter(Photo.photo_time >= start_date)
    if end_date:
        cover_query = cover_query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    covers = cover_query.filter(
        group_col.in_(names)
    ).distinct(
        group_col
    ).order_by(
        group_col,
        desc(Photo.photo_time)
    ).all()

    # Map location name to cover photo
    cover_map = {loc_name: photo for photo, loc_name in covers}

    locations = []
    if is_scene:
        for name, sid, is_custom, count in results:
            locations.append({
                "name": name,
                "id": str(sid),
                "is_custom": is_custom,
                "level": level,
                "count": count,
                "cover": cover_map.get(name)
            })
    else:
        for name, count in results:
            locations.append({
                "name": name,
                "level": level,
                "count": count,
                "cover": cover_map.get(name)
            })
        
    return locations

def get_location_photos(db: Session, owner_id: UUID, name: str, level: str = 'city', skip: int = 0, limit: int = 50, start_date: str = None, end_date: str = None, scene_id: UUID = None):
    # 使用 join 配合 contains_eager 替代 joinedload，避免产生重复的 JOIN 查询，提升性能
    query = db.query(Photo).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
    query = query.filter(Photo.owner_id == owner_id, Photo.is_deleted == False)

    if level == 'city':
        col = PhotoMetadata.city
    elif level == 'province':
        col = PhotoMetadata.province
    elif level == 'district':
        col = PhotoMetadata.district
    elif level == 'scene':
        if scene_id:
            col = PhotoMetadata.scene_id
        else:
            col = Scene.name
            query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)
    else:
        return []
        
    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    return query.filter(
        col == (scene_id if level == 'scene' and scene_id else name)
    ).order_by(
        desc(Photo.photo_time)
    ).offset(skip).limit(limit).all()

def get_map_markers(db: Session, owner_id: UUID, start_date: str = None, end_date: str = None):
    query = db.query(
        Photo.id,
        PhotoMetadata.latitude,
        PhotoMetadata.longitude
    ).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
     .filter(PhotoMetadata.latitude.isnot(None))\
     .filter(PhotoMetadata.longitude.isnot(None))\
     .filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
     
    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    results = query.all()
     
    return [
        {"id": str(r[0]), "lat": float(r[1]), "lng": float(r[2])}
        for r in results
    ]

def get_timeline_nodes(db: Session, owner_id: UUID, level: str = 'city', skip: int = 0, limit: int = 100, start_date: str = None, end_date: str = None):
    from app.schemas.location import TimelineResponse, TimelineNode
    from sqlalchemy import cast, String

    date_expr = date_only(db, Photo.photo_time)

    if level == 'province':
        base_loc = func.nullif(PhotoMetadata.province, '')
        base_level = 'province'
    elif level == 'district':
        base_loc = func.nullif(PhotoMetadata.district, '')
        base_level = 'district'
    elif level == 'scene':
        base_loc = func.nullif(Scene.name, '')
        base_level = 'scene'
    else: # default 'city'
        base_loc = func.nullif(PhotoMetadata.city, '')
        base_level = 'city'

    if level == 'scene':
        loc_name_expr = func.coalesce(
            func.nullif(Scene.name, ''),
            func.nullif(PhotoMetadata.city, ''),
            func.nullif(PhotoMetadata.district, ''),
            func.nullif(PhotoMetadata.province, ''),
            '未知位置'
        )
        level_expr = case(
            (func.nullif(Scene.name, '').isnot(None), 'scene'),
            (func.nullif(PhotoMetadata.city, '').isnot(None), 'city'),
            (func.nullif(PhotoMetadata.district, '').isnot(None), 'district'),
            (func.nullif(PhotoMetadata.province, '').isnot(None), 'province'),
            else_='city'
        )
    else:
        loc_name_expr = func.coalesce(
            func.nullif(Scene.name, ''),
            base_loc,
            '未知位置'
        )
        level_expr = case(
            (func.nullif(Scene.name, '').isnot(None), 'scene'),
            (base_loc.isnot(None), base_level),
            else_=base_level
        )

    query = db.query(
        date_expr.label('date'),
        loc_name_expr.label('loc_name'),
        level_expr.label('level'),
        func.count(Photo.id).label('photo_count'),
        func.avg(PhotoMetadata.latitude).label('lat'),
        func.avg(PhotoMetadata.longitude).label('lng'),
        func.max(cast(Photo.id, String)).label('cover_id'),
        func.min(Photo.photo_time).label('start_time'),
        func.max(Photo.photo_time).label('end_time')
    ).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id) \
     .outerjoin(Scene, PhotoMetadata.scene_id == Scene.id) \
     .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
     .filter(PhotoMetadata.latitude.isnot(None)) \
     .filter(PhotoMetadata.longitude.isnot(None)) \
     .filter(Photo.photo_time.isnot(None))

    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    query = query.group_by(date_expr, loc_name_expr, level_expr) \
                 .order_by(desc(func.max(Photo.photo_time)))

    results = query.all()
    nodes = []

    for row in results:
        date_str = as_date_string(row.date)
        loc_name = row.loc_name
        level = row.level
        lat = float(row.lat)
        lng = float(row.lng)
        count = row.photo_count
        cover_id = row.cover_id
        start_time = getattr(row, 'start_time', None)
        end_time = getattr(row, 'end_time', None)

        if not nodes:
            nodes.append(TimelineNode(
                startDate=date_str,
                endDate=date_str,
                locationName=loc_name,
                level=level,
                lat=lat,
                lng=lng,
                photoCount=count,
                coverId=cover_id,
                startTime=start_time,
                endTime=end_time
            ))
            continue

        last_node = nodes[-1]

        if last_node.locationName == loc_name:
            last_node.startDate = min(last_node.startDate, date_str)
            last_node.endDate = max(last_node.endDate, date_str)
            if start_time and (last_node.startTime is None or start_time < last_node.startTime):
                last_node.startTime = start_time
            if end_time and (last_node.endTime is None or end_time > last_node.endTime):
                last_node.endTime = end_time
            # 更新平均经纬度
            total_lat = (last_node.lat * last_node.photoCount) + (lat * count)
            total_lng = (last_node.lng * last_node.photoCount) + (lng * count)
            last_node.photoCount += count
            last_node.lat = total_lat / last_node.photoCount
            last_node.lng = total_lng / last_node.photoCount
        else:
            nodes.append(TimelineNode(
                startDate=date_str,
                endDate=date_str,
                locationName=loc_name,
                level=level,
                lat=lat,
                lng=lng,
                photoCount=count,
                coverId=cover_id,
                startTime=start_time,
                endTime=end_time
            ))

    total_nodes = len(nodes)
    paginated_nodes = nodes[skip:skip + limit]

    return TimelineResponse(nodes=paginated_nodes, total=total_nodes)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance between two GPS points."""
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(a)))


def get_trajectory_points(
    db: Session,
    owner_id: UUID,
    start_date: str,
    end_date: str,
    max_points: int = 360,
):
    """Return chronologically ordered GPS points with stationary bursts collapsed.

    Photos within 60 metres of the previous retained point are represented by one
    weighted point. A second contiguous bucket pass limits payload size while
    preserving route order, first/last time and total photo counts.
    """
    from app.schemas.location import TrajectoryPoint, TrajectoryResponse

    rows = db.query(
        Photo.id,
        Photo.photo_time,
        PhotoMetadata.latitude,
        PhotoMetadata.longitude,
        PhotoMetadata.province,
        PhotoMetadata.city,
        PhotoMetadata.district,
        Scene.name.label('scene_name'),
    ).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).outerjoin(
        Scene, PhotoMetadata.scene_id == Scene.id
    ).filter(
        Photo.owner_id == owner_id,
        Photo.is_deleted == False,
        Photo.photo_time.isnot(None),
        PhotoMetadata.latitude.isnot(None),
        PhotoMetadata.longitude.isnot(None),
        Photo.photo_time >= start_date,
        Photo.photo_time <= f"{end_date} 23:59:59",
    ).order_by(Photo.photo_time.asc()).all()

    collapsed = []
    for row in rows:
        lat = float(row.latitude)
        lng = float(row.longitude)
        scene_name = getattr(row, 'scene_name', None)
        district = getattr(row, 'district', None)
        city = getattr(row, 'city', None)
        province = getattr(row, 'province', None)
        location_name = scene_name or district or city or province or 'GPS 位置'
        level = 'scene' if scene_name else 'district' if district else 'city' if city else 'province'

        if collapsed and _haversine_km(collapsed[-1]['lat'], collapsed[-1]['lng'], lat, lng) <= 0.06:
            point = collapsed[-1]
            count = point['photoCount'] + 1
            point['lat'] = (point['lat'] * point['photoCount'] + lat) / count
            point['lng'] = (point['lng'] * point['photoCount'] + lng) / count
            point['photoCount'] = count
            point['endAt'] = row.photo_time
            continue

        collapsed.append({
            'photoId': row.id,
            'capturedAt': row.photo_time,
            'endAt': row.photo_time,
            'lat': lat,
            'lng': lng,
            'photoCount': 1,
            'coverId': row.id,
            'locationName': location_name,
            'level': level,
        })

    sampled = len(collapsed) > max_points
    if sampled:
        bucket_size = ceil(len(collapsed) / max_points)
        compacted = []
        for offset in range(0, len(collapsed), bucket_size):
            bucket = collapsed[offset:offset + bucket_size]
            representative = dict(bucket[len(bucket) // 2])
            representative['capturedAt'] = bucket[0]['capturedAt']
            representative['endAt'] = bucket[-1]['endAt']
            representative['photoCount'] = sum(point['photoCount'] for point in bucket)
            compacted.append(representative)
        collapsed = compacted

    return TrajectoryResponse(
        points=[TrajectoryPoint(**point) for point in collapsed],
        totalPhotos=len(rows),
        sampled=sampled,
    )

def get_location_distribution(db: Session, owner_id: UUID, level: str = 'city', start_date: str = None, end_date: str = None):
    is_scene = False
    if level == 'city':
        group_col = PhotoMetadata.city
    elif level == 'province':
        group_col = PhotoMetadata.province
    elif level == 'district':
        group_col = PhotoMetadata.district
    elif level == 'scene':
        group_col = Scene.name
        is_scene = True
    else:
        return []

    # Group by location and count, no limit
    query = db.query(
        group_col.label('name'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    )

    if is_scene:
        query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    results = query.filter(
        group_col.is_not(None),
        group_col != ''
    ).group_by(
        group_col
    ).all()
    
    return [{"name": r[0], "count": r[1], "level": level} for r in results]

def get_location_statistics(db: Session, owner_id: UUID):
    # Filter photos by owner_id first
    subq = db.query(Photo.id).filter(Photo.owner_id == owner_id, Photo.is_deleted == False).subquery()
    
    # Query stats using the subquery
    result = db.query(
        func.count(func.distinct(case((PhotoMetadata.province != '', PhotoMetadata.province), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.city != '', PhotoMetadata.city), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.district != '', PhotoMetadata.district), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.country != '', PhotoMetadata.country), else_=None)))
    ).join(
        subq, PhotoMetadata.photo_id == subq.c.id
    ).first()
    
    return {
        "province_count": result[0] or 0,
        "city_count": result[1] or 0,
        "district_count": result[2] or 0,
        "country_count": result[3] or 0
    }

def search_locations(db: Session, owner_id: UUID, query: str, limit: int = 20):
    search = f"%{query}%"
    suggestions = []
    seen = set()

    # 1. Search Provinces
    provinces = db.query(PhotoMetadata.province)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False)\
        .filter(PhotoMetadata.province.ilike(search))\
        .filter(PhotoMetadata.province.isnot(None), PhotoMetadata.province != '')\
        .distinct()\
        .limit(10).all()
        
    for p in provinces:
        label = p[0]
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": label,
                    "city": "",
                    "district": ""
                }
            })
            
    # 2. Search Cities (Distinct Province + City)
    # Match on Province OR City
    cities = db.query(PhotoMetadata.province, PhotoMetadata.city)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id)\
        .filter((PhotoMetadata.province.ilike(search)) | (PhotoMetadata.city.ilike(search)))\
        .filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != '')\
        .distinct()\
        .limit(20).all()

    for p, c in cities:
        parts = [x for x in [p, c] if x]
        label = "".join(parts)
        
        # Only add if it matches the query string somewhat (e.g. contains query)
        # Or simply add because it was returned by the query
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": p or "",
                    "city": c,
                    "district": ""
                }
            })

    # 3. Search Districts (Distinct Province + City + District)
    # Match on Province OR City OR District
    districts = db.query(PhotoMetadata.province, PhotoMetadata.city, PhotoMetadata.district)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False)\
        .filter(
            (PhotoMetadata.province.ilike(search)) |
            (PhotoMetadata.city.ilike(search)) |
            (PhotoMetadata.district.ilike(search))
        )\
        .filter(PhotoMetadata.district.isnot(None), PhotoMetadata.district != '')\
        .distinct()\
        .limit(20).all()
        
    for p, c, d in districts:
        parts = [x for x in [p, c, d] if x]
        label = "".join(parts)
        
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": p or "",
                    "city": c or "",
                    "district": d
                }
            })
            
    # Sort by label length (shorter = broader scope usually comes first)
    suggestions.sort(key=lambda x: len(x["label"]))
    
    return suggestions[:limit]
