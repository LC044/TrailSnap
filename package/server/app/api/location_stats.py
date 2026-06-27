from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.api import deps
from app.db.models import User
from app.crud import location_stats as crud
from app.schemas.location_stats import (
    OverviewStats, AnnualTrendItem, MonthlyRadarItem,
    PlacesResponse, HeatmapRangeResponse,
)

router = APIRouter()


@router.get("/overview", response_model=OverviewStats, summary="足迹概览")
def get_overview(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return crud.get_overview(db, current_user.id, start_date, end_date)


@router.get("/annual-trend", response_model=List[AnnualTrendItem], summary="年度旅行趋势")
def get_annual_trend(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return crud.get_annual_trend(db, current_user.id, start_date, end_date)


@router.get("/monthly-radar", response_model=List[MonthlyRadarItem], summary="月度出行雷达")
def get_monthly_radar(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return crud.get_monthly_radar(db, current_user.id, start_date, end_date)


@router.get("/places", response_model=PlacesResponse, summary="最常去的地方与重访清单")
def get_places(
    level: str = Query('city', regex='^(city|province|district|scene)$'),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    parent_region: Optional[str] = Query(None, description="按省份过滤"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return crud.get_places(db, current_user.id, level, start_date, end_date, parent_region, limit)


@router.get("/heatmap", response_model=HeatmapRangeResponse, summary="旅行日历热力图")
def get_heatmap(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return crud.get_heatmap_range(db, current_user.id, start_date, end_date)
