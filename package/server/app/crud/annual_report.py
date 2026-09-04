from typing import List, Optional, Dict
from datetime import datetime
import math
import logging
import numpy as np
from uuid import UUID

from fastapi import Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, desc
from pydantic import BaseModel

from app.dependencies import get_db
from app.db.models.photo import Photo, ImageType, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.face import Face, FaceIdentity
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.trip import TrainTicket
from app.db.models.image_vector import ImageVector
from app.crud.search_vector import SEASON_VECTORS, EASTER_EGG_VECTOR
from app.service.media_urls import thumbnail_url

from app.schemas.annual_report import (
    AnnualReportData, UserInfo, TimeMetrics, MemoryMetrics, 
    EmotionMetrics, LocationMetrics, SeasonMetrics, SeasonData,
    EasterEgg, EasterEggTags, CategoryDistributionItem, TopCity,
    LocationPoint, CarouselGroup, ExpenseMetrics, MonthlyExpense,
    TicketDetail, TravelBehaviorMetrics, ComprehensiveMetrics,
    MonthlyFrequency, RouteStats, DestinationStats, TripTypeDistribution,
    TransportAnalysisMetrics
)

class ReportSummary(BaseModel):
    user: UserInfo
    time: TimeMetrics

def get_date_range_filter(query, start_time: datetime, end_time: datetime, user_id: Optional[UUID] = None):
    q = query.filter(
        Photo.photo_time >= start_time,
        Photo.photo_time <= end_time,
        Photo.is_deleted == False
    )
    if user_id:
        q = q.filter(Photo.owner_id == user_id)
    return q

def get_annual_report_photos(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    # 基础过滤：时间范围 + 未删除 + 图片 + 非截图 + 有 EXIF
    base_query = db.query(Photo).join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id).filter(
        Photo.photo_time >= start_time,
        Photo.photo_time <= end_time,
        Photo.is_deleted == False,
        Photo.file_type == FileType.image,
        Photo.image_type != ImageType.SCREENSHOT,
        PhotoMetadata.exif_info.isnot(None)
    )
    if user_id:
        base_query = base_query.filter(Photo.owner_id == user_id)

    # 窗口函数：按月分区、photo_time DESC 编号
    month_col = extract('month', Photo.photo_time)
    row_num = func.row_number().over(
        partition_by=month_col,
        order_by=Photo.photo_time.desc()
    ).label("rn")
    ranked = base_query.with_entities(
        Photo.id, month_col.label("month"), row_num
    ).subquery()

    # 取每月前 10（按 month + rn 排序保证输出有序）
    top_rows = (
        db.query(ranked.c.id, ranked.c.month)
        .filter(ranked.c.rn <= 10)
        .order_by(ranked.c.month, ranked.c.rn)
        .all()
    )

    # 一次 IN 查询取完整 Photo 对象，再按月组装
    photo_ids = [r[0] for r in top_rows]
    photos_map = {
        p.id: p for p in db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
    } if photo_ids else {}

    monthly_groups: Dict[int, List[Photo]] = {}
    for pid, month in top_rows:
        p = photos_map.get(pid)
        if p is not None:
            monthly_groups.setdefault(month, []).append(p)

    return monthly_groups

