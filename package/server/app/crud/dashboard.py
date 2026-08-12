from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, extract, desc
from datetime import datetime, date, timedelta

from app.crud.face import get_identities_with_details
from app.db.models.photo import Photo, FileType
from app.db.models.face import Face, FaceIdentity
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.sql import as_date, as_date_string, date_only
from app.schemas.dashboard import (
    DashboardCard, DashboardFace,
    DashboardContentStats, ContentDetail, DashboardTime,
    DashboardTimeChartItem, DashboardResponse,
    HeatmapResponse, HeatmapItem,
    EmotionCalendarResponse, EmotionCalendarItem
)

def get_dashboard_stats(db: Session, owner_id: UUID) -> DashboardResponse:
    # 1. Card Stats
    total_media = db.query(Photo).filter(Photo.owner_id == owner_id).count()
    
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_new = db.query(Photo).filter(Photo.upload_time >= today_start, Photo.owner_id == owner_id).count()
    
    total_size_bytes = db.query(func.sum(Photo.size)).filter(Photo.owner_id== owner_id).scalar() or 0
    # Convert bytes to GB
    storage_gb = total_size_bytes / (1024 * 1024 * 1024)
    storage_used = f"{storage_gb:.1f}GB"

    card = DashboardCard(
        total_media=total_media,
        today_new=today_new,
        storage_used=storage_used
    )

    # 2. Face Stats
    total_identified = db.query(FaceIdentity).filter(FaceIdentity.is_deleted == False, FaceIdentity.owner_id == owner_id).count()

    # Pending faces (faces without identity)
    # Assuming pending means face_identity_id is NULL
    pending_faces_count = db.query(Face).join(Photo, Face.photo_id == Photo.id).filter(Face.face_identity_id == None, Face.is_deleted == False, Photo.owner_id == owner_id).count()

    # Unidentified photos count (photos that contain at least one unidentified face)
    # This might be similar to pending_faces_count but counting distinct photos
    unidentified_photos_count = db.query(func.count(func.distinct(Face.photo_id))).join(Photo, Face.photo_id == Photo.id).filter(Face.face_identity_id == None, Face.is_deleted == False, Photo.owner_id == owner_id).scalar() or 0
    
    # Top 3 Faces

    top_faces = get_identities_with_details(db, owner_id=owner_id, skip=0, limit=3)

    face_stats = DashboardFace(
        total_identified=total_identified,
        top_faces=top_faces,
        pending_faces_count=pending_faces_count, # Using simple count for now as per prompt "5位待确认" might need clustering logic which is complex
        unidentified_photos_count=unidentified_photos_count
    )

    # 3. Content Stats
    # Photos
    photos_count = db.query(Photo).filter(Photo.file_type == FileType.image, Photo.owner_id == owner_id).count()
    # Mock breakdown for photos
    photos_detail = ContentDetail(
        total=photos_count,
        sub_1_label="普通",
        sub_1_count=photos_count, # simplified
        sub_2_label="截图",
        sub_2_count=0 # simplified
    )

    # Videos
    videos_count = db.query(Photo).filter(Photo.file_type.in_([FileType.video, FileType.live_photo]), Photo.owner_id == owner_id).count()
    # Mock breakdown for videos
    videos_detail = ContentDetail(
        total=videos_count,
        sub_1_label="短视频",
        sub_1_count=videos_count,
        sub_2_label="长视频",
        sub_2_count=0
    )

    # Tags (Scenery, Food)
    # Need to check if tags exist. 
    scenery_count = db.query(PhotoTagRelation).join(PhotoTag).filter(PhotoTag.tag_name == '风景').count()
    food_count = db.query(PhotoTagRelation).join(PhotoTag).filter(PhotoTag.tag_name == '美食').count()

    content_stats = DashboardContentStats(
        photos=photos_detail,
        videos=videos_detail,
        scenery_count=scenery_count,
        food_count=food_count
    )

    # 4. Time Stats
    # Group by Year
    year_stats = db.query(
        func.extract('year', Photo.photo_time).label('year'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == owner_id)\
    .group_by(func.extract('year', Photo.photo_time))\
    .order_by(desc('year')).all()

    chart_data = []
    colors = ['#4A90E2', '#67C23A', '#909399', '#E6A23C', '#F56C6C']
    
    total_for_chart = sum([item.count for item in year_stats]) if year_stats else 0
    current_year = datetime.now().year
    current_year_percentage = 0

    for i, (year, count) in enumerate(year_stats):
        if year is None: continue
        percentage = round((count / total_for_chart) * 100, 1) if total_for_chart > 0 else 0
        if int(year) == current_year:
            current_year_percentage = int(percentage)
        
        chart_data.append(DashboardTimeChartItem(
            year=int(year),
            count=count,
            percentage=percentage,
            color=colors[i % len(colors)]
        ))

    # Monthly Peak
    # Find month with max photos
    # Postgres specific: date_trunc or extract
    # We can group by year-month
    month_stats = db.query(
        func.extract('year', Photo.photo_time).label('year'),
        func.extract('month', Photo.photo_time).label('month'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == owner_id)\
    .group_by(
        func.extract('year', Photo.photo_time),
        func.extract('month', Photo.photo_time)
    ).order_by(desc('count')).first()

    if month_stats:
        m_year = int(month_stats.year)
        m_month = int(month_stats.month)
        m_count = month_stats.count
        monthly_peak = f"{m_year}年{m_month}月拍摄最多：{m_count}张"
    else:
        monthly_peak = "暂无数据"

    time_stats = DashboardTime(
        current_year_percentage=current_year_percentage,
        chart_data=chart_data,
        monthly_peak=monthly_peak
    )

    return DashboardResponse(
        card=card,
        face=face_stats,
        content=content_stats,
        time=time_stats
    )

def get_heatmap_stats(db: Session, owner_id: UUID, year: int | None = None) -> HeatmapResponse:
    today = datetime.now().date()
    date_expr = date_only(db, Photo.photo_time)
    query = db.query(
        date_expr.label('photo_date'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == owner_id, Photo.photo_time != None)
    
    if year:
        # filter by specific year
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        query = query.filter(
            Photo.photo_time >= datetime.combine(start_date, datetime.min.time()), 
            Photo.photo_time <= datetime.combine(end_date, datetime.max.time())
        )
    else:
        # past 365 days
        start_date = today - timedelta(days=364)
        end_date = today
        query = query.filter(
            Photo.photo_time >= datetime.combine(start_date, datetime.min.time()), 
            Photo.photo_time <= datetime.combine(end_date, datetime.max.time())
        )
        
    query = query.group_by(date_expr).order_by(date_expr)
    results = query.all()
    
    total_photos = 0
    total_days = len(results)
    data = []
    
    max_consecutive_days = 0
    current_consecutive = 0
    prev_date = None
    
    for r in results:
        photo_date = as_date(r.photo_date)
        total_photos += r.count
        data.append(HeatmapItem(date=photo_date.isoformat(), count=r.count))
        
        if prev_date and (photo_date - prev_date).days == 1:
            current_consecutive += 1
        else:
            current_consecutive = 1
            
        max_consecutive_days = max(max_consecutive_days, current_consecutive)
        prev_date = photo_date
        
    # Find available years
    years_query = db.query(
        func.extract('year', Photo.photo_time).label('year')
    ).filter(Photo.owner_id == owner_id, Photo.photo_time != None)\
    .group_by(func.extract('year', Photo.photo_time))\
    .order_by(desc('year')).all()
    
    available_years = [int(y.year) for y in years_query if y.year]
    
    return HeatmapResponse(
        total_photos=total_photos,
        total_days=total_days,
        max_consecutive_days=max_consecutive_days,
        data=data,
        available_years=available_years
    )


def get_emotion_calendar_stats(db: Session, owner_id: UUID, year: int | None = None) -> EmotionCalendarResponse:
    """Get emotion calendar data - per-day dominant colors and emotion hints."""
    from app.db.models.photo_color import PhotoColor
    from app.db.models.tag import PhotoTag, PhotoTagRelation

    today = datetime.now().date()

    # Date range filter
    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        start_date = today - timedelta(days=364)
        end_date = today

    time_filter = (
        Photo.photo_time >= datetime.combine(start_date, datetime.min.time()),
        Photo.photo_time <= datetime.combine(end_date, datetime.max.time()),
    )

    date_expr = date_only(db, Photo.photo_time)

    # 1. Per-day photo counts
    date_counts = db.query(
        date_expr.label('photo_date'),
        func.count(Photo.id).label('count'),
    ).filter(Photo.owner_id == owner_id, Photo.photo_time != None, *time_filter) \
        .group_by(date_expr).order_by(date_expr).all()

    # 2. Photo IDs per date
    photo_date_rows = db.query(
        date_expr.label('photo_date'),
        Photo.id.label('photo_id'),
    ).filter(Photo.owner_id == owner_id, Photo.photo_time != None, *time_filter).all()

    photo_by_date: dict = {}
    for row in photo_date_rows:
        d = as_date_string(row.photo_date)
        photo_by_date.setdefault(d, []).append(row.photo_id)

    all_photo_ids = [pid for ids in photo_by_date.values() for pid in ids]

    # 3. Batch fetch PhotoColor records
    color_map: dict = {}  # photo_id -> PhotoColor
    if all_photo_ids:
        try:
            chunk_size = 500
            for i in range(0, len(all_photo_ids), chunk_size):
                chunk = all_photo_ids[i:i + chunk_size]
                colors = db.query(PhotoColor).filter(PhotoColor.photo_id.in_(chunk)).all()
                for c in colors:
                    color_map[str(c.photo_id)] = c
        except Exception as e:
            db.rollback()
            import logging
            logging.getLogger(__name__).warning(f"PhotoColor query failed (table may not exist yet): {e}")
            color_map = {}

    # 4. Batch fetch classification tags via JOIN (PhotoTagRelation -> PhotoTag)
    tag_map: dict = {}  # photo_id -> list of tag_name
    if all_photo_ids:
        try:
            chunk_size = 500
            for i in range(0, len(all_photo_ids), chunk_size):
                chunk = all_photo_ids[i:i + chunk_size]
                tag_rows = db.query(
                    PhotoTagRelation.photo_id,
                    PhotoTag.tag_name,
                ).join(PhotoTag, PhotoTagRelation.tag_id == PhotoTag.id) \
                 .filter(PhotoTagRelation.photo_id.in_(chunk), PhotoTag.type == 'yolo').all()
                for row in tag_rows:
                    pid_str = str(row.photo_id)
                    tag_map.setdefault(pid_str, []).append(row.tag_name)
        except Exception as e:
            db.rollback()
            import logging
            logging.getLogger(__name__).warning(f"Tag query failed: {e}")
            tag_map = {}

    # 5. Aggregate per-day
    total_photos = 0
    data = []

    for r in date_counts:
        total_photos += r.count
        date_str = as_date_string(r.photo_date)
        photo_ids = photo_by_date.get(date_str, [])

        dominant_color = None
        avg_brightness = None
        avg_saturation = None
        emotion_hint = None
        all_categories: list = []

        color_records = [color_map[str(pid)] for pid in photo_ids if str(pid) in color_map]

        if color_records:
            emotion_counts: dict = {}
            brightness_sum = 0.0
            saturation_sum = 0.0
            top_color_counts: dict = {}

            for cr in color_records:
                if cr.emotion_hint:
                    emotion_counts[cr.emotion_hint] = emotion_counts.get(cr.emotion_hint, 0) + 1
                if cr.brightness is not None:
                    brightness_sum += cr.brightness
                if cr.saturation is not None:
                    saturation_sum += cr.saturation
                if cr.dominant_colors and len(cr.dominant_colors) > 0:
                    top_color = cr.dominant_colors[0].get('hex') if isinstance(cr.dominant_colors[0], dict) else cr.dominant_colors[0]
                    top_color_counts[top_color] = top_color_counts.get(top_color, 0) + 1

            if emotion_counts:
                emotion_hint = max(emotion_counts, key=emotion_counts.get)
            if top_color_counts:
                dominant_color = max(top_color_counts, key=top_color_counts.get)
            avg_brightness = round(brightness_sum / len(color_records), 3) if brightness_sum else None
            avg_saturation = round(saturation_sum / len(color_records), 3) if saturation_sum else None

        # Collect classification tags from JOIN (not stored in PhotoColor)
        for pid in photo_ids:
            tags = tag_map.get(str(pid), [])
            all_categories.extend(tags)
        unique_cats = list(dict.fromkeys(all_categories))[:3]

        data.append(EmotionCalendarItem(
            date=date_str,
            photo_count=r.count,
            dominant_color=dominant_color,
            brightness=avg_brightness,
            saturation=avg_saturation,
            top_categories=unique_cats,
            emotion_hint=emotion_hint,
        ))

    # Available years
    years_query = db.query(
        func.extract('year', Photo.photo_time).label('year')
    ).filter(Photo.owner_id == owner_id, Photo.photo_time != None) \
        .group_by(func.extract('year', Photo.photo_time)) \
        .order_by(desc('year')).all()

    available_years = [int(y.year) for y in years_query if y.year]

    return EmotionCalendarResponse(
        total_photos=total_photos,
        total_days=len(date_counts),
        data=data,
        available_years=available_years
    )

