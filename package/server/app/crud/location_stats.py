import math
from uuid import UUID
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, case

from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.sql import as_date_string, date_only
from app.schemas.location_stats import (
    OverviewStats, AnnualTrendItem, MonthlyRadarItem,
    PlaceStats, PlacesResponse, HeatmapItem, HeatmapRangeResponse,
)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return 6371 * c


def _apply_date_filter(query, start_date: Optional[str], end_date: Optional[str]):
    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")
    return query


def _day_city_centroids(db: Session, owner_id: UUID, start_date: Optional[str], end_date: Optional[str], with_year: bool = False):
    """Return chronological (year?, date, city, avg_lat, avg_lng) rows for photos with GPS."""
    date_expr = date_only(db, Photo.photo_time)
    city_expr = func.coalesce(
        func.nullif(PhotoMetadata.city, ''),
        func.nullif(PhotoMetadata.province, ''),
        '未知',
    )
    cols = [date_expr.label('d'), city_expr.label('c'),
            func.avg(PhotoMetadata.latitude).label('lat'),
            func.avg(PhotoMetadata.longitude).label('lng')]
    if with_year:
        cols.insert(0, extract('year', Photo.photo_time).label('y'))

    query = db.query(*cols) \
        .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
        .filter(PhotoMetadata.latitude.isnot(None)) \
        .filter(PhotoMetadata.longitude.isnot(None)) \
        .filter(Photo.photo_time.isnot(None))
    query = _apply_date_filter(query, start_date, end_date)

    group_cols = [date_expr, city_expr]
    if with_year:
        group_cols.insert(0, extract('year', Photo.photo_time))
    query = query.group_by(*group_cols).order_by(date_expr)
    return query.all()


def _travel_distance(rows) -> float:
    """Sum haversine between consecutive day-city centroids, skipping <1km jitter."""
    total = 0.0
    prev = None
    for r in rows:
        cur = (float(r.lat), float(r.lng))
        if prev is not None:
            seg = _haversine(prev[0], prev[1], cur[0], cur[1])
            if seg >= 1.0:
                total += seg
        prev = cur
    return round(total, 1)


def get_overview(db: Session, owner_id: UUID, start_date: Optional[str] = None, end_date: Optional[str] = None) -> OverviewStats:
    has_location = db.query(func.count(Photo.id)) \
        .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
        .filter(PhotoMetadata.latitude.isnot(None)) \
        .filter(Photo.photo_time.isnot(None))
    has_location = _apply_date_filter(has_location, start_date, end_date).scalar() or 0

    province_count = db.query(func.count(func.distinct(case((PhotoMetadata.province != '', PhotoMetadata.province), else_=None)))) \
        .join(Photo, Photo.id == PhotoMetadata.photo_id) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
    province_count = _apply_date_filter(province_count, start_date, end_date).scalar() or 0

    city_count = db.query(func.count(func.distinct(case((PhotoMetadata.city != '', PhotoMetadata.city), else_=None)))) \
        .join(Photo, Photo.id == PhotoMetadata.photo_id) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
    city_count = _apply_date_filter(city_count, start_date, end_date).scalar() or 0

    scene_count = db.query(func.count(func.distinct(PhotoMetadata.scene_id))) \
        .join(Photo, Photo.id == PhotoMetadata.photo_id) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
        .filter(PhotoMetadata.scene_id.isnot(None))
    scene_count = _apply_date_filter(scene_count, start_date, end_date).scalar() or 0

    travel_days = db.query(func.count(func.distinct(date_only(db, Photo.photo_time)))) \
        .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
        .filter(Photo.photo_time.isnot(None))
    travel_days = _apply_date_filter(travel_days, start_date, end_date).scalar() or 0

    total_distance = 0.0
    farthest_place = None
    farthest_distance = 0.0
    if has_location > 0:
        total_distance = _travel_distance(_day_city_centroids(db, owner_id, start_date, end_date))

        city_centroids = db.query(
            PhotoMetadata.city.label('c'),
            func.avg(PhotoMetadata.latitude).label('lat'),
            func.avg(PhotoMetadata.longitude).label('lng'),
            func.count(Photo.id).label('cnt'),
        ).join(Photo, Photo.id == PhotoMetadata.photo_id) \
         .filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
         .filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != '') \
         .filter(PhotoMetadata.latitude.isnot(None)) \
         .filter(Photo.photo_time.isnot(None))
        city_centroids = _apply_date_filter(city_centroids, start_date, end_date) \
            .group_by(PhotoMetadata.city).order_by(desc(func.count(Photo.id))).all()

        if city_centroids:
            center = city_centroids[0]
            c_lat, c_lng = float(center.lat), float(center.lng)
            for row in city_centroids:
                dist = _haversine(c_lat, c_lng, float(row.lat), float(row.lng))
                if dist > farthest_distance:
                    farthest_distance = dist
                    farthest_place = row.c

    return OverviewStats(
        total_distance_km=total_distance,
        province_count=province_count,
        city_count=city_count,
        scene_count=scene_count,
        travel_days=travel_days,
        farthest_place=farthest_place,
        farthest_distance_km=round(farthest_distance, 1),
        has_location=has_location > 0,
    )


