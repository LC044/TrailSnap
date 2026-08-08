from fastapi import APIRouter, Depends, HTTPException, Body, Query, Path
from sqlalchemy.orm import Session

import app.schemas.photo
from app.api import deps
from app.dependencies import get_db, BaseResponse
from app.schemas import face as schemas
from app.crud import face as crud_face
from app.core.config_manager import config_manager
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID

from app.schemas.face import FaceIdentitySchema, RemovePhotosRequest, SetCoverRequest, MergeRequest, FaceIdentityCreate, AddPhotosToIdentityRequest

from app.db.models.photo import Photo
from app.db.models.face import Face
from app.db.models.user import User

import numpy as np
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

from app.service.face_cluster import FaceClusterService, FaceRescanConflictError, FaceRescanError

@router.post("/identities", response_model=BaseResponse[FaceIdentitySchema], summary="创建新人物", description="创建一个新的人物记录")
def create_identity(
    payload: FaceIdentityCreate = Body(..., description="人物信息"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    创建新人物。
    """
    data = crud_face.create_identity(db, payload, owner_id=current_user.id)
    return BaseResponse(code=200, msg="创建成功", data=data)

@router.post("/identities/{id}/add-photos", summary="添加照片到人物", description="将选中的照片添加到指定人物相册中")
async def add_photos_to_identity(
    id: UUID = Path(..., description="人物ID"),
    payload: AddPhotosToIdentityRequest = Body(..., description="要添加的照片列表"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    将选中的照片添加到人物相册中。
    1. 如果照片中包含人脸，则选择与人物相似度最高的人脸进行关联。
    2. 如果照片中不包含人脸，则触发AI识别人脸。
       - 如果识别到人脸，则添加到人物相册中。
       - 如果没有识别到人脸，则创建一个新的人脸记录并与人物关联（特征值为空，置信度为1）。
    """
    identity = crud_face.get_identity(db, id, owner_id=current_user.id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    
    count = 0
    
    # 1. 计算当前人物的特征中心（如果有已关联的人脸）
    assigned_faces = db.query(Face).join(Photo).filter(
        Face.face_identity_id == id,
        Face.is_deleted == False,
        Face.face_feature.isnot(None),
        Photo.owner_id == current_user.id
    ).all()
    
    identity_center = None
    if assigned_faces:
        embeddings = [np.array(f.face_feature) for f in assigned_faces]
        if embeddings:
            identity_center = np.mean(embeddings, axis=0)
            norm = np.linalg.norm(identity_center)
            if norm > 0:
                identity_center = identity_center / norm
            
    for photo_id in payload.photo_ids:
        photo = db.query(Photo).get(photo_id)
        if not photo or photo.owner_id != current_user.id:
            continue
            
        # 2. 检查该照片是否已有人脸
        faces = db.query(Face).filter(Face.photo_id == photo_id, Face.is_deleted == False).all()
        
        if not faces:
            # 3. 如果没有人脸，触发AI识别
            try:
                # process_single_photo 是异步的，会更新数据库
                # 传入 None 作为 task_manager，因为这里不需要创建新任务
                # await process_single_photo(None, photo, db)
                
                # 重新查询人脸
                faces = db.query(Face).filter(Face.photo_id == photo_id, Face.is_deleted == False).all()
            except Exception as e:
                logger.error(f"Failed to process photo {photo_id}: {e}")
                # AI处理失败，视为无人脸，继续下面的逻辑创建默认人脸
                pass
        
        if faces:
            # 4. 如果有人脸（原有或AI识别出），选择最佳匹配
            best_face = None
            if identity_center is not None:
                # 找余弦距离最近的
                min_dist = 2.0
                for face in faces:
                    if face.face_feature is None:
                        continue
                    # 确保向量维度一致
                    feat = np.array(face.face_feature)
                    norm = np.linalg.norm(feat)
                    if norm > 0:
                        feat = feat / norm
                        dist = 1.0 - np.dot(identity_center, feat)
                        if dist < min_dist:
                            min_dist = dist
                            best_face = face
            
            if not best_face:
                # 如果没有中心向量或无法计算距离，选择面积最大的人脸
                max_area = -1
                for face in faces:
                    area = 0
                    if face.face_rect and len(face.face_rect) == 4:
                        w = face.face_rect[2] - face.face_rect[0]
                        h = face.face_rect[3] - face.face_rect[1]
                        area = w * h
                    
                    if area > max_area:
                        max_area = area
                        best_face = face
                        
                # 如果还是没有（例如face_rect为空），选第一个
                if not best_face and faces:
                    best_face = faces[0]
            
            if best_face:
                # 关联到人物
                best_face.face_identity_id = id
                # 可以选择设置 recognize_confidence，这里设为 1.0 表示手动确认
                best_face.recognize_confidence = 1.0
                db.add(best_face)
                count += 1
                
        else:
            # 5. 如果仍然没有人脸（AI未识别到），创建默认人脸
            dummy_face = Face(
                photo_id=photo_id,
                face_identity_id=id,
                face_feature=None,
                face_rect=None,
                face_confidence=1.0,
                recognize_confidence=1.0
            )
            db.add(dummy_face)
            count += 1
            
    db.commit()
    from app.crud.album import trigger_conditional_albums_update
    trigger_conditional_albums_update(db, current_user.id, payload.photo_ids)
    return BaseResponse(code=200, msg="添加成功", data={"status": "success", "count": count})

@router.put("/identities/{id}", response_model=BaseResponse[FaceIdentitySchema], summary="更新人物信息", description="修改人物的显示名称、描述和标签")
def update_identity(
    id: UUID = Path(..., description="人物ID"),
    payload: schemas.FaceIdentityUpdate = Body(..., description="人物更新信息"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    更新人物信息（名称、描述、标签）。
    """
    updated_identity = crud_face.update_identity(db, id, payload, owner_id=current_user.id)
    if not updated_identity:
        raise HTTPException(status_code=404, detail="Identity not found")

    return BaseResponse(code=200, msg="更新成功", data=updated_identity)

@router.get("/identities", response_model=BaseResponse[List[FaceIdentitySchema]],summary="获取人物列表", description="获取所有已识别的人物列表，支持分页，返回包含封面信息和照片数量的人物对象")
def list_identities(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=10000, description="每页数量"),
    types: List[str] = Query(["named", "unnamed"], alias="types" , description="人物类型筛选：named, unnamed, hidden"),
    min_photos: Optional[int] = Query(None, ge=0, description="最低照片数过滤阈值；不传时取用户配置 ai.face_recognition_min_photos"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取人物列表，包含每个人的封面照片和照片总数。
    """
    # 显式传入的 min_photos 优先（供测试/管理端绕过用户配置），否则回退到用户配置
    if min_photos is None:
        min_photos = config_manager.get_user_config(current_user.id, db).ai.face_recognition_min_photos
    data = crud_face.get_identities_with_details(
        db,
        skip=skip,
        limit=limit,
        min_photos=min_photos,
        visibility_types=types,
        owner_id=current_user.id
    )
    return BaseResponse(code=200, msg="获取成功", data=data)


@router.get("/identities/{id}/photos",response_model=BaseResponse[List[app.schemas.photo.Photo]] ,summary="获取人物照片列表", description="获取指定人物下的所有照片")
def get_identity_photos(
    id: UUID = Path(..., description="人物ID"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    获取指定人物关联的所有照片列表。
    """
    data = crud_face.get_identity_photos(db, id, skip=skip, limit=limit, owner_id=current_user.id)
    return BaseResponse(code=200, msg="获取成功", data=data)

@router.delete("/identities/{id}", summary="删除人物", description="删除指定人物，但保留其关联的照片（解除关联）")
def delete_identity(
    id: UUID = Path(..., description="人物ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    删除人物。
    注意：这会直接删除人物记录，并将关联的人脸数据中的 identity_id 置为 NULL（解除关联）。
    """
    if not crud_face.delete_identity(db, id, owner_id=current_user.id):
        return BaseResponse(code=404, msg="Identity not found", data=None)
    
    from app.crud.album import trigger_conditional_albums_update
    # 删除人物影响的照片不好直接获取，传 None 触发全量扫描
    trigger_conditional_albums_update(db, current_user.id, None)
    return BaseResponse(code=200, msg="删除成功", data={"status": "success"})

@router.post("/identities/{id}/remove-photos", summary="从人物中移除照片", description="将指定照片从该人物中移除（解除人脸关联）")
def remove_photos_from_identity(
    id: UUID = Path(..., description="人物ID"),
    payload: RemovePhotosRequest = Body(..., description="要移除的照片列表"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    批量从人物中移除照片。
    """
    if not crud_face.get_identity(db, id, owner_id=current_user.id):
        return BaseResponse(code=404, msg="Identity not found", data=None)
    
    count = crud_face.remove_photos_from_identity(db, id, payload.photo_ids, owner_id=current_user.id)
    from app.crud.album import trigger_conditional_albums_update
    trigger_conditional_albums_update(db, current_user.id, payload.photo_ids)
    return BaseResponse(code=200, msg="移除成功", data={"status": "success", "count": count})

@router.put("/identities/{id}/cover", summary="设置人物封面", description="将指定照片设为该人物的封面照片")
def set_identity_cover(
    id: UUID = Path(..., description="人物ID"),
    payload: SetCoverRequest = Body(..., description="封面设置请求"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    设置人物的封面照片。
    系统会自动查找该照片中属于该人物的人脸，并将其ID设为默认人脸ID。
    """
    if not crud_face.get_identity(db, id, owner_id=current_user.id):
        return BaseResponse(code=404, msg="Identity not found", data=None)
    
    if not crud_face.set_identity_cover(db, id, payload.photo_id, owner_id=current_user.id):
        return BaseResponse(code=404, msg="Face not found in this photo for this identity", data=None)

    return BaseResponse(code=200, msg="设置成功", data={"status": "success"})

@router.post("/identities/merge", summary="合并人物", description="将多个源人物合并到一个目标人物中")
def merge_identities(
    payload: MergeRequest = Body(..., description="合并请求"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    合并人物。
    """
    if not crud_face.merge_identities(db, payload.target_id, payload.source_ids, owner_id=current_user.id):
         raise HTTPException(status_code=400, detail="Merge failed")

    from app.crud.album import trigger_conditional_albums_update
    # 难以获取所有影响的 photo_ids，传 None 触发全量扫描
    trigger_conditional_albums_update(db, current_user.id, None)
    return BaseResponse(code=200, msg="合并成功", data={"status": "success"})

@router.post("/identities/{id}/rescan", summary="重新扫描人物人脸", description="根据当前人物的人脸中心，重新扫描未分配的人脸并尝试关联")
def rescan_identity(
    id: UUID = Path(..., description="人物ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    重新扫描人物人脸，将符合条件的人脸关联到该人物。
    """
    if not crud_face.get_identity(db, id, owner_id=current_user.id):
        raise HTTPException(status_code=404, detail="Identity not found")
        
    try:
        service = FaceClusterService(db, user_id=current_user.id)
        result = service.rescan_identity(id, owner_id=current_user.id)
    except FaceRescanError as exc:
        raise HTTPException(status_code=500, detail="Face identity rescan failed") from exc

    from app.crud.album import trigger_conditional_albums_update
    affected_photo_ids = [UUID(photo_id) for photo_id in result.pop("affected_photo_ids", [])]
    if affected_photo_ids:
        trigger_conditional_albums_update(db, current_user.id, affected_photo_ids)
    return BaseResponse(code=200, msg="扫描成功", data=result)


@router.post("/identities/{id}/rescan/preview", summary="预览人物重新扫描结果", description="扫描全部有效人脸并返回待新增、改归属和待移出候选，不修改数据")
def preview_identity_rescan(
    id: UUID = Path(..., description="人物ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if not crud_face.get_identity(db, id, owner_id=current_user.id):
        raise HTTPException(status_code=404, detail="Identity not found")

    try:
        service = FaceClusterService(db, user_id=current_user.id)
        result = service.preview_identity_rescan(id, owner_id=current_user.id)
    except FaceRescanError as exc:
        raise HTTPException(status_code=500, detail="Face identity rescan preview failed") from exc
    return BaseResponse(code=200, msg="扫描预览成功", data=result)


@router.post("/identities/{id}/rescan/apply", summary="应用人物重新扫描结果", description="重新校验候选项后，在一个事务中应用用户确认的新增和移出操作")
def apply_identity_rescan(
    payload: schemas.FaceRescanApplyRequest,
    id: UUID = Path(..., description="人物ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if not crud_face.get_identity(db, id, owner_id=current_user.id):
        raise HTTPException(status_code=404, detail="Identity not found")

    try:
        service = FaceClusterService(db, user_id=current_user.id)
        result = service.apply_identity_rescan(
            id,
            owner_id=current_user.id,
            add_face_ids=payload.add_face_ids,
            remove_face_ids=payload.remove_face_ids,
        )
    except FaceRescanConflictError as exc:
        raise HTTPException(status_code=409, detail="Face rescan candidates changed; preview again") from exc
    except FaceRescanError as exc:
        raise HTTPException(status_code=500, detail="Face identity rescan apply failed") from exc

    from app.crud.album import trigger_conditional_albums_update
    affected_photo_ids = [UUID(photo_id) for photo_id in result.pop("affected_photo_ids", [])]
    if affected_photo_ids:
        trigger_conditional_albums_update(db, current_user.id, affected_photo_ids)
    return BaseResponse(code=200, msg="重新扫描结果已应用", data=result)
