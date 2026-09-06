from sqlalchemy.orm import Session, joinedload, contains_eager
from uuid import UUID
from sqlalchemy import and_, func, desc, extract, case, or_
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.sql import as_date_string, date_only

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

def get_location_photos(db: Session, owner_id: UUID, name: str, level: str = 'city', skip: int = 0, limit: int = 50, start_date: str = None, end_date: str = None):
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
        col = Scene.name
        query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)
    else:
        return []
        
    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    return query.filter(
        col == name
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
        func.max(cast(Photo.id, String)).label('cover_id')
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

        if not nodes:
            nodes.append(TimelineNode(
                startDate=date_str,
                endDate=date_str,
                locationName=loc_name,
                level=level,
                lat=lat,
                lng=lng,
                photoCount=count,
                coverId=cover_id
            ))
            continue

        last_node = nodes[-1]

        if last_node.locationName == loc_name:
            last_node.startDate = date_str
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
                coverId=cover_id
            ))

    total_nodes = len(nodes)
    paginated_nodes = nodes[skip:skip + limit]

    return TimelineResponse(nodes=paginated_nodes, total=total_nodes)

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