def get_annual_trend(db: Session, owner_id: UUID, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[AnnualTrendItem]:
    year_counts = db.query(
        extract('year', Photo.photo_time).label('y'),
        func.count(Photo.id).label('cnt'),
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
     .filter(Photo.photo_time.isnot(None))
    year_counts = _apply_date_filter(year_counts, start_date, end_date) \
        .group_by(extract('year', Photo.photo_time)).order_by(extract('year', Photo.photo_time)).all()

    centroids = _day_city_centroids(db, owner_id, start_date, end_date, with_year=True)
    per_year_rows: dict = {}
    for r in centroids:
        per_year_rows.setdefault(int(r.y), []).append(r)

    return [
        AnnualTrendItem(
            year=int(row.y),
            photo_count=row.cnt,
            distance_km=_travel_distance(per_year_rows.get(int(row.y), [])),
        )
        for row in year_counts
        if row.y is not None
    ]


def get_monthly_radar(db: Session, owner_id: UUID, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[MonthlyRadarItem]:
    month_counts = db.query(
        extract('month', Photo.photo_time).label('m'),
        func.count(Photo.id).label('cnt'),
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
     .filter(Photo.photo_time.isnot(None))
    month_counts = _apply_date_filter(month_counts, start_date, end_date) \
        .group_by(extract('month', Photo.photo_time)).all()

    count_map = {int(r.m): r.cnt for r in month_counts if r.m is not None}
    max_count = max(count_map.values()) if count_map else 0
    return [
        MonthlyRadarItem(
            month=m,
            photo_count=count_map.get(m, 0),
            activity_score=round(count_map.get(m, 0) / max_count * 100) if max_count else 0,
        )
        for m in range(1, 13)
    ]


def get_places(db: Session, owner_id: UUID, level: str = 'city', start_date: Optional[str] = None,
               end_date: Optional[str] = None, parent_region: Optional[str] = None, limit: int = 10) -> PlacesResponse:
    is_scene = False
    if level == 'province':
        group_col = PhotoMetadata.province
    elif level == 'district':
        group_col = PhotoMetadata.district
    elif level == 'scene':
        group_col = Scene.name
        is_scene = True
    else:
        group_col = PhotoMetadata.city

    date_expr = date_only(db, Photo.photo_time)
    query = db.query(
        group_col.label('name'),
        date_expr.label('d'),
        func.count(Photo.id).label('cnt'),
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
     .filter(Photo.photo_time.isnot(None)) \
     .filter(group_col.isnot(None))

    if is_scene:
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id) \
                     .join(Scene, PhotoMetadata.scene_id == Scene.id)
    else:
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
        query = query.filter(group_col != '')

    if parent_region:
        query = query.filter(PhotoMetadata.province == parent_region)
    query = _apply_date_filter(query, start_date, end_date)

    rows = query.group_by(group_col, date_expr).order_by(group_col, date_expr).all()

    places: dict = {}
    for r in rows:
        name = r.name
        d_str = as_date_string(r.d)
        entry = places.setdefault(name, {'name': name, 'photo_count': 0, 'dates': []})
        entry['photo_count'] += r.cnt
        entry['dates'].append(d_str)

    all_places = []
    for p in places.values():
        dates = sorted(set(p['dates']))
        all_places.append(PlaceStats(
            name=p['name'],
            level=level,
            photo_count=p['photo_count'],
            first_date=dates[0] if dates else None,
            last_date=dates[-1] if dates else None,
            visit_count=len(dates),
            visit_dates=dates,
        ))

    top_places = sorted(all_places, key=lambda x: x.photo_count, reverse=True)[:limit]
    revisits = sorted([p for p in all_places if p.visit_count > 1], key=lambda x: x.visit_count, reverse=True)
    return PlacesResponse(top_places=top_places, revisits=revisits)


def get_heatmap_range(db: Session, owner_id: UUID, start_date: Optional[str] = None, end_date: Optional[str] = None) -> HeatmapRangeResponse:
    date_expr = date_only(db, Photo.photo_time)
    query = db.query(
        date_expr.label('d'),
        func.count(Photo.id).label('cnt'),
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted == False) \
     .filter(Photo.photo_time.isnot(None))
    query = _apply_date_filter(query, start_date, end_date)
    rows = query.group_by(date_expr).order_by(date_expr).all()

    total_photos = 0
    data = []
    for r in rows:
        total_photos += r.cnt
        data.append(HeatmapItem(date=as_date_string(r.d), count=r.cnt))

    return HeatmapRangeResponse(total_photos=total_photos, total_days=len(data), data=data)