def get_report_expenses(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    query = db.query(TrainTicket).filter(
        TrainTicket.date_time >= start_time,
        TrainTicket.date_time <= end_time
    )
    if user_id:
        query = query.filter(TrainTicket.owner_id == user_id)
    
    total_count = query.count()
    
    # Calculate total amount
    total_amount_result = query.with_entities(func.sum(TrainTicket.price)).scalar()
    total_amount = float(total_amount_result) if total_amount_result else 0.0
    
    average_price = total_amount / total_count if total_count > 0 else 0.0
    
    # Max expense
    max_expense_ticket = query.order_by(TrainTicket.price.desc()).first()
    max_expense_amount = float(max_expense_ticket.price) if max_expense_ticket else 0.0
    max_expense_name = f"{max_expense_ticket.train_code} ({max_expense_ticket.departure_station}-{max_expense_ticket.arrival_station})" if max_expense_ticket else None
    
    # Monthly trend
    # Group by month
    base_monthly_query = db.query(
        extract('year', TrainTicket.date_time).label('year'),
        extract('month', TrainTicket.date_time).label('month'),
        func.sum(TrainTicket.price).label('amount')
    ).filter(
        TrainTicket.date_time >= start_time,
        TrainTicket.date_time <= end_time
    )
    if user_id:
        base_monthly_query = base_monthly_query.filter(TrainTicket.owner_id == user_id)

    monthly_data = base_monthly_query.group_by(
        'year', 'month'
    ).order_by(
        'year', 'month'
    ).all()
    
    monthly_trend = []
    for row in monthly_data:
        # row is (year, month, amount)
        monthly_trend.append(MonthlyExpense(
            month=f"{int(row.year)}-{int(row.month):02d}",
            amount=float(row.amount)
        ))

    # Last Year Comparison
    try:
        start_time_last_year = start_time.replace(year=start_time.year - 1)
        end_time_last_year = end_time.replace(year=end_time.year - 1)
    except ValueError:
        # Handle leap year case if necessary (e.g. Feb 29)
        start_time_last_year = start_time.replace(year=start_time.year - 1, day=28)
        end_time_last_year = end_time.replace(year=end_time.year - 1, day=28)

    query_last_year = db.query(TrainTicket).filter(
        TrainTicket.date_time >= start_time_last_year,
        TrainTicket.date_time <= end_time_last_year
    )
    if user_id:
        query_last_year = query_last_year.filter(TrainTicket.owner_id == user_id)

    total_amount_last_year_result = query_last_year.with_entities(func.sum(TrainTicket.price)).scalar()
    total_amount_last_year = float(total_amount_last_year_result) if total_amount_last_year_result else 0.0

    base_monthly_last_year = db.query(
        extract('year', TrainTicket.date_time).label('year'),
        extract('month', TrainTicket.date_time).label('month'),
        func.sum(TrainTicket.price).label('amount')
    ).filter(
        TrainTicket.date_time >= start_time_last_year,
        TrainTicket.date_time <= end_time_last_year
    )
    if user_id:
        base_monthly_last_year = base_monthly_last_year.filter(TrainTicket.owner_id == user_id)

    monthly_data_last_year = base_monthly_last_year.group_by(
        'year', 'month'
    ).order_by(
        'year', 'month'
    ).all()

    monthly_trend_last_year = []
    for row in monthly_data_last_year:
        monthly_trend_last_year.append(MonthlyExpense(
            month=f"{int(row.year)}-{int(row.month):02d}",
            amount=float(row.amount)
        ))
        
    return ExpenseMetrics(
        totalAmount=total_amount,
        totalCount=total_count,
        averagePrice=average_price,
        monthlyTrend=monthly_trend,
        totalAmountLastYear=total_amount_last_year,
        monthlyTrendLastYear=monthly_trend_last_year,
        maxExpenseTicket=max_expense_name,
        maxExpenseAmount=max_expense_amount
    )

def get_report_summary(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    base_query = get_date_range_filter(db.query(Photo), start_time, end_time, user_id)
    total_photos = base_query.count()

    # --- Time Metrics ---
    accompany_days = base_query.with_entities(func.date(Photo.photo_time)).distinct().count()

    first_photo = base_query.order_by(Photo.photo_time.asc()).first()
    last_photo = base_query.order_by(Photo.photo_time.desc()).first()

    late_night_count = base_query.filter(extract('hour', Photo.photo_time) < 5).count()

    # Get all dates with photos
    photo_dates_rows = base_query.with_entities(func.date(Photo.photo_time)).distinct().all()
    photo_dates = [str(row[0]) for row in photo_dates_rows]

    time_metrics = TimeMetrics(
        totalPhotos=total_photos,
        accompanyDays=accompany_days,
        firstPhotoDate=first_photo.photo_time.strftime('%Y-%m-%d') if first_photo else None,
        lastPhotoDate=last_photo.photo_time.strftime('%Y-%m-%d') if last_photo else None,
        lateNightPhotoCount=late_night_count,
        photoDates=photo_dates
    )

    # --- User Info (Mock/Static) ---
    user_info = UserInfo(
        nickname="时光旅人",
        avatarUrl="/avatar.png"
    )

    return ReportSummary(user=user_info, time=time_metrics)

def find_best_match_photo(
    db: Session, 
    start_time: datetime, 
    end_time: datetime, 
    embedding: List[float], 
    months: Optional[List[int]] = None,
    user_id: Optional[UUID] = None
) -> Optional[Photo]:
    """
    Find the best matching photo based on vector similarity.
    Filters by time range, file type (image only), excludes screenshots.
    """
    query = db.query(Photo).join(ImageVector, Photo.id == ImageVector.photo_id)\
        .filter(Photo.photo_time >= start_time, Photo.photo_time <= end_time, Photo.is_deleted == False)\
        .filter(Photo.file_type == FileType.image)\
        .filter(Photo.image_type != ImageType.SCREENSHOT)
    
    if user_id:
        query = query.filter(Photo.owner_id == user_id)

    if months:
         query = query.filter(extract('month', Photo.photo_time).in_(months))
         
    # Order by cosine distance (lower is better/more similar)
    if db.bind.dialect.name == "sqlite":
        target = np.asarray(embedding, dtype=float)
        target_norm = np.linalg.norm(target)
        rows = query.with_entities(Photo, ImageVector.embedding).all()

        def sqlite_distance(row):
            if not row[1] or target_norm == 0:
                return 1.0
            candidate = np.asarray(row[1], dtype=float)
            denominator = np.linalg.norm(candidate) * target_norm
            return 1.0 if denominator == 0 else 1.0 - float(np.dot(candidate, target) / denominator)

        best_photo = min(
            rows,
            key=sqlite_distance,
            default=(None, None),
        )[0]
    else:
        best_photo = query.order_by(ImageVector.embedding.cosine_distance(embedding)).first()
    return best_photo


def get_report_season(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    base_query = get_date_range_filter(db.query(Photo), start_time, end_time, user_id)

    seasons_def = [
        ("春", [3, 4, 5], "嫩芽"),
        ("夏", [6, 7, 8], "蝉鸣"),
        ("秋", [9, 10, 11], "晚风"),
        ("冬", [12, 1, 2], "暖意")
    ]
    season_list = []

    for name, months, default_tag in seasons_def:
        season_query = base_query.filter(Photo.file_type == FileType.image)\
            .filter(Photo.image_type != ImageType.SCREENSHOT)\
            .filter(extract('month', Photo.photo_time).in_(months))
        count = season_query.count()

        # Vector search for representative photo
        search_vector = SEASON_VECTORS.get(name)
        rep_photo = None
        if search_vector:
            rep_photo = find_best_match_photo(db, start_time, end_time, search_vector, months, user_id)
        
        # Fallback if no match from vector search
        if not rep_photo:
            rep_photo = season_query.first()

        rep_photo_url = thumbnail_url(user_id or rep_photo.owner_id, rep_photo.id) if rep_photo else f"https://picsum.photos/seed/{name}/400/600"
        # rep_photo_url = f"https://picsum.photos/seed/{name}/400/600"
        season_list.append(SeasonData(
            seasonName=name,
            photoCount=count,
            topTag=default_tag, 
            representativePhoto=rep_photo_url,
            highlight=f"记录了{count}个精彩瞬间", 
            shootMonth=f"{months[0]}-{months[-1]}月" if len(months) > 1 else f"{months[0]}月"
        ))

    return SeasonMetrics(seasonList=season_list)

def get_report_emotion(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    base_query = get_date_range_filter(db.query(Photo), start_time, end_time, user_id)
    total_photos = base_query.count()
    
    video_query = db.query(func.sum(Photo.duration)).filter(
        Photo.photo_time >= start_time,
        Photo.photo_time <= end_time
    )
    if user_id:
        video_query = video_query.filter(Photo.owner_id == user_id)
    total_video_duration = video_query.scalar() or 0

    live_query = db.query(Photo).filter(
        Photo.photo_time >= start_time,
        Photo.photo_time <= end_time,
        Photo.file_type == FileType.live_photo
    )
    if user_id:
        live_query = live_query.filter(Photo.owner_id == user_id)
    total_live_photo = live_query.count()

    # 相机拍摄的照片数量
    camera_query = db.query(Photo).filter(
        Photo.photo_time >= start_time,
        Photo.photo_time <= end_time,
        Photo.file_type == FileType.image,
        Photo.image_type == ImageType.CAMERA
    )
    if user_id:
        camera_query = camera_query.filter(Photo.owner_id == user_id)
    total_camera_photo = camera_query.count()

    return EmotionMetrics(
        livePhotos=total_live_photo,
        backupPhotos=total_photos,
        totalVideoDuration=total_video_duration,
        cameraPhotos=total_camera_photo,
        emotionCarouselGroups=[
            CarouselGroup(
                id='g1', 
                locationName='海边回忆', 
                photos=[f"https://picsum.photos/seed/{i+20}/400/600" for i in range(3)]
            )
        ]
    )

def get_report_easter_egg(
    start_time: datetime,
    end_time: datetime,
    db: Session,
    user_id: Optional[UUID] = None
):
    # Use vector search
    best_photo = find_best_match_photo(db, start_time, end_time, EASTER_EGG_VECTOR, user_id=user_id)
    
    best_photo_url = thumbnail_url(user_id or best_photo.owner_id, best_photo.id) if best_photo else f"https://picsum.photos/seed/best/400/600"
    best_photo_date = best_photo.photo_time.strftime('%Y-%m-%d') if best_photo else "2024-10-01"
    
    return EasterEgg(
        bestPhotoUrl=best_photo_url,
        bestPhotoDate=best_photo_date,
        tags=EasterEggTags(main="生活记录家", sub=['偏爱人像', '乐于收藏', '心怀温柔'])
    )
