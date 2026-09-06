from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.dependencies import get_db, BaseResponse
from app.schemas import location as schemas
from app.crud import location as crud
from app.schemas import photo as photo_schemas
from app.schemas import scene as scene_schemas
from app.crud import scene as scene_crud
from app.api import deps
from app.db.models import User
from app.schemas.photo import Photo

router = APIRouter()

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
    photos = crud.get_location_photos(db, current_user.id, name, level, skip, limit, start_date, end_date)
    et = time.time()
    print(f"get_location_photos: {et - st} s")
    return photos
