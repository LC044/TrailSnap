from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from uuid import UUID
from app.dependencies import get_db, BaseResponse
from app.schemas import location as schemas
from app.crud import location as crud
from app.crud import footprint as footprint_crud
from app.schemas.footprint import FootprintResponse, FootprintRoute
from app.schemas import photo as photo_schemas
from app.schemas import scene as scene_schemas
from app.crud import scene as scene_crud
from app.api import deps
from app.db.models import User
from app.schemas.photo import Photo

router = APIRouter()

@router.get("/map-routes", response_model=BaseResponse[List[FootprintRoute]], summary="获取地图足迹连线")
def get_map_routes(
    start_date: date | None = Query(None, description="开始日期"),
    end_date: date | None = Query(None, description="结束日期"),
    max_points: int = Query(300, ge=50, le=800, description="最多返回的真实地点连线数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return BaseResponse.success(data=footprint_crud.get_map_routes(
            db, current_user.id, start_date, end_date, max_points,
        ))
    except ValueError as exc:
        return BaseResponse.fail(code=422, msg=str(exc))

@router.get("/footprint", response_model=BaseResponse[FootprintResponse], summary="获取三维足迹地图")
def get_footprint(
    year: int | None = Query(None, ge=1, le=9998, description="拍摄年份；不传则为全部年份"),
    bbox: str | None = Query(None, max_length=120, description="可见范围 west,south,east,north；只裁剪地图图层"),
    max_points: int = Query(800, ge=200, le=2000, description="城市和照片地点连线各自的数量上限"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        data = footprint_crud.get_footprint(db, current_user.id, year, bbox, max_points)
        return BaseResponse.success(data=data)
    except ValueError as exc:
        return BaseResponse.fail(code=422, msg=str(exc))


@router.get("/footprint/photos", response_model=BaseResponse[List[Photo]], summary="获取足迹城市照片")
def get_footprint_photos(
    city_id: str = Query(..., min_length=4, max_length=2000),
    year: int | None = Query(None, ge=1, le=9998),
    skip: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return BaseResponse.success(data=footprint_crud.get_footprint_photos(db, current_user.id, city_id, year, skip, limit))
    except ValueError as exc:
        return BaseResponse.fail(code=422, msg=str(exc))


@router.get("/search", response_model=List[schemas.LocationSearchItem], summary="搜索位置")
def search_locations(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    搜索包含关键词的省/市/区。
    """
    return crud.search_locations(db, current_user.id, q)

@router.get("/years", response_model=List[int], summary="获取有位置照片的年份")
def get_years(db: Session = Depends(get_db), current_user: User = Depends(deps.get_current_user)):
    """
    获取包含有效地理位置信息的照片拍摄年份。
    """
    return crud.get_location_years(db, current_user.id)

@router.get("", response_model=List[schemas.Location], summary="获取位置列表")
def get_locations(
    level: str = Query('city', regex='^(city|province|district|scene)$', description="分组级别：city 或 province 或 district 或 scene"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取按城市或省份分组的位置列表，包含每个位置的封面照片和照片数量。
    """
    return crud.get_locations(db, current_user.id, level, skip, limit, start_date, end_date)

@router.get("/distribution", response_model=List[schemas.LocationBase], summary="获取位置分布数据")
def get_location_distribution(
    level: str = Query('city', regex='^(city|province|district|scene)$', description="分组级别：city 或 province 或 district 或 scene"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取所有位置的分布数据（仅包含名称和数量），用于地图展示。
    """
    return crud.get_location_distribution(db, current_user.id, level, start_date, end_date)

@router.get("/statistics", response_model=schemas.LocationStatistics, summary="获取位置统计数据")
def get_location_statistics(db: Session = Depends(get_db), current_user: User = Depends(deps.get_current_user)):
    """
    获取位置统计数据（省份、城市、区县数量等）。
    """
    return crud.get_location_statistics(db, current_user.id)

from app.schemas.metadata import PhotoDetail

@router.get("/timeline", response_model=schemas.TimelineResponse, summary="获取足迹时间轴照片")
def get_timeline_photos(
    level: str = Query('city', regex='^(city|province|district|scene)$', description="分组级别：city 或 province 或 district 或 scene"),
    skip: int = 0,
    limit: int = 100,
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取足迹时间轴节点（按天和行程聚合），按拍摄时间倒序排列。
    """
    return crud.get_timeline_nodes(db, current_user.id, level, skip, limit, start_date, end_date)

@router.get("/trajectory", response_model=BaseResponse[schemas.TrajectoryResponse], summary="获取旅行 GPS 轨迹")
def get_trajectory(
    start_date: str = Query(..., description="旅程开始日期"),
    end_date: str = Query(..., description="旅程结束日期"),
    max_points: int = Query(360, ge=50, le=1000, description="最多返回的轨迹点数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """按真实拍摄时间返回经空间去重、限量采样的 GPS 轨迹点。"""
    data = crud.get_trajectory_points(db, current_user.id, start_date, end_date, max_points)
    return BaseResponse.success(data=data)

@router.get("/markers", response_model=List[schemas.MapMarker], summary="获取地图标记点")
def get_map_markers(
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取所有包含GPS信息的照片标记点。
    """
    return crud.get_map_markers(db, current_user.id, start_date, end_date)


@router.get("/time-compare", response_model=BaseResponse[schemas.TimeCompareSummary], summary="获取地点时光对照摘要")
def get_time_compare_summary(
    scene_id: Optional[UUID] = Query(None, description="具体地点 ID"),
    photo_id: Optional[UUID] = Query(None, description="从单张照片解析具体地点"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if not scene_id and not photo_id:
        return BaseResponse.fail(code=422, msg="scene_id or photo_id is required")
    result = crud.get_time_compare_summary(db, current_user.id, scene_id=scene_id, photo_id=photo_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Location or photo not found")
    return BaseResponse.success(data=result)


@router.get("/time-compare/photos", response_model=BaseResponse[List[Photo]], summary="获取地点的对照照片")
def get_time_compare_photos(
    scene_id: Optional[UUID] = Query(None, description="具体地点 ID"),
    photo_id: Optional[UUID] = Query(None, description="GPS 邻近匹配的锚点照片 ID"),
    reference_photo_id: Optional[UUID] = Query(None, description="用于相似视角排序的另一侧照片 ID"),
    year: Optional[int] = Query(None, ge=1, le=9998, description="兼容旧客户端的拍摄年份"),
    visit_date: Optional[date] = Query(None, description="拍摄日，用于排除同日连拍"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if not scene_id and not photo_id:
        return BaseResponse.fail(code=422, msg="scene_id or photo_id is required")
    photos = crud.get_time_compare_photos(
        db,
        current_user.id,
        scene_id=scene_id,
        photo_id=photo_id,
        reference_photo_id=reference_photo_id,
        year=year,
        skip=skip,
        limit=limit,
        visit_date=visit_date,
    )
    if photos is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return BaseResponse.success(data=photos)

@router.post("/scenes", response_model=BaseResponse[scene_schemas.Scene], summary="创建景区")
def create_scene(
    scene: scene_schemas.SceneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    创建新的景区，并自动关联范围内的照片。
    """
    return BaseResponse.success(data=scene_crud.create_scene(db, scene, owner_id=current_user.id))

@router.get("/scenes/list", response_model=BaseResponse[List[scene_schemas.Scene]], summary="获取所有景区详情")
def get_scenes_list(
    skip: int = 0,
    limit: int = 100,
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取所有景区详细信息（包含多边形坐标）。
    """
    return BaseResponse.success(data=scene_crud.get_scenes(db, skip, limit, start_date, end_date, owner_id=current_user.id))

@router.get("/scenes/{scene_id}", response_model=BaseResponse[scene_schemas.Scene], summary="获取景区详情")
def get_scene_details(
    scene_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取指定景区的详细信息。
    """
    scene = scene_crud.get_scene(db, scene_id, owner_id=current_user.id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return BaseResponse.success(data=scene)

@router.put("/scenes/{scene_id}", response_model=BaseResponse[scene_schemas.Scene], summary="更新景区")
def update_scene(
    scene_id: UUID,
    scene: scene_schemas.SceneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    更新景区信息。
    """
    try:
        db_scene = scene_crud.update_scene(db, scene_id, scene, owner_id=current_user.id)
        if not db_scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        return BaseResponse.success(data=db_scene)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.delete("/scenes/{scene_id}", response_model=BaseResponse[dict], summary="删除景区")
def delete_scene(
    scene_id: UUID = Path(..., description="景区ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    删除景区。系统默认景区不允许删除。
    """
    try:
        scene = scene_crud.delete_scene(db, scene_id, owner_id=current_user.id)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        return BaseResponse.success(data={"status": "success", "message": "Scene deleted"})
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/{name}/photos", response_model=List[Photo], summary="获取位置照片列表")
def get_location_photos(
    name: str = Path(..., description="位置名称"),
    level: str = Query('city', regex='^(city|province|district|scene)$', description="分组级别：city 或 province 或 district 或 scene"),
    scene_id: Optional[UUID] = Query(None, description="景区 ID；景区详情优先按 ID 查询"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取指定位置（城市或省份）的照片列表。
    """
    import time
    st = time.time()
    photos = crud.get_location_photos(db, current_user.id, name, level, skip, limit, start_date, end_date, scene_id)
    et = time.time()
    print(f"get_location_photos: {et - st} s")
    return photos
