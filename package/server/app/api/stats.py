from uuid import UUID
from typing import List, Optional
import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract

import app.crud.photo
from app.db.models import User
from app.dependencies import get_db
from app.db.models.photo import Photo
from app.db.models.album import Album
from app.schemas.album import TimelineItem, TimelineStats
from app.schemas.dashboard import DashboardResponse, HeatmapResponse, EmotionCalendarResponse
from app.schemas.filter import FilterOptions
from app.crud import dashboard as crud_dashboard
from app.crud import album as crud_album
from app.api.deps import get_current_user

router = APIRouter()

@router.get('/timeline', response_model=TimelineStats)
def get_timeline_stats(
    album_id: UUID|None = None,
    years: Optional[List[int]] = Query(None),
    cities: Optional[List[str]] = Query(None),
    makes: Optional[List[str]] = Query(None),
    models: Optional[List[str]] = Query(None),
    image_types: Optional[List[str]] = Query(None),
    file_types: Optional[List[str]] = Query(None),
    uploaded_after: Optional[datetime.datetime] = None,
    uploaded_before: Optional[datetime.datetime] = None,
    province: Optional[str] = None,
    folder: Optional[str] = None,
    folder_direct: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder_roots = None
    if folder_direct and not (folder and folder.strip()):
        from app.utils.path import get_user_roots
        folder_roots = get_user_roots(current_user.id, db)
    return app.crud.photo.get_timeline_stats(
        db,
        album_id=album_id,
        years=years,
        cities=cities,
        makes=makes,
        models=models,
        image_types=image_types,
        file_types=file_types,
        uploaded_after=uploaded_after,
        uploaded_before=uploaded_before,
        province=province,
        folder=folder,
        folder_direct=folder_direct,
        folder_roots=folder_roots,
        user_id=current_user.id
    )

@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get dashboard overview data.
    """
    return crud_dashboard.get_dashboard_stats(db, owner_id=current_user.id)

@router.get("/heatmap", response_model=HeatmapResponse)
def get_heatmap_stats(year: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get heatmap stats data.
    """
    return crud_dashboard.get_heatmap_stats(db, owner_id=current_user.id, year=year)

@router.get("/emotion-calendar", response_model=EmotionCalendarResponse)
def get_emotion_calendar(year: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get emotion calendar data - per-day dominant colors and emotion hints.
    """
    return crud_dashboard.get_emotion_calendar_stats(db, owner_id=current_user.id, year=year)

@router.get("/filters", response_model=FilterOptions)
def get_filter_options(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get all available filter options.
    """
    return app.crud.photo.get_filter_options(db, user_id=current_user.id)
