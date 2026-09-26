"""Owner-scoped footprint aggregation on PostgreSQL and SQLite.

Only bounded city/route scalar rows leave the database. Window functions split
visits before limiting the rendered payload, so limits never change statistics
or invent a connection over skipped photos. All coordinates are WGS84 EXIF GPS.
"""

import base64
import binascii
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from math import isfinite
from uuid import UUID

from sqlalchemy import Integer, String, and_, case, cast, extract, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata

VISIT_GAP_SECONDS = 7 * 24 * 60 * 60
_SEPARATOR = "\x1f"


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Accept west,south,east,north; west > east crosses the antimeridian."""
    if value is None:
        return None
    try:
        west, south, east, north = (float(part.strip()) for part in value.split(","))
    except (ValueError, TypeError):
        raise ValueError("bbox 必须是 west,south,east,north 四个坐标") from None
    if not all(isfinite(part) for part in (west, south, east, north)):
        raise ValueError("bbox 坐标必须为有限数值")
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("bbox 经度范围为 -180..180，纬度为 -90..90，south 不得大于 north")
    return west, south, east, north


def _city_id(key: str) -> str:
    return "fp_" + base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")


def _decode_city_id(value: str) -> str:
    try:
        if not value.startswith("fp_") or len(value) > 2000:
            raise ValueError()
        token = value[3:]
        key = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True).decode()
        if key.count(_SEPARATOR) != 2 or _city_id(key) != value:
            raise ValueError()
        return key
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError("无效的城市标识") from None


def _place_expressions():
    def clean(column):
        return func.coalesce(func.nullif(func.trim(column), ""), "")

    country = clean(PhotoMetadata.country)
    province = clean(PhotoMetadata.province)
    city = clean(PhotoMetadata.city)
    district = clean(PhotoMetadata.district)
    # Ungeocoded GPS photos still appear; separate ~10 km cells prevent unknown
    # places on opposite continents being merged into one fictitious city.
    cell = cast(func.round(PhotoMetadata.latitude, 1), String) + ":" + cast(func.round(PhotoMetadata.longitude, 1), String)
    location = case((city != "", "city:" + city), else_="gps:" + cell)
    key = country + _SEPARATOR + province + _SEPARATOR + location
    name = case(
        (city != "", city), (district != "", district), (province != "", province),
        else_="GPS 位置 " + cell,
    )
    return key, country, province, city, name


def _photo_filters(owner_id: UUID, year: int | None):
    filters = [Photo.owner_id == owner_id, Photo.is_deleted.is_(False)]
    if year is not None:
        if not 1 <= year <= 9998:
            raise ValueError("year 必须在 1..9998 之间")
        filters.extend((Photo.photo_time >= datetime(year, 1, 1), Photo.photo_time < datetime(year + 1, 1, 1)))
    return filters


def _gps_filters():
    # BETWEEN also rejects PostgreSQL numeric NaN and out-of-range infinities.
    return [PhotoMetadata.latitude.between(-90, 90), PhotoMetadata.longitude.between(-180, 180)]


def _in_bbox(lat, lng, bbox):
    west, south, east, north = bbox
    longitude = lng.between(west, east) if west <= east else or_(lng >= west, lng <= east)
    return and_(lat.between(south, north), longitude)


def _elapsed_seconds(db, later, earlier):
    if db.get_bind().dialect.name == "sqlite":
        return (func.julianday(later) - func.julianday(earlier)) * 86400
    return extract("epoch", later - earlier)


def _source(owner_id, year, start_date: date | None = None, end_date: date | None = None):
    key, country, province, city, name = _place_expressions()
    query = select(
        Photo.id.label("photo_id"), Photo.photo_time.label("taken_at"),
        PhotoMetadata.latitude.label("lat"), PhotoMetadata.longitude.label("lng"),
        key.label("key"), country.label("country"), province.label("province"),
        city.label("city"), name.label("name"),
        func.row_number().over(
            partition_by=key, order_by=(Photo.photo_time.desc().nullslast(), Photo.id.desc()),
        ).label("cover_rank"),
    ).join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id).where(
        *_photo_filters(owner_id, year), *_gps_filters(),
    )
    if start_date is not None:
        query = query.where(Photo.photo_time >= datetime.combine(start_date, time.min))
    if end_date is not None:
        query = query.where(Photo.photo_time < datetime.combine(end_date + timedelta(days=1), time.min))
    return query.cte("footprint_source")


def _visits(db, source):
    order = (source.c.taken_at, source.c.photo_id)
    previous = select(
        source,
        func.lag(source.c.key).over(order_by=order).label("previous_key"),
        func.lag(source.c.taken_at).over(order_by=order).label("previous_at"),
    ).where(source.c.taken_at.is_not(None)).cte("footprint_previous")
    is_start = case((or_(
        previous.c.previous_key.is_(None), previous.c.previous_key != previous.c.key,
        _elapsed_seconds(db, previous.c.taken_at, previous.c.previous_at) > VISIT_GAP_SECONDS,
    ), 1), else_=0)
    numbered = select(
        previous,
        func.sum(is_start).over(
            order_by=(previous.c.taken_at, previous.c.photo_id), rows=(None, 0),
        ).label("visit_no"),
    ).cte("footprint_numbered")
    points = select(
        numbered,
        func.row_number().over(
            partition_by=numbered.c.visit_no, order_by=(numbered.c.taken_at, numbered.c.photo_id),
        ).label("first_rank"),
        func.row_number().over(
            partition_by=numbered.c.visit_no, order_by=(numbered.c.taken_at.desc(), numbered.c.photo_id.desc()),
        ).label("last_rank"),
    ).cte("footprint_visit_points")
    return select(
        points.c.visit_no, points.c.key,
        func.min(points.c.name).label("name"),
        func.min(points.c.taken_at).label("start_at"), func.max(points.c.taken_at).label("end_at"),
        func.count().label("photo_count"),
        func.max(case((points.c.first_rank == 1, points.c.lat))).label("start_lat"),
        func.max(case((points.c.first_rank == 1, points.c.lng))).label("start_lng"),
        func.max(case((points.c.last_rank == 1, points.c.lat))).label("end_lat"),
        func.max(case((points.c.last_rank == 1, points.c.lng))).label("end_lng"),
    ).group_by(points.c.visit_no, points.c.key).cte("footprint_visits")


def _sample_routes(db: Session, visits, max_points: int, bounds=None) -> tuple[list[dict], bool]:
    connection_columns = [
        func.lag(visits.c[column]).over(order_by=visits.c.visit_no).label("previous_" + column)
        for column in ("key", "name", "end_at", "start_lat", "start_lng")
    ]
    connections = select(visits, *connection_columns).cte("footprint_connections")
    route_query = select(connections).where(
        connections.c.previous_key.is_not(None), connections.c.previous_key != connections.c.key,
        _elapsed_seconds(db, connections.c.start_at, connections.c.previous_end_at) <= VISIT_GAP_SECONDS,
        connections.c.start_at > connections.c.previous_end_at,
    )
    if bounds:
        route_query = route_query.where(or_(
            _in_bbox(connections.c.start_lat, connections.c.start_lng, bounds),
            _in_bbox(connections.c.previous_start_lat, connections.c.previous_start_lng, bounds),
        ))
    # Sample original edges evenly; never connect visits across omitted edges.
    counted = route_query.add_columns(
        func.row_number().over(order_by=connections.c.start_at).label("route_rank"),
        func.count().over().label("total_routes"),
    ).cte("footprint_ranked_routes")
    bucket = func.floor((counted.c.route_rank - 1) * (max_points - 1.0) / func.nullif(counted.c.total_routes - 1, 0))
    rows = db.execute(select(counted).where(or_(
        counted.c.total_routes <= max_points,
        counted.c.route_rank == 1,
        counted.c.route_rank == counted.c.total_routes,
        bucket > func.floor((counted.c.route_rank - 2) * (max_points - 1.0) / func.nullif(counted.c.total_routes - 1, 0)),
    )).order_by(counted.c.start_at).limit(max_points)).mappings().all()
    routes = [{
        "id": "route_" + sha256(f'{row["previous_key"]}|{row["key"]}|{row["start_at"].isoformat()}'.encode()).hexdigest()[:20],
        # A visit uses the same anchor for its incoming and outgoing edge.
        "from": [float(row["previous_start_lng"]), float(row["previous_start_lat"])],
        "to": [float(row["start_lng"]), float(row["start_lat"])],
        "from_name": row["previous_name"], "to_name": row["name"],
        "start_at": row["previous_end_at"], "end_at": row["start_at"],
        "photo_count": row["photo_count"],
    } for row in rows]
    return routes, bool(rows and rows[0]["total_routes"] > max_points)


def get_map_routes(db: Session, owner_id: UUID, start_date: date | None = None,
                   end_date: date | None = None, max_points: int = 300) -> list[dict]:
    """Return bounded real visit edges across the selected date range."""
    if start_date and end_date and start_date > end_date:
        raise ValueError("开始日期不得晚于结束日期")
    source = _source(owner_id, None, start_date, end_date)
    routes, _ = _sample_routes(db, _visits(db, source), max_points)
    return routes


def get_footprint(db: Session, owner_id: UUID, year: int | None = None,
                  bbox: str | None = None, max_points: int = 800) -> dict:
    """Return statistics for the selected year and a bounded viewport payload.

    Timeline uses all non-deleted dated photos, including photos without GPS.
    Summary's photo_count does too; geographic/visit counts require valid GPS.
    Bbox only filters visible map features, never the summary or year axis.
    """
    bounds = parse_bbox(bbox)
    if not 200 <= max_points <= 2000:
        raise ValueError("max_points 必须在 200..2000 之间")
    source = _source(owner_id, year)
    visits = _visits(db, source)
    places = select(
        source.c.key, source.c.country, source.c.province, source.c.city,
        func.max(case((source.c.cover_rank == 1, source.c.name))).label("name"),
        func.max(case((source.c.cover_rank == 1, source.c.lat))).label("lat"),
        func.max(case((source.c.cover_rank == 1, source.c.lng))).label("lng"),
        func.max(case((source.c.cover_rank == 1, cast(source.c.photo_id, String)))).label("cover_id"),
        func.count().label("photo_count"),
        func.min(source.c.taken_at).label("first_at"), func.max(source.c.taken_at).label("last_at"),
    ).group_by(source.c.key, source.c.country, source.c.province, source.c.city).cte("footprint_places")
    visit_counts = select(visits.c.key, func.count().label("visit_count")).group_by(visits.c.key).cte("footprint_visit_counts")
    total_photos = select(func.count()).select_from(Photo).where(*_photo_filters(owner_id, year)).scalar_subquery()
    summary_row = db.execute(select(
        total_photos.label("photo_count"),
        func.coalesce(func.sum(places.c.photo_count), 0).label("gps_photo_count"),
        func.count(func.distinct(case((places.c.province != "", places.c.country + _SEPARATOR + places.c.province)))).label("province_count"),
        func.count(case((places.c.city != "", 1))).label("city_count"),
        func.count(func.distinct(func.nullif(places.c.country, ""))).label("country_count"),
        select(func.count()).select_from(visits).scalar_subquery().label("visit_count"),
    )).mappings().one()
    city_query = select(places, func.coalesce(visit_counts.c.visit_count, 0).label("visit_count")).outerjoin(
        visit_counts, visit_counts.c.key == places.c.key,
    )
    if bounds:
        city_query = city_query.where(_in_bbox(places.c.lat, places.c.lng, bounds))
    city_rows = db.execute(city_query.order_by(places.c.photo_count.desc(), places.c.key).limit(max_points + 1)).mappings().all()
    cities = [{
        "id": _city_id(row["key"]), "name": row["name"], "country": row["country"], "province": row["province"],
        "lat": float(row["lat"]), "lng": float(row["lng"]), "cover_id": str(UUID(row["cover_id"])),
        "photo_count": row["photo_count"], "visit_count": row["visit_count"],
        "first_at": row["first_at"], "last_at": row["last_at"],
    } for row in city_rows[:max_points]]

    routes, routes_sampled = _sample_routes(db, visits, max_points, bounds)

    key, _, _, city, _ = _place_expressions()
    # SQLite's strftime parser rounds a value such as 23:59:59.999999 into
    # the following day. Read the ISO year directly so the timeline preserves
    # the same calendar year used by the exclusive date-range filter.
    year_expr = (
        cast(func.substr(cast(Photo.photo_time, String), 1, 4), Integer)
        if db.get_bind().dialect.name == "sqlite"
        else extract("year", Photo.photo_time)
    )
    timeline_rows = db.execute(select(
        year_expr.label("year"), func.count(Photo.id).label("photo_count"),
        func.count(func.distinct(case((and_(*_gps_filters(), city != ""), key)))).label("city_count"),
    ).select_from(Photo).outerjoin(PhotoMetadata, PhotoMetadata.photo_id == Photo.id).where(
        *_photo_filters(owner_id, None), Photo.photo_time.is_not(None),
    ).group_by(year_expr).order_by(year_expr)).mappings().all()
    timeline = [{"year": int(row["year"]), "photo_count": row["photo_count"], "city_count": row["city_count"]} for row in timeline_rows]
    return {
        "years": [row["year"] for row in timeline], "summary": dict(summary_row), "cities": cities,
        "routes": routes, "timeline": timeline,
        "sampled": len(city_rows) > max_points or routes_sampled,
    }


def get_footprint_photos(db: Session, owner_id: UUID, city_id: str, year: int | None = None,
                         skip: int = 0, limit: int = 24):
    """Resolve an opaque city id, then apply the same owner/date/GPS constraints."""
    key = _decode_city_id(city_id)
    place_key, *_ = _place_expressions()
    return db.query(Photo).join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id).filter(
        *_photo_filters(owner_id, year), *_gps_filters(), place_key == key,
    ).order_by(Photo.photo_time.desc().nullslast(), Photo.id.desc()).offset(skip).limit(limit).all()
